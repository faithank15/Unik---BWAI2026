"""Rédaction des courriels de relance par le LLM (extension IA, section 2).

Le code décide et fournit les faits ; le LLM ne fait que formuler dans un cadre fermé. Le texte
généré dépend du cas, de l'étape, du canal et de la version de consigne, pas du client : il est mis
en cache (table `redactions`) et réutilisé pour tous les clients concernés. La génération se fait
HORS transaction (`preparer`) ; l'assemblage dans la transaction d'envoi ne lit que le cache.
Sans LLM, en cas de panne ou de rédaction refusée (W1 à W8), le canevas fixe de l'étape sert de
repli : le repli est journalisé avec son motif et l'envoi n'est jamais bloqué.
"""
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from app import clock
from app.db import transaction
from app.domain import redaction as dom
from app.domain import relances as dom_rel
from app.domain.calendrier import prochain_jour_ouvre
from app.ia.adaptateur import CONSIGNE_REDACTION, Adaptateur, Indisponible
from app.journal import IA, SYSTEME, Acteur, journaliser
from app.parametres import lire_booleen, lire_entier, lire_texte
from app.services import calculs


@dataclass(frozen=True)
class ContexteRedaction:
    cle: str
    cas: str
    ton: str
    ton_plafond: str
    canal: str
    contexte_llm: dict
    faits: dict
    lignes: list[dom.LigneCourriel]
    raison_sociale: str
    reference_paiement: str
    entreprise: str


def active(conn: sqlite3.Connection, canal: str) -> bool:
    """Seul le courriel est rédigé par le LLM ; WhatsApp suivra le même schéma."""
    return canal == "EMAIL" and lire_booleen(conn, "redaction_llm_active")


