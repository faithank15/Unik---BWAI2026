"""Moteur de relances (spécification, section 7) : planifier, revérifier, envoyer.

Le moteur fonctionne en deux temps. `planifier` décide chaque jour quelles relances préparer ;
`envoyer_relance` les revérifie une à une, dans une transaction `BEGIN IMMEDIATE`, avant l'envoi
simulé. Chacun est idempotent et sans mémoire d'un jour à l'autre : tout se recalcule à partir
de la base. Aucun appel au LLM, aucun accès réseau : l'envoi s'écrit dans `envois_simules`.
"""
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app import clock
from app.db import prochain_id, transaction
from app.domain import canevas
from app.domain import relances as dom
from app.domain.calendrier import est_jour_ouvre
from app.errors import Introuvable
from app.journal import Acteur, journaliser
from app.parametres import lire_booleen, lire_entier, lire_texte
from app.services import parametres as svc_parametres
from app.services.revue import ouvrir_revue, resoudre_revues


# ---- chargement du contexte -------------------------------------------------------------
def charger_params(conn: sqlite3.Connection) -> dom.ParamsRelances:
    return dom.ParamsRelances(
        jours={"P": lire_entier(conn, "jours_p"), "R1": lire_entier(conn, "jours_r1"),
               "R2": lire_entier(conn, "jours_r2"), "R3": lire_entier(conn, "jours_r3")},
        rappel_preventif_actif=lire_booleen(conn, "rappel_preventif_actif"),
        espacement_normal=lire_entier(conn, "espacement_normal_jours"),
        espacement_rattrapage=lire_entier(conn, "espacement_rattrapage_jours"),
        seuil_gros_montant=lire_entier(conn, "seuil_gros_montant"),
        delai_escalade=lire_entier(conn, "delai_escalade_jours"),
        marge_promesse=lire_entier(conn, "marge_promesse_jours"))


@dataclass
class Contexte:
    ref: date
    p: dom.ParamsRelances
    feries: set[date]
    contestations: list[tuple[str, str | None]] = field(default_factory=list)
    promesses: dict[str, list[date]] = field(default_factory=dict)
    accords_acceptes: set[str] = field(default_factory=set)
    factures_impayees: set[str] = field(default_factory=set)
    messages: list[tuple[str, str | None]] = field(default_factory=list)


def charger_contexte(conn: sqlite3.Connection) -> Contexte:
    ctx = Contexte(ref=clock.date_reference(conn), p=charger_params(conn),
                   feries={date.fromisoformat(r[0]) for r in
                           conn.execute("SELECT date FROM jours_feries")})
    ctx.contestations = [(r[0], r[1]) for r in conn.execute(
        "SELECT facture_id, echeance_id FROM contestations WHERE statut = 'OUVERTE'")]
    for r in conn.execute("SELECT facture_id, date_promise FROM promesses_paiement "
                          "WHERE statut = 'EN_COURS'"):
        ctx.promesses.setdefault(r[0], []).append(date.fromisoformat(r[1]))
    ctx.accords_acceptes = {r[0] for r in conn.execute(
        "SELECT facture_id FROM accords_echeancier WHERE statut = 'ACCEPTE'")}
    ctx.factures_impayees = {r[0] for r in conn.execute(
        "SELECT DISTINCT facture_id FROM v_echeances_calc WHERE etat = 'ACTIVE' "
        "AND retard_jours > 0")}
    ctx.messages = [(r[0], r[1]) for r in conn.execute(
        "SELECT client_id, facture_citee_id FROM messages_entrants "
        "WHERE statut_traitement IN ('A_CLASSER', 'EN_REVUE') "
        "AND COALESCE(categorie_validee, categorie_ia, '') != 'DEMANDE_COPIE_FACTURE'")]
    return ctx


def motif_suspension(ctx: Contexte, facture_id: str, echeance_id: str,
                     client_id: str) -> str | None:
    """Suspensions (section 7.3), recalculées à chaque exécution et jamais stockées."""
    for f, e in ctx.contestations:
        if f == facture_id and (e is None or e == echeance_id):
            return "SUSPENDU_CONTESTATION"
    for d in ctx.promesses.get(facture_id, []):
        if ctx.ref <= d + _jours(ctx.p.marge_promesse):
            return "SUSPENDU_PROMESSE"
    if facture_id in ctx.accords_acceptes and facture_id not in ctx.factures_impayees:
        return "SUSPENDU_ECHEANCIER"
    for c, f in ctx.messages:
        if c == client_id and (f is None or f == facture_id):
            return "SUSPENDU_MESSAGE_EN_ATTENTE"
    return None


