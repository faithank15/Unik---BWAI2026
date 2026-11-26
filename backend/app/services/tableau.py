"""Tableau de bord, explications et comparaison à la référence (spécification, section 15).

Tout chiffre affiché renvoie à la liste (route) qui l'explique ; tout résultat calculé (solde,
statut, rang de priorité, relance annulée) renvoie aux pièces et événements qui le produisent.
"""
import json
import sqlite3
from collections import Counter

from app import clock
from app.errors import Introuvable
from app.services import calculs
from app.services import relances as svc_relances

MOTIFS_SUSPENSION = ("SUSPENDU_CONTESTATION", "SUSPENDU_PROMESSE", "SUSPENDU_ECHEANCIER",
                     "SUSPENDU_MESSAGE_EN_ATTENTE")
STATUTS_FACTURE = ("ANNULEE", "SOLDEE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER", "ECHUE",
                   "NON_ECHUE")
TRANCHES = (("non_echu", None, None), ("1_30_jours", 1, 30), ("31_60_jours", 31, 60),
            ("61_90_jours", 61, 90), ("plus_de_90_jours", 91, None))


def _echeances_relancables(conn: sqlite3.Connection) -> list[dict]:
    """Échéances ACTIVE au solde positif d'une facture VALIDEE."""
    factures = calculs.factures_calculees(conn)
    return [e for e in calculs.echeances_calculees(conn)
            if e["etat"] == "ACTIVE" and e["solde"] > 0
            and factures[e["facture_id"]]["statut_document"] == "VALIDEE"]


def tableau_de_bord(conn: sqlite3.Connection) -> dict:
    ref = clock.date_reference(conn).isoformat()
    factures = calculs.factures_calculees(conn)
    ouvertes = [f for f in factures.values() if f["statut_document"] == "VALIDEE"
                and f["solde"] > 0]
    echeances = _echeances_relancables(conn)
    en_retard = [e for e in echeances if e["retard_jours"] > 0]
    total = sum(f["solde"] for f in ouvertes)
    echu = sum(e["solde"] for e in en_retard)
    par_statut = Counter(f["statut"] for f in factures.values())
    retards = [e["retard_jours"] for e in en_retard]
    rel = Counter(r[0] for r in conn.execute(
        "SELECT statut FROM relances WHERE date_prevue = ?", (ref,)))
    susp = Counter(s["motif"] for s in svc_relances.suspensions(conn))
    modes: Counter = Counter()
    non_affectes = {"nb": 0, "montant": 0}
    total_reglements = 0
    for r in conn.execute(
            "SELECT p.mode, p.montant, p.montant - COALESCE((SELECT SUM(montant_affecte) FROM "
            "affectations a WHERE a.paiement_id = p.id), 0) AS reste FROM paiements p"):
        modes[r["mode"]] += r["montant"]
        total_reglements += r["montant"]
        if r["reste"] > 0:
            non_affectes["nb"] += 1
            non_affectes["montant"] += r["reste"]
    revue = Counter(r[0] for r in conn.execute(
        "SELECT type FROM file_revue WHERE statut = 'OUVERTE'"))
    par_cat = Counter(r[0] for r in conn.execute(
        "SELECT COALESCE(categorie_validee, categorie_ia) FROM messages_entrants "
        "WHERE COALESCE(categorie_validee, categorie_ia) IS NOT NULL"))
    reportees = []
    for r in conn.execute(
            "SELECT objet_id, details FROM journal WHERE type_evenement = "
            "'RELANCE_REPORTEE_ESPACEMENT' AND date_reference = ? ORDER BY id", (ref,)):
        d = json.loads(r["details"] or "{}")
        reportees.append({"client_id": r["objet_id"], "canal": d.get("canal"),
                          "raison": "ESPACEMENT_MINIMAL", "total": d.get("total"),
                          "dernier_envoi": d.get("dernier_envoi"),
                          "ecart_minimal_jours": d.get("ecart_minimal"),
                          "prochaine_date_possible": d.get("prochaine_date_possible")})
    prom = Counter(r[0] for r in conn.execute("SELECT statut FROM promesses_paiement"))
    tenues, non_tenues = prom["TENUE"], prom["NON_TENUE"]
    return {
        "date_reference": ref,
        "encours": {"total": total, "echu": echu, "non_echu": total - echu,
                    "nb_factures_ouvertes": len(ouvertes)},
        "factures_par_statut": {s: par_statut.get(s, 0) for s in STATUTS_FACTURE},
        "retards": {"nb_echeances_en_retard": len(en_retard),
                    "retard_moyen_jours": round(sum(retards) / len(retards), 1) if retards
                    else 0, "retard_max_jours": max(retards, default=0)},
        "relances": {"planifiees": rel["PLANIFIEE"],
                     "en_attente_validation": rel["EN_ATTENTE_VALIDATION"],
                     "envoyees_sim": rel["ENVOYEE_SIM"], "annulees": rel["ANNULEE"],
                     "sautees": rel["SAUTEE"]},
        "actions_suspendues": {m: susp.get(m, 0) for m in MOTIFS_SUSPENSION},
        "relances_reportees": reportees,
        "reglements_simules": {"total": total_reglements, "par_mode": dict(modes),
                               "non_affectes": non_affectes},
        "revue": {"total_ouvertes": sum(revue.values()), "par_type": dict(revue)},
        "messages": {"par_statut": dict(Counter(r[0] for r in conn.execute(
            "SELECT statut_traitement FROM messages_entrants"))), "par_categorie": dict(par_cat)},
        "promesses": {"en_cours": prom["EN_COURS"], "tenues": tenues, "non_tenues": non_tenues,
                      "taux_tenues": round(tenues / (tenues + non_tenues), 4)
                      if tenues + non_tenues else 0.0},
        "liens": {
            "encours.total": "/api/factures?solde_min=1",
            "encours.echu": "/api/echeances?en_retard=true",
            "encours.non_echu": "/api/echeances?en_retard=false",
            "factures_par_statut": "/api/factures?statut={statut}",
            "retards": "/api/echeances?en_retard=true",
            "relances": f"/api/relances?date={ref}&statut={{statut}}",
            "actions_suspendues": "/api/relances/suspensions",
            "reglements_simules": "/api/paiements",
            "reglements_simules.non_affectes": "/api/paiements?non_affecte=true",
            "revue": "/api/revue?statut=OUVERTE",
            "messages": "/api/messages?statut_traitement={statut}",
            "promesses": "/api/promesses",
            "balance_agee": "/api/tableau-de-bord/balance-agee",
        },
    }