def construire_contexte(conn: sqlite3.Connection, relance: sqlite3.Row,
                        lignes: list[sqlite3.Row]) -> ContexteRedaction:
    """Tous les faits viennent du code : cas, ton, catégories, variables et leurs valeurs."""
    ref = clock.date_reference(conn)
    etapes = [x["etape_echeance"] for x in lignes]
    ech_ids = [x["echeance_id"] for x in lignes]
    marques = ",".join("?" * len(ech_ids))
    detail = conn.execute(
        f"SELECT c.echeance_id, c.facture_id, c.date_echeance, c.solde, c.retard_jours, "
        f"f.numero, f.date_emission, f.client_id FROM v_echeances_calc c JOIN factures f ON "
        f"f.id = c.facture_id WHERE c.echeance_id IN ({marques}) ORDER BY c.date_echeance, "
        f"c.echeance_id", ech_ids).fetchall()
    client_id = detail[0]["client_id"]
    factures = sorted({d["facture_id"] for d in detail})
    mq = ",".join("?" * len(factures))
    totaux = conn.execute(
        f"SELECT COALESCE(SUM(montant_du), 0) AS du, COALESCE(SUM(affecte), 0) AS paye, "
        f"COALESCE(SUM(solde), 0) AS solde FROM v_echeances_calc WHERE facture_id IN ({mq}) "
        f"AND etat = 'ACTIVE'", factures).fetchone()
    promesse = conn.execute(
        f"SELECT date_promise FROM promesses_paiement WHERE facture_id IN ({mq}) AND statut = "
        f"'NON_TENUE' ORDER BY date_promise DESC LIMIT 1", factures).fetchone()
    histo = calculs.historique_par_client(conn, calculs.factures_calculees(conn)).get(
        client_id, (0, 0))
    cas = dom.determiner_cas(
        promesse is not None, totaux["paye"] > 0, histo[0], histo[1],
        lire_entier(conn, "retards_retardataire_habituel"))
    ton_max = dom_rel.ton(etapes)                    # étape la plus grave du message
    ton_plafond = dom.ton_de_l_etape(ton_max)
    nb_cat = "UNE" if len(factures) == 1 else "PLUSIEURS"
    total_solde = sum(d["solde"] for d in detail)
    retard_max = max(d["retard_jours"] for d in detail)
    dernier = conn.execute(
        "SELECT COALESCE(categorie_validee, categorie_ia) AS c FROM messages_entrants WHERE "
        "client_id = ? AND COALESCE(categorie_validee, categorie_ia) IS NOT NULL "
        "ORDER BY date_reception DESC, id DESC LIMIT 1", (client_id,)).fetchone()
    client = conn.execute("SELECT raison_sociale FROM clients WHERE id = ?",
                          (client_id,)).fetchone()
    pref = conn.execute("SELECT interlocuteur FROM preferences_contact WHERE client_id = ?",
                        (client_id,)).fetchone()
    entreprise = lire_texte(conn, "nom_entreprise_emettrice")
    limite = prochain_jour_ouvre(
        ref + timedelta(days=lire_entier(conn, "delai_limite_jours")),
        {date.fromisoformat(r[0]) for r in conn.execute("SELECT date FROM jours_feries")})
    plus_ancienne = min(date.fromisoformat(d["date_echeance"]) for d in detail)
    faits = {
        "client": client["raison_sociale"],
        "interlocuteur": (pref["interlocuteur"] if pref and pref["interlocuteur"]
                          else dom.SALUTATION_DEFAUT),
        "numero_facture": ", ".join(sorted({d["numero"] for d in detail})),
        "nb_factures": str(len(factures)),
        "montant_total": f"{dom.formater_montant(totaux['du'])} FCFA",
        "solde": f"{dom.formater_montant(total_solde)} FCFA",
        "date_echeance": dom.formater_date(plus_ancienne),
        "date_limite": dom.formater_date(limite),
        "jours_retard": str(retard_max),
        "entreprise_emettrice": entreprise,
    }
    if totaux["paye"] > 0:
        faits["montant_paye"] = f"{dom.formater_montant(totaux['paye'])} FCFA"
    if promesse is not None:
        faits["date_promesse"] = dom.formater_date(date.fromisoformat(promesse["date_promise"]))
    annee = ref.year
    numero = int(relance["id"].split("-")[1])
    contexte = dom.contexte_llm(
        etape=ton_max, canal=relance["canal"], cas=cas, ton_cible=ton_plafond,
        nb_factures=nb_cat, anciennete_retard=dom.categorie_anciennete(retard_max),
        enjeu=dom.categorie_enjeu(total_solde, lire_entier(conn, "seuil_gros_montant")),
        dernier_echange=dernier["c"] if dernier else None,
        variables_disponibles=sorted(faits))
    return ContexteRedaction(
        cle=dom.cle_cache(cas, ton_plafond, relance["canal"], nb_cat, CONSIGNE_REDACTION),
        cas=cas,
        ton=ton_plafond, ton_plafond=ton_plafond, canal=relance["canal"],
        contexte_llm=contexte, faits=faits,
        lignes=[dom.LigneCourriel(d["numero"], date.fromisoformat(d["date_emission"]),
                                  date.fromisoformat(d["date_echeance"]), d["retard_jours"],
                                  d["solde"]) for d in detail],
        raison_sociale=client["raison_sociale"],
        reference_paiement=f"MM-SIM-{annee}-{numero:06d}", entreprise=entreprise)


def lire_cache(conn: sqlite3.Connection, cle: str) -> dom.Redaction | None:
    r = conn.execute("SELECT objet, introduction, conclusion, ton_applique FROM redactions "
                     "WHERE cle = ?", (cle,)).fetchone()
    return dom.Redaction(*tuple(r)) if r else None


def assembler(conn: sqlite3.Connection, ctx: ContexteRedaction, acteur: Acteur | None = None,
              relance_id: str | None = None) -> tuple[str, str] | None:
    """(objet, corps) depuis le cache, ou None (repli sur le canevas). Dans la transaction
    d'envoi (`acteur` donné) un repli par assemblage impossible est journalisé."""
    red = lire_cache(conn, ctx.cle)
    if red is None:
        return None
    try:
        return dom.assembler_courriel(red, ctx.faits, ctx.lignes, ctx.raison_sociale,
                                      ctx.reference_paiement, ctx.entreprise)
    except dom.RedactionInvalide as e:
        if acteur is not None:
            journaliser(conn, "REDACTION_REPLI", "RELANCE", relance_id, acteur=acteur,
                        details={"cle": ctx.cle, "motif": e.regle, "detail": e.detail})
        return None