def _jours(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def _candidats(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Échéances ACTIVE au solde positif d'une facture VALIDEE."""
    return conn.execute(
        "SELECT c.echeance_id, c.facture_id, c.date_echeance, c.solde, f.client_id, "
        "f.numero, f.taux_penalite_retard FROM v_echeances_calc c "
        "JOIN factures f ON f.id = c.facture_id "
        "WHERE c.etat = 'ACTIVE' AND c.solde > 0 AND f.statut_document = 'VALIDEE' "
        "ORDER BY c.echeance_id").fetchall()


def _clients(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["id"]: r for r in conn.execute(
        "SELECT c.id, c.email, c.whatsapp, p.canal_prefere, p.canaux_autorises, "
        "p.consentement_relance, p.interlocuteur FROM clients c "
        "LEFT JOIN preferences_contact p ON p.client_id = c.id")}


def canal_du_client(c: sqlite3.Row) -> tuple[str | None, str | None]:
    return dom.choisir_canal(
        c["canal_prefere"], (c["canaux_autorises"] or "").split(";"),
        None if c["consentement_relance"] is None else bool(c["consentement_relance"]),
        c["email"], c["whatsapp"])


def _traitees(conn: sqlite3.Connection, exclure_relance: str | None = None
              ) -> dict[str, dict[str, dom.EtapeTraitee]]:
    """Étapes déjà mentionnées par une ligne de relance, quel que soit son statut."""
    out: dict[str, dict[str, dom.EtapeTraitee]] = defaultdict(dict)
    for r in conn.execute(
            "SELECT l.echeance_id, l.etape_echeance, r.statut, r.date_envoi, r.id "
            "FROM relance_lignes l JOIN relances r ON r.id = l.relance_id"):
        if r["id"] == exclure_relance:
            continue
        statut = {"ENVOYEE_SIM": "ENVOYEE", "SAUTEE": "SAUTEE"}.get(r["statut"], "AUTRE")
        actuel = out[r["echeance_id"]].get(r["etape_echeance"])
        if actuel is None or statut == "ENVOYEE":
            out[r["echeance_id"]][r["etape_echeance"]] = dom.EtapeTraitee(
                statut, date.fromisoformat(r["date_envoi"]) if r["date_envoi"] else None)
    return out


def _dernier_envoi(conn: sqlite3.Connection, client_id: str, canal: str,
                   exclure: str | None = None) -> date | None:
    r = conn.execute("SELECT MAX(date_envoi) FROM relances WHERE client_id = ? AND canal = ? "
                     "AND statut = 'ENVOYEE_SIM' AND id != ?",
                     (client_id, canal, exclure or "")).fetchone()[0]
    return date.fromisoformat(r) if r else None


# ---- planification ----------------------------------------------------------------------
def _maj_promesses(conn: sqlite3.Connection, ctx: Contexte, acteur: Acteur) -> None:
    """Promesses EN_COURS : TENUE si la facture est soldée, NON_TENUE une fois la marge passée."""
    for r in conn.execute("SELECT id, facture_id, date_promise FROM promesses_paiement "
                          "WHERE statut = 'EN_COURS' ORDER BY id").fetchall():
        solde = conn.execute("SELECT solde FROM v_factures_solde WHERE facture_id = ?",
                             (r["facture_id"],)).fetchone()[0]
        if solde == 0:
            nouveau, evt = "TENUE", "PROMESSE_TENUE"
        elif date.fromisoformat(r["date_promise"]) + _jours(ctx.p.marge_promesse) < ctx.ref:
            nouveau, evt = "NON_TENUE", "PROMESSE_NON_TENUE"
        else:
            continue
        conn.execute("UPDATE promesses_paiement SET statut = ? WHERE id = ?", (nouveau, r["id"]))
        journaliser(conn, evt, "PROMESSE", r["id"], avant={"statut": "EN_COURS"},
                    apres={"statut": nouveau}, acteur=acteur)


def planifier(conn: sqlite3.Connection, acteur: Acteur) -> dict:
    """Planification du jour (section 7.1). Un jour non ouvré ne crée rien."""
    with transaction(conn):
        ref = clock.date_reference(conn)
        p = charger_params(conn)
        feries = {date.fromisoformat(r[0]) for r in conn.execute("SELECT date FROM jours_feries")}
        vide = {"traitement_id": None, "date_reference": ref.isoformat(), "jour_ouvre": False,
                "creees": 0, "sautees": 0, "reportees_espacement": 0, "escalades": 0,
                "suspendues": []}
        if not est_jour_ouvre(ref, feries):
            journaliser(conn, "JOUR_NON_OUVRE", "SYSTEME", None, acteur=acteur,
                        details={"date": ref.isoformat()})
            return vide
        trt = prochain_id(conn, "TRT")
        conn.execute("INSERT INTO traitements_lot(id, type, date_reference, statut, debut) "
                     "VALUES (?, 'PLANIFICATION', ?, 'EN_COURS', ?)",
                     (trt, ref.isoformat(), clock.maintenant()))
        ctx = charger_contexte(conn)
        _maj_promesses(conn, ctx, acteur)
        ctx = charger_contexte(conn)
        clients = _clients(conn)
        traitees = _traitees(conn)
        candidats = _candidats(conn)
        resume = {**vide, "traitement_id": trt, "jour_ouvre": True}
        groupes: dict[tuple[str, str], list[dict]] = defaultdict(list)
        non_suspendues = []
        for e in candidats:
            motif = motif_suspension(ctx, e["facture_id"], e["echeance_id"], e["client_id"])
            if motif:
                resume["suspendues"].append({"echeance_id": e["echeance_id"], "motif": motif})
                _journaliser_suspension(conn, e["echeance_id"], motif, ref, acteur)
                continue
            non_suspendues.append(e)
            c = clients[e["client_id"]]
            canal, motif_revue = canal_du_client(c)
            steps = traitees[e["echeance_id"]]
            res = dom.etape_a_preparer(
                date.fromisoformat(e["date_echeance"]), steps, ref, feries, p,
                p_applicable=e["facture_id"] not in ctx.accords_acceptes)
            if canal is None:
                if res.candidate:
                    ouvrir_revue(conn, motif_revue, "CLIENT", e["client_id"], e["client_id"],
                                 "Relance due mais contact impossible", acteur)
                continue
            for etape, motif_saut in res.sautees:
                _creer_sautee(conn, e, canal, etape, motif_saut, ref, trt, acteur)
                steps[etape] = dom.EtapeTraitee("SAUTEE")
                resume["sautees"] += 1
            if res.candidate:
                groupes[(e["client_id"], canal)].append({"e": e, "cand": res.candidate})
        envois: dict[tuple[str, str], date | None] = {}
        for (client, canal), lignes in sorted(groupes.items()):
            if conn.execute("SELECT 1 FROM relances WHERE client_id = ? AND canal = ? AND "
                            "statut IN ('PLANIFIEE', 'EN_ATTENTE_VALIDATION')",
                            (client, canal)).fetchone():
                continue  # une relance est déjà en cours pour ce client et ce canal
            dernier = envois.setdefault((client, canal), _dernier_envoi(conn, client, canal))
            ecart = dom.ecart_minimal(any(x["cand"].rattrapage for x in lignes), p)
            if not dom.espacement_respecte(ref, dernier, ecart):
                resume["reportees_espacement"] += 1
                journaliser(conn, "RELANCE_REPORTEE_ESPACEMENT", "CLIENT", client, acteur=acteur,
                            details={"canal": canal, "dernier_envoi": dernier.isoformat(),
                                     "ecart_minimal": ecart})
                continue
            total = sum(x["e"]["solde"] for x in lignes)
            etapes = [x["cand"].etape for x in lignes]
            motif = dom.motif_de_planification(
                total, len(lignes), any(x["cand"].date_effective == ref
                                        and x["cand"].date_brute != ref for x in lignes), p)
            cle = dom.cle_idempotence(client, canal, [(x["e"]["echeance_id"], x["cand"].etape)
                                                       for x in lignes], ref)
            if conn.execute("SELECT 1 FROM relances WHERE cle_idempotence = ?",
                            (cle,)).fetchone():
                continue
            rid = prochain_id(conn, "REL")
            conn.execute(
                "INSERT INTO relances(id, client_id, canal, etape, date_prevue, statut, motif, "
                "cle_idempotence, traitement_id) VALUES (?,?,?,?,?,'PLANIFIEE',?,?,?)",
                (rid, client, canal, dom.etape_de_relance(etapes), ref.isoformat(), motif,
                 cle, trt))
            for x in sorted(lignes, key=lambda y: y["e"]["echeance_id"]):
                conn.execute("INSERT INTO relance_lignes(relance_id, echeance_id, "
                             "etape_echeance) VALUES (?,?,?)",
                             (rid, x["e"]["echeance_id"], x["cand"].etape))
            journaliser(conn, "RELANCE_PLANIFIEE", "RELANCE", rid, acteur=acteur,
                        apres={"client_id": client, "canal": canal, "etapes": sorted(etapes),
                               "total_solde": total}, details={"motif": motif})
            resume["creees"] += 1
        # Escalade : R3 envoyée depuis au moins delai_escalade_jours, sans suite
        for e in non_suspendues:
            r3 = traitees[e["echeance_id"]].get("R3")
            if r3 and r3.statut == "ENVOYEE" and dom.escalade_due(r3.date_envoi, ref, p):
                if ouvrir_revue(conn, "ESCALADE", "ECHEANCE", e["echeance_id"], e["client_id"],
                                "R3 sans suite", acteur):
                    journaliser(conn, "ESCALADE_CREEE", "ECHEANCE", e["echeance_id"],
                                acteur=acteur, details={"r3_envoyee_le": r3.date_envoi.isoformat()})
                    resume["escalades"] += 1
        conn.execute("UPDATE traitements_lot SET statut = 'TERMINE', fin = ?, nb_total = ?, "
                     "nb_traites = ?, details = ? WHERE id = ?",
                     (clock.maintenant(), resume["creees"] + resume["sautees"],
                      resume["creees"] + resume["sautees"],
                      json.dumps({k: v for k, v in resume.items() if k != "suspendues"}), trt))
        return resume


def _journaliser_suspension(conn: sqlite3.Connection, echeance_id: str, motif: str, ref: date,
                            acteur: Acteur) -> None:
    """RELANCE_SUSPENDUE : une seule fois par échéance, motif et jour."""
    deja = conn.execute("SELECT 1 FROM journal WHERE type_evenement = 'RELANCE_SUSPENDUE' AND "
                        "objet_id = ? AND date_reference = ? AND details LIKE ?",
                        (echeance_id, ref.isoformat(), f'%"{motif}"%')).fetchone()
    if not deja:
        journaliser(conn, "RELANCE_SUSPENDUE", "ECHEANCE", echeance_id, acteur=acteur,
                    details={"motif": motif})


def _creer_sautee(conn: sqlite3.Connection, e: sqlite3.Row, canal: str, etape: str, motif: str,
                  ref: date, trt: str, acteur: Acteur) -> None:
    """Rappel P qui ne sera jamais préparé : une relance SAUTEE, une ligne, jamais regroupée."""
    cle = dom.cle_idempotence(e["client_id"], canal, [(e["echeance_id"], etape)], ref)
    if conn.execute("SELECT 1 FROM relances WHERE cle_idempotence = ?", (cle,)).fetchone():
        return
    rid = prochain_id(conn, "REL")
    conn.execute("INSERT INTO relances(id, client_id, canal, etape, date_prevue, statut, motif, "
                 "cle_idempotence, traitement_id) VALUES (?,?,?,?,?,'SAUTEE',?,?,?)",
                 (rid, e["client_id"], canal, etape, ref.isoformat(), motif, cle, trt))
    conn.execute("INSERT INTO relance_lignes(relance_id, echeance_id, etape_echeance) "
                 "VALUES (?,?,?)", (rid, e["echeance_id"], etape))
    journaliser(conn, "RELANCE_SAUTEE", "RELANCE", rid, acteur=acteur,
                details={"echeance_id": e["echeance_id"], "motif": motif})


# ---- vérification et envoi --------------------------------------------------------------
def _verifier_ligne(conn: sqlite3.Connection, ctx: Contexte, echeance_id: str) -> str | None:
    """Motif d'annulation d'une ligne, ou None si elle reste justifiée (section 7.8)."""
    e = conn.execute(
        "SELECT c.solde, c.facture_id, f.client_id, f.statut_document FROM v_echeances_calc c "
        "JOIN factures f ON f.id = c.facture_id WHERE c.echeance_id = ?",
        (echeance_id,)).fetchone()
    if e["solde"] <= 0:
        return "SOLDE_NUL"
    if e["statut_document"] == "ANNULEE":
        return "FACTURE_ANNULEE"
    m = motif_suspension(ctx, e["facture_id"], echeance_id, e["client_id"])
    return dom.MOTIFS_SUSPENSION_VERS_ANNULATION[m] if m else None


def _verifier_contact(conn: sqlite3.Connection, client_id: str, canal: str) -> str | None:
    c = _clients(conn)[client_id]
    valide, motif = canal_du_client(c)
    if valide is None:
        return motif
    aut = (c["canaux_autorises"] or "").split(";")
    ok = canal in aut and bool(c["email"] if canal == "EMAIL" else c["whatsapp"])
    return None if ok else "CANAL_INVALIDE"


def _annuler(conn: sqlite3.Connection, r: sqlite3.Row, motif: str, acteur: Acteur) -> None:
    """Annulation : les lignes sont conservées (les étapes restent « traitées »)."""
    conn.execute("UPDATE relances SET statut = 'ANNULEE', motif = ? WHERE id = ?",
                 (motif, r["id"]))
    journaliser(conn, "RELANCE_ANNULEE", "RELANCE", r["id"], acteur=acteur,
                avant={"statut": r["statut"]}, apres={"statut": "ANNULEE"},
                details={"motif": motif})
    resoudre_revues(conn, "GROS_MONTANT", "RELANCE", r["id"], "RELANCE_ANNULEE", acteur,
                    f"Annulée : {motif}")


def _reverifier(conn: sqlite3.Connection, ctx: Contexte, r: sqlite3.Row, acteur: Acteur
                ) -> str | None:
    """Contrôles 2 à 4 sur les lignes et le contact. Retire les lignes injustifiées ; annule
    la relance s'il n'en reste aucune. Retourne le motif d'annulation, sinon None."""
    lignes = conn.execute("SELECT echeance_id, etape_echeance FROM relance_lignes "
                          "WHERE relance_id = ? ORDER BY echeance_id", (r["id"],)).fetchall()
    retirees = [(l_, m) for l_ in lignes if (m := _verifier_ligne(conn, ctx, l_["echeance_id"]))]
    if retirees:
        if len(retirees) == len(lignes):
            _annuler(conn, r, retirees[0][1], acteur)
            return retirees[0][1]
        for l_, m in retirees:
            conn.execute("DELETE FROM relance_lignes WHERE relance_id = ? AND echeance_id = ?",
                         (r["id"], l_["echeance_id"]))
            journaliser(conn, "LIGNE_RETIREE", "RELANCE", r["id"], acteur=acteur,
                        details={"echeance_id": l_["echeance_id"], "motif": m})
        restantes = [x["etape_echeance"] for x in lignes
                     if x["echeance_id"] not in {y[0]["echeance_id"] for y in retirees}]
        conn.execute("UPDATE relances SET etape = ? WHERE id = ?",
                     (dom.etape_de_relance(restantes), r["id"]))
    motif = _verifier_contact(conn, r["client_id"], r["canal"])
    if motif:
        _annuler(conn, r, motif, acteur)
        return motif
    return None


def _soldes_courants(conn: sqlite3.Connection, relance_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT l.echeance_id, l.etape_echeance, c.solde, c.date_echeance, f.numero, "
        "f.taux_penalite_retard FROM relance_lignes l "
        "JOIN v_echeances_calc c ON c.echeance_id = l.echeance_id "
        "JOIN factures f ON f.id = c.facture_id WHERE l.relance_id = ? "
        "ORDER BY l.echeance_id", (relance_id,)).fetchall()


def _rendre(conn: sqlite3.Connection, r: sqlite3.Row, lignes: list[sqlite3.Row]
            ) -> tuple[str | None, str]:
    inter = conn.execute("SELECT interlocuteur FROM preferences_contact WHERE client_id = ?",
                         (r["client_id"],)).fetchone()
    ton = dom.ton([l_["etape_echeance"] for l_ in lignes])
    annee = clock.date_reference(conn).year
    numero = int(r["id"].split("-")[1])
    return canevas.rendre(
        ton, r["canal"], inter[0] if inter else None,
        lire_texte(conn, "nom_entreprise_emettrice"),
        [canevas.LigneMessage(l_["numero"], date.fromisoformat(l_["date_echeance"]),
                              l_["solde"], l_["taux_penalite_retard"]) for l_ in lignes],
        f"MM-SIM-{annee}-{numero:06d}")


def traiter_relance(conn: sqlite3.Connection, relance_id: str, acteur: Acteur) -> dict:
    """Corps de `envoyer_relance`, à appeler dans une transaction ouverte (section 7.8)."""
    r = conn.execute("SELECT * FROM relances WHERE id = ?", (relance_id,)).fetchone()
    if r is None:
        raise Introuvable(f"Relance {relance_id} introuvable.")
    if r["statut"] not in ("PLANIFIEE", "EN_ATTENTE_VALIDATION"):
        return {"id": relance_id, "resultat": "DEJA_TRAITEE", "statut": r["statut"]}
    ctx = charger_contexte(conn)
    if not est_jour_ouvre(ctx.ref, ctx.feries):
        return {"id": relance_id, "resultat": "REPORTEE", "statut": r["statut"]}
    motif = _reverifier(conn, ctx, r, acteur)
    if motif:
        return {"id": relance_id, "resultat": "ANNULEE", "statut": "ANNULEE", "motif": motif}
    # Espacement minimal depuis le dernier envoi (hors cette relance)
    traitees = _traitees(conn, exclure_relance=relance_id)
    lignes = conn.execute("SELECT echeance_id, etape_echeance FROM relance_lignes WHERE "
                          "relance_id = ?", (relance_id,)).fetchall()
    rattrapage = False
    for l_ in lignes:
        e = conn.execute("SELECT date_echeance FROM echeances WHERE id = ?",
                         (l_["echeance_id"],)).fetchone()
        d_ech = date.fromisoformat(e[0])
        eff = dom.date_effective(d_ech, l_["etape_echeance"], ctx.p, ctx.feries)
        prevue = date.fromisoformat(r["date_prevue"])
        rattrapage |= dom.en_rattrapage(d_ech, l_["etape_echeance"], eff, prevue,
                                        traitees.get(l_["echeance_id"], {}), ctx.p, ctx.feries)
    dernier = _dernier_envoi(conn, r["client_id"], r["canal"], exclure=relance_id)
    if not dom.espacement_respecte(ctx.ref, dernier, dom.ecart_minimal(rattrapage, ctx.p)):
        _annuler(conn, r, "ESPACEMENT_NON_RESPECTE", acteur)
        return {"id": relance_id, "resultat": "ANNULEE", "statut": "ANNULEE",
                "motif": "ESPACEMENT_NON_RESPECTE"}
    soldes = _soldes_courants(conn, relance_id)
    total = sum(x["solde"] for x in soldes)
    if total > ctx.p.seuil_gros_montant and r["valide_par"] is None:
        if r["statut"] == "PLANIFIEE":
            conn.execute("UPDATE relances SET statut = 'EN_ATTENTE_VALIDATION' WHERE id = ?",
                         (relance_id,))
            ouvrir_revue(conn, "GROS_MONTANT", "RELANCE", relance_id, r["client_id"],
                         f"Solde cumulé {total} FCFA", acteur)
            journaliser(conn, "RELANCE_EN_ATTENTE_VALIDATION", "RELANCE", relance_id,
                        acteur=acteur, avant={"statut": "PLANIFIEE"},
                        apres={"statut": "EN_ATTENTE_VALIDATION"}, details={"total": total})
        return {"id": relance_id, "resultat": "EN_ATTENTE_VALIDATION",
                "statut": "EN_ATTENTE_VALIDATION"}
    objet, contenu = _rendre(conn, r, soldes)
    client = conn.execute("SELECT email, whatsapp FROM clients WHERE id = ?",
                          (r["client_id"],)).fetchone()
    destinataire = client["email"] if r["canal"] == "EMAIL" else client["whatsapp"]
    conn.execute("INSERT INTO envois_simules(id, relance_id, canal, destinataire, objet, "
                 "contenu, horodatage) VALUES (?,?,?,?,?,?,?)",
                 (prochain_id(conn, "ENV"), relance_id, r["canal"], destinataire, objet,
                  contenu, clock.maintenant()))
    conn.execute("UPDATE relances SET statut = 'ENVOYEE_SIM', date_envoi = ?, contenu = ? "
                 "WHERE id = ?", (ctx.ref.isoformat(), contenu, relance_id))
    for x in soldes:
        conn.execute("UPDATE relance_lignes SET solde_au_moment_de_l_envoi = ? WHERE "
                     "relance_id = ? AND echeance_id = ?", (x["solde"], relance_id,
                                                           x["echeance_id"]))
    journaliser(conn, "RELANCE_ENVOYEE_SIM", "RELANCE", relance_id, acteur=acteur,
                avant={"statut": r["statut"]},
                apres={"statut": "ENVOYEE_SIM", "date_envoi": ctx.ref.isoformat()},
                details={"canal": r["canal"], "total_solde": total,
                         "valide_par": r["valide_par"]})
    return {"id": relance_id, "resultat": "ENVOYEE_SIM", "statut": "ENVOYEE_SIM"}


def envoyer_relance(conn: sqlite3.Connection, relance_id: str, acteur: Acteur) -> dict:
    """Revérifie puis envoie une relance. Le second de deux traitements concurrents trouve
    la relance déjà traitée et ne fait rien (scénario S08)."""
    with transaction(conn):
        return traiter_relance(conn, relance_id, acteur)


def valider_relance(conn: sqlite3.Connection, relance_id: str, acteur: Acteur) -> dict:
    """Validation humaine (VALIDATEUR) d'une relance de gros montant : renseigne valide_par,
    résout l'entrée de revue puis rappelle l'envoi, qui revérifie tout."""
    with transaction(conn):
        r = conn.execute("SELECT * FROM relances WHERE id = ?", (relance_id,)).fetchone()
        if r is None:
            raise Introuvable(f"Relance {relance_id} introuvable.")
        if r["statut"] != "EN_ATTENTE_VALIDATION":
            return {"id": relance_id, "resultat": "SANS_EFFET", "statut": r["statut"]}
        conn.execute("UPDATE relances SET valide_par = ? WHERE id = ?", (acteur.id, relance_id))
        resoudre_revues(conn, "GROS_MONTANT", "RELANCE", relance_id, "VALIDEE", acteur)
        journaliser(conn, "RELANCE_VALIDEE", "RELANCE", relance_id, acteur=acteur,
                    details={"valide_par": acteur.id})
        return traiter_relance(conn, relance_id, acteur)


def rejeter_relance(conn: sqlite3.Connection, relance_id: str, acteur: Acteur) -> dict:
    with transaction(conn):
        r = conn.execute("SELECT * FROM relances WHERE id = ?", (relance_id,)).fetchone()
        if r is None:
            raise Introuvable(f"Relance {relance_id} introuvable.")
        if r["statut"] != "EN_ATTENTE_VALIDATION":
            return {"id": relance_id, "resultat": "SANS_EFFET", "statut": r["statut"]}
        conn.execute("UPDATE relances SET statut = 'ANNULEE', motif = 'REJETEE_PAR_VALIDATEUR' "
                     "WHERE id = ?", (relance_id,))
        resoudre_revues(conn, "GROS_MONTANT", "RELANCE", relance_id, "REJETEE", acteur)
        journaliser(conn, "RELANCE_REJETEE", "RELANCE", relance_id, acteur=acteur,
                    avant={"statut": "EN_ATTENTE_VALIDATION"},
                    apres={"statut": "ANNULEE", "motif": "REJETEE_PAR_VALIDATEUR"})
        return {"id": relance_id, "resultat": "ANNULEE", "statut": "ANNULEE",
                "motif": "REJETEE_PAR_VALIDATEUR"}


def annuler_injustifiees(conn: sqlite3.Connection, client_id: str | None, acteur: Acteur
                         ) -> list[dict]:
    """Annulation immédiate (section 7.9), dans la transaction de l'événement : paiement ou
    avoir affecté, contestation ouverte, promesse créée, accord accepté, message en attente.
    Les relances PLANIFIEE et EN_ATTENTE_VALIDATION du client subissent la même vérification
    que juste avant l'envoi."""
    if client_id is None:
        return []
    ctx = charger_contexte(conn)
    annulees = []
    for r in conn.execute("SELECT * FROM relances WHERE client_id = ? AND statut IN "
                          "('PLANIFIEE', 'EN_ATTENTE_VALIDATION') ORDER BY id",
                          (client_id,)).fetchall():
        motif = _reverifier(conn, ctx, r, acteur)
        if motif:
            annulees.append({"id": r["id"], "motif": motif})
    return annulees


# ---- lot d'envoi ------------------------------------------------------------------------
def envoyer_lot(conn: sqlite3.Connection, acteur: Acteur) -> dict:
    """Envoie les relances PLANIFIEE dont la date prévue est atteinte, dans l'ordre des
    identifiants, une transaction par relance, avec progression dans `traitements_lot`.
    Avec `simulation_interruption_apres` = N, le lot s'arrête après N relances (INTERROMPU) ;
    relancé, il ne traite que celles encore PLANIFIEE, sans doublon (scénario S19)."""
    ref = clock.date_reference(conn)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM relances WHERE statut = 'PLANIFIEE' AND date_prevue <= ? ORDER BY id",
        (ref.isoformat(),))]
    limite_txt = lire_texte(conn, "simulation_interruption_apres")
    limite = int(limite_txt) if limite_txt else None
    with transaction(conn):
        trt = prochain_id(conn, "TRT")
        conn.execute("INSERT INTO traitements_lot(id, type, date_reference, statut, debut, "
                     "nb_total) VALUES (?, 'ENVOI', ?, 'EN_COURS', ?, ?)",
                     (trt, ref.isoformat(), clock.maintenant(), len(ids)))
    compte = {"ENVOYEE_SIM": 0, "ANNULEE": 0, "EN_ATTENTE_VALIDATION": 0, "REPORTEE": 0,
              "DEJA_TRAITEE": 0}
    statut, traites = "TERMINE", 0
    for i, rid in enumerate(ids):
        if limite is not None and i >= limite:
            statut = "INTERROMPU"
            with transaction(conn):
                svc_parametres.ecrire_parametre_tx(conn, "simulation_interruption_apres", "",
                                                   acteur)
            break
        res = envoyer_relance(conn, rid, acteur)
        compte[res["resultat"]] = compte.get(res["resultat"], 0) + 1
        traites += 1
        with transaction(conn):
            conn.execute("UPDATE traitements_lot SET nb_traites = ? WHERE id = ?", (traites, trt))
    with transaction(conn):
        conn.execute("UPDATE traitements_lot SET statut = ?, fin = ?, nb_traites = ?, "
                     "details = ? WHERE id = ?",
                     (statut, clock.maintenant(), traites, json.dumps(compte), trt))
    return {"traitement_id": trt, "date_reference": ref.isoformat(), "statut": statut,
            "nb_total": len(ids), "nb_traites": traites, "envoyees": compte["ENVOYEE_SIM"],
            "annulees": compte["ANNULEE"], "en_attente_validation": compte[
                "EN_ATTENTE_VALIDATION"], "deja_traitees": compte["DEJA_TRAITEE"]}