def balance_agee(conn: sqlite3.Connection) -> dict:
    """Soldes répartis par retard : non échu, 1-30, 31-60, 61-90, plus de 90 jours."""
    echeances = _echeances_relancables(conn)
    tranches = []
    for nom, mini, maxi in TRANCHES:
        sel = [e for e in echeances
               if (e["retard_jours"] == 0 if mini is None else
                   e["retard_jours"] >= mini and (maxi is None or e["retard_jours"] <= maxi))]
        if mini is None:
            lien = "/api/echeances?en_retard=false"
        else:
            lien = f"/api/echeances?retard_min={mini}" + (f"&retard_max={maxi}" if maxi else "")
        tranches.append({"tranche": nom, "nb_echeances": len(sel),
                         "solde": sum(e["solde"] for e in sel), "liste": lien})
    return {"date_reference": clock.date_reference(conn).isoformat(), "tranches": tranches,
            "total": sum(t["solde"] for t in tranches)}


def comparaison_reference(conn: sqlite3.Connection) -> dict:
    """Le système contre la règle naïve « relancer chaque échéance en retard, une relance
    chacune », à la date de référence. Le temps gagné se mesure à part, par chronométrage
    manuel sur 20 dossiers : l'API ne le calcule pas."""
    ref = clock.date_reference(conn).isoformat()
    en_retard = {e["id"]: e for e in _echeances_relancables(conn) if e["retard_jours"] > 0}
    susp = [s for s in svc_relances.suspensions(conn) if s["echeance_id"] in en_retard]
    par_motif = Counter(s["motif"] for s in susp)
    rels = conn.execute("SELECT id, statut FROM relances WHERE date_prevue = ?",
                        (ref,)).fetchall()
    preparees = [r for r in rels if r["statut"] != "SAUTEE"]
    nb_lignes = sum(conn.execute("SELECT COUNT(*) FROM relance_lignes WHERE relance_id = ?",
                                 (r["id"],)).fetchone()[0] for r in preparees)
    c = Counter(r["statut"] for r in rels)
    return {
        "date_reference": ref,
        "reference": {"regle": "relancer chaque échéance en retard, une relance chacune",
                      "nb_relances_naives": len(en_retard),
                      "nb_relances_injustifiees": len(susp),
                      "injustifiees_par_motif": {m: par_motif.get(m, 0)
                                                 for m in MOTIFS_SUSPENSION}},
        "systeme": {"relances_preparees": len(preparees), "lignes_preparees": nb_lignes,
                    "messages_apres_regroupement": len(preparees),
                    "suspensions": len(susp), "annulations": c["ANNULEE"],
                    "envois": c["ENVOYEE_SIM"]},
        "gain": {"relances_injustifiees_evitees": len(susp),
                 "messages_economises_par_le_regroupement": nb_lignes - len(preparees)},
        "liens": {"suspensions": "/api/relances/suspensions",
                  "relances": f"/api/relances?date={ref}"},
    }


MOTIF_STATUT = {
    "ANNULEE": "Le document est annulé",
    "SOLDEE": "Le solde de la facture est nul",
    "CONTESTEE": "Une contestation est ouverte",
    "COUVERTE_PAR_ECHEANCIER": "Un accord d'échéancier est accepté sans tranche échue impayée",
    "NON_ECHUE": "Aucune échéance en retard",
}