def preparer(conn: sqlite3.Connection, adaptateur: Adaptateur | None,
             relance_id: str) -> dict:
    """Génère (hors transaction) la rédaction d'une relance par courriel si le cache n'a pas déjà
    celle de son cas. Retourne l'origine : LLM_CACHE, LLM ou REPLI (avec le motif)."""
    r = conn.execute("SELECT * FROM relances WHERE id = ?", (relance_id,)).fetchone()
    if r is None or r["statut"] not in ("PLANIFIEE", "EN_ATTENTE_VALIDATION") \
            or not active(conn, r["canal"]):
        return {"origine": "CANEVAS", "motif": "NON_APPLICABLE"}
    if adaptateur is None or adaptateur.client is None \
            or not hasattr(adaptateur.client, "rediger"):
        return {"origine": "CANEVAS", "motif": "LLM_NON_CONFIGURE"}   # aucun bruit de journal
    lignes = conn.execute("SELECT echeance_id, etape_echeance FROM relance_lignes WHERE "
                          "relance_id = ?", (relance_id,)).fetchall()
    if not lignes:
        return {"origine": "CANEVAS", "motif": "AUCUNE_LIGNE"}
    ctx = construire_contexte(conn, r, lignes)
    if lire_cache(conn, ctx.cle) is not None:
        return {"origine": "LLM_CACHE", "cle": ctx.cle}
    simulation = lire_booleen(conn, "simulation_llm_indisponible")
    try:
        if adaptateur is None:
            raise Indisponible("Aucun LLM configuré.")
        red = adaptateur.rediger(ctx.contexte_llm, ctx.ton_plafond, simulation)
        # La rédaction doit aussi s'assembler avec les faits de ce message (variables valides)
        dom.assembler_courriel(red, ctx.faits, ctx.lignes, ctx.raison_sociale,
                               ctx.reference_paiement, ctx.entreprise)
    except Indisponible as e:
        _journaliser_repli(conn, relance_id, ctx.cle, "INDISPONIBLE", str(e))
        return {"origine": "REPLI", "motif": "INDISPONIBLE"}
    except dom.RedactionInvalide as e:
        _journaliser_repli(conn, relance_id, ctx.cle, e.regle, e.detail)
        return {"origine": "REPLI", "motif": e.regle}
    with transaction(conn):
        deja = conn.execute("SELECT 1 FROM redactions WHERE cle = ?", (ctx.cle,)).fetchone()
        if not deja:
            conn.execute(
                "INSERT INTO redactions(cle, cas, ton, canal, nb_factures, version, "
                "modele_version, objet, introduction, conclusion, ton_applique, cree_le) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ctx.cle, ctx.cas, ctx.ton, ctx.canal, ctx.contexte_llm["nb_factures"],
                 CONSIGNE_REDACTION, adaptateur.version_redaction, red.objet,
                 red.introduction, red.conclusion, red.ton_applique, clock.maintenant()))
            journaliser(conn, "REDACTION_GENEREE", "REDACTION", ctx.cle, acteur=IA,
                        details={"cas": ctx.cas, "ton": ctx.ton, "canal": ctx.canal,
                                 "modele_version": adaptateur.version_redaction,
                                 "relance_id": relance_id})
    return {"origine": "LLM", "cle": ctx.cle}


def _journaliser_repli(conn: sqlite3.Connection, relance_id: str, cle: str, motif: str,
                       detail: str) -> None:
    with transaction(conn):
        journaliser(conn, "REDACTION_REPLI", "RELANCE", relance_id, acteur=SYSTEME,
                    details={"cle": cle, "motif": motif, "detail": detail[:200]})


# ---- relecture humaine -----------------------------------------------------------------
def lister(conn: sqlite3.Connection, statut: str | None = None) -> list[dict]:
    sql = "SELECT * FROM redactions" + (" WHERE statut = ?" if statut else "") + " ORDER BY cle"
    return [dict(r) for r in conn.execute(sql, (statut,) if statut else ())]


def marquer_relue(conn: sqlite3.Connection, cle: str, acteur: Acteur) -> dict:
    from app.errors import Introuvable
    with transaction(conn):
        r = conn.execute("SELECT * FROM redactions WHERE cle = ?", (cle,)).fetchone()
        if r is None:
            raise Introuvable(f"Rédaction {cle} introuvable.")
        if r["statut"] != "RELUE":
            conn.execute("UPDATE redactions SET statut = 'RELUE' WHERE cle = ?", (cle,))
            journaliser(conn, "REDACTION_RELUE", "REDACTION", cle, acteur=acteur,
                        avant={"statut": r["statut"]}, apres={"statut": "RELUE"})
    return {**dict(r), "statut": "RELUE"}