def avancer(conn: sqlite3.Connection, jours: int, executer: bool, acteur: Acteur) -> dict:
    """Avance la date de référence d'un jour à la fois ; avec `executer`, lance la
    planification puis l'envoi à chaque jour (les gros montants restent en attente)."""
    resultats = []
    for _ in range(jours):
        suivant = (clock.date_reference(conn) + _jours(1)).isoformat()
        svc_parametres.ecrire_parametre(conn, "date_reference", suivant, acteur)
        jour = {"date": suivant}
        if executer:
            jour["planification"] = planifier(conn, acteur)
            jour["envoi"] = envoyer_lot(conn, acteur)
        resultats.append(jour)
    return {"date_reference": clock.date_reference(conn).isoformat(), "jours": jours,
            "executer": executer, "resultats": resultats}


# ---- lecture ----------------------------------------------------------------------------
def suspensions(conn: sqlite3.Connection) -> list[dict]:
    """Échéances relançables suspendues, avec leur motif, calculées à la demande."""
    ctx = charger_contexte(conn)
    clients = _clients(conn)
    sortie = []
    for e in _candidats(conn):
        m = motif_suspension(ctx, e["facture_id"], e["echeance_id"], e["client_id"])
        if m:
            canal, _ = canal_du_client(clients[e["client_id"]])
            sortie.append({"echeance_id": e["echeance_id"], "facture_id": e["facture_id"],
                           "facture_numero": e["numero"], "client_id": e["client_id"],
                           "canal": canal, "motif": m, "date_echeance": e["date_echeance"],
                           "solde": e["solde"]})
    return sortie