def explication_facture(conn: sqlite3.Connection, facture_id: str) -> dict:
    """Assemble tout ce qui justifie le résultat affiché : règle de statut appliquée et
    écartées, échéances, affectations, avoirs, dossiers, relances, messages et journal."""
    f = calculs.factures_calculees(conn).get(facture_id)
    if f is None:
        raise Introuvable(f"Facture {facture_id} introuvable.")
    ech = calculs.echeances_calculees(conn, facture_id=facture_id)
    ech_ids = [e["id"] for e in ech]
    marques = ",".join("?" * len(ech_ids)) or "''"
    affectations = [dict(r) for r in conn.execute(
        f"SELECT a.id, a.echeance_id, a.paiement_id, a.avoir_id, a.montant_affecte, a.mode, "
        f"a.date_affectation FROM affectations a WHERE a.echeance_id IN ({marques}) "
        "ORDER BY a.date_affectation, a.id", ech_ids)]
    avoirs = [dict(r) for r in conn.execute(
        "SELECT id, date_avoir AS date, montant, motif FROM avoirs WHERE facture_id = ? "
        "ORDER BY id", (facture_id,))]
    contestations = [dict(r) for r in conn.execute(
        "SELECT * FROM contestations WHERE facture_id = ? ORDER BY id", (facture_id,))]
    promesses = [dict(r) for r in conn.execute(
        "SELECT * FROM promesses_paiement WHERE facture_id = ? ORDER BY id", (facture_id,))]
    accords = [dict(r) for r in conn.execute(
        "SELECT * FROM accords_echeancier WHERE facture_id = ? ORDER BY id", (facture_id,))]
    relances = []
    for r in conn.execute(
            f"SELECT DISTINCT r.id, l.echeance_id, l.etape_echeance, r.statut, r.date_prevue, "
            f"r.date_envoi, r.motif FROM relance_lignes l JOIN relances r ON r.id = "
            f"l.relance_id WHERE l.echeance_id IN ({marques}) ORDER BY r.date_prevue, r.id",
            ech_ids):
        nb = conn.execute("SELECT COUNT(*) FROM journal WHERE objet_type = 'RELANCE' AND "
                          "objet_id = ?", (r["id"],)).fetchone()[0]
        relances.append({"id": r["id"], "echeance_id": r["echeance_id"],
                         "etape_echeance": r["etape_echeance"], "statut": r["statut"],
                         "date_prevue": r["date_prevue"], "date_envoi": r["date_envoi"],
                         "motif": r["motif"],
                         # relances historiques : sans événement de journal, antérieures au
                         # chargement du jeu de données
                         "anterieure_au_chargement": nb == 0})
    messages = [dict(r) for r in conn.execute(
        "SELECT id, canal, date_reception, statut_traitement, categorie_ia, categorie_validee "
        "FROM messages_entrants WHERE facture_citee_id = ? ORDER BY id", (facture_id,))]
    objets = [("FACTURE", facture_id)] + [("ECHEANCE", e) for e in ech_ids]
    objets += [("PAIEMENT", a["paiement_id"]) for a in affectations if a["paiement_id"]]
    objets += [("AVOIR", a["id"]) for a in avoirs]
    objets += [("RELANCE", r["id"]) for r in relances]
    objets += [("CONTESTATION", c["id"]) for c in contestations]
    objets += [("PROMESSE", p["id"]) for p in promesses]
    objets += [("ACCORD", a["id"]) for a in accords]
    objets += [("MESSAGE", m["id"]) for m in messages]
    journal, vus = [], set()
    for t, i in objets:
        for r in conn.execute("SELECT id, horodatage, date_reference, type_evenement, "
                              "objet_type, objet_id, acteur_type, acteur_id, correlation_id "
                              "FROM journal WHERE objet_type = ? AND objet_id = ? ORDER BY id",
                              (t, i)):
            if r["id"] not in vus:
                vus.add(r["id"])
                journal.append(dict(r))
    journal.sort(key=lambda x: x["id"])
    # règle de statut appliquée et motif
    statut = f["statut"]
    if statut == "ECHUE":
        n = f["retard_jours"]
        motif = f"Une échéance est en retard de {n} jour{'s' if n > 1 else ''}"
    else:
        motif = MOTIF_STATUT[statut]
    return {
        "facture": {"id": f["id"], "numero": f["numero"], "statut": statut, "solde": f["solde"],
                    "affecte": f["affecte"], "retard_jours": f["retard_jours"]},
        "calcul": {
            "regle_statut": {"appliquee": statut,
                             "ecartees": [x["regle"] for x in f["regles_ecartees"]],
                             "motifs_exclusion": f["regles_ecartees"], "motif": motif},
            "echeances": [{k: e[k] for k in ("id", "rang", "date_echeance", "montant_du",
                                             "affecte", "solde", "retard_jours", "etat")}
                          for e in ech]},
        "affectations": affectations, "avoirs": avoirs, "contestations": contestations,
        "promesses": promesses, "accords": accords, "relances": relances,
        "messages": messages, "journal": journal,
    }