def lire_relance(conn: sqlite3.Connection, relance_id: str) -> dict:
    r = conn.execute("SELECT * FROM relances WHERE id = ?", (relance_id,)).fetchone()
    if r is None:
        raise Introuvable(f"Relance {relance_id} introuvable.")
    envoyee = r["statut"] == "ENVOYEE_SIM"
    lignes_db = conn.execute(
        "SELECT l.echeance_id, l.etape_echeance, l.solde_au_moment_de_l_envoi, c.solde, "
        "c.date_echeance, f.numero, f.taux_penalite_retard FROM relance_lignes l "
        "JOIN v_echeances_calc c ON c.echeance_id = l.echeance_id "
        "JOIN factures f ON f.id = c.facture_id WHERE l.relance_id = ? "
        "ORDER BY l.echeance_id", (relance_id,)).fetchall()
    etapes = {x["echeance_id"]: x["etape_echeance"] for x in lignes_db}
    absorbees = dom.lignes_absorbees(etapes)
    lignes = [{"echeance_id": x["echeance_id"], "facture_numero": x["numero"],
               "etape_echeance": x["etape_echeance"],
               "decision": ("ABSORBEE" if x["echeance_id"] in absorbees else "PREPAREE"),
               "solde": (x["solde_au_moment_de_l_envoi"] if envoyee
                         and x["solde_au_moment_de_l_envoi"] is not None else x["solde"])}
              for x in lignes_db]
    apercu = r["contenu"]
    if apercu is None and r["statut"] in ("PLANIFIEE", "EN_ATTENTE_VALIDATION") and lignes_db:
        objet, corps = _rendre(conn, r, lignes_db)
        apercu = (f"Objet : {objet}\n\n" if objet else "") + corps
    revue = conn.execute("SELECT id FROM file_revue WHERE type = 'GROS_MONTANT' AND "
                         "objet_type = 'RELANCE' AND objet_id = ?", (relance_id,)).fetchone()
    historique = [dict(h) for h in conn.execute(
        "SELECT horodatage, type_evenement, acteur_type, acteur_id, details FROM journal "
        "WHERE objet_type = 'RELANCE' AND objet_id = ? ORDER BY id", (relance_id,))]
    return {"id": r["id"], "client_id": r["client_id"], "canal": r["canal"], "etape": r["etape"],
            "ton": dom.ton(list(etapes.values())) if etapes else r["etape"],
            "date_prevue": r["date_prevue"], "date_envoi": r["date_envoi"],
            "statut": r["statut"], "motif": r["motif"], "valide_par": r["valide_par"],
            "lignes": lignes, "total_solde": sum(x["solde"] for x in lignes),
            "revue_id": revue[0] if revue else None, "contenu_apercu": apercu,
            "historique": historique}


def lister_relances(conn: sqlite3.Connection, statut: str | None = None,
                    client_id: str | None = None, etape: str | None = None,
                    date_: str | None = None) -> list[dict]:
    cond, args = [], []
    for champ, val in (("statut", statut), ("client_id", client_id), ("etape", etape),
                       ("date_prevue", date_)):
        if val:
            cond.append(f"{champ} = ?")
            args.append(val)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    sortie = []
    for r in conn.execute("SELECT * FROM relances" + where + " ORDER BY id", args):
        nb = conn.execute("SELECT COUNT(*) FROM relance_lignes WHERE relance_id = ?",
                          (r["id"],)).fetchone()[0]
        sortie.append({"id": r["id"], "client_id": r["client_id"], "canal": r["canal"],
                       "etape": r["etape"], "date_prevue": r["date_prevue"],
                       "date_envoi": r["date_envoi"], "statut": r["statut"],
                       "motif": r["motif"], "nb_lignes": nb})
    return sortie


def boite_envoi(conn: sqlite3.Connection, canal: str | None = None,
                client_id: str | None = None) -> list[dict]:
    cond, args = [], []
    if canal:
        cond.append("e.canal = ?")
        args.append(canal)
    if client_id:
        cond.append("r.client_id = ?")
        args.append(client_id)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    return [dict(x) for x in conn.execute(
        "SELECT e.id, e.relance_id, r.client_id, e.canal, e.destinataire, e.objet, e.contenu, "
        "e.horodatage, r.date_envoi FROM envois_simules e JOIN relances r ON r.id = "
        "e.relance_id" + where + " ORDER BY e.id", args)]


