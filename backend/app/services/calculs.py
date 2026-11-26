"""Calculs en lecture : soldes, retards, statuts et priorisation.

Rien n'est stocké. Tout part des vues `v_echeances_calc` et `v_factures_solde`, dont les
résultats doivent égaler exactement la vérité terrain du jeu de données.
"""
import sqlite3
from decimal import Decimal

from app import clock
from app.domain.priorisation import (
    ParametresPriorisation,
    cle_de_tri,
    ratio_retard,
    score,
)
from app.domain.priorisation import Score as ScorePriorite
from app.domain.soldes import EntreeStatut, evaluer_statut, partiellement_payee
from app.parametres import lire_decimal, lire_entier


def parametres_priorisation(conn: sqlite3.Connection) -> ParametresPriorisation:
    return ParametresPriorisation(
        plafond_retard_jours=lire_entier(conn, "plafond_retard_jours"),
        plafond_solde=lire_entier(conn, "plafond_solde"),
        poids_anciennete=lire_entier(conn, "poids_anciennete"),
        poids_solde=lire_entier(conn, "poids_solde"),
        poids_historique=lire_entier(conn, "poids_historique"),
        historique_neutre_points=lire_decimal(conn, "historique_neutre_points"))


def factures_calculees(conn: sqlite3.Connection) -> dict[str, dict]:
    """Toutes les factures avec solde, retard, statut et indicateur « partiellement payée »."""
    contestees = {r[0] for r in conn.execute(
        "SELECT DISTINCT facture_id FROM contestations WHERE statut = 'OUVERTE'")}
    accords = {r[0] for r in conn.execute(
        "SELECT DISTINCT facture_id FROM accords_echeancier WHERE statut = 'ACCEPTE'")}
    resultat: dict[str, dict] = {}
    for r in conn.execute(
            "SELECT f.id, f.numero, f.client_id, f.montant_ttc, f.date_emission, "
            "f.conditions_paiement, f.taux_penalite_retard, f.statut_document, "
            "f.ref_facture_normalisee, v.solde, v.affecte, v.retard_max "
            "FROM factures f JOIN v_factures_solde v ON v.facture_id = f.id ORDER BY f.id"):
        statut, ecartees = evaluer_statut(EntreeStatut(
            statut_document=r["statut_document"], solde=r["solde"],
            contestation_ouverte=r["id"] in contestees, accord_accepte=r["id"] in accords,
            retard_max=r["retard_max"]))
        resultat[r["id"]] = {
            "id": r["id"], "numero": r["numero"], "client_id": r["client_id"],
            "date_emission": r["date_emission"], "montant_ttc": r["montant_ttc"],
            "conditions_paiement": r["conditions_paiement"],
            "taux_penalite_retard": r["taux_penalite_retard"],
            "ref_facture_normalisee": r["ref_facture_normalisee"],
            "statut_document": r["statut_document"], "statut": statut,
            "regles_ecartees": ecartees,
            "partiellement_payee": partiellement_payee(r["affecte"], r["solde"]),
            "solde": r["solde"], "affecte": r["affecte"], "retard_jours": r["retard_max"],
        }
    return resultat


def echeances_calculees(conn: sqlite3.Connection, **filtres) -> list[dict]:
    """Échéances avec affecté, solde et retard (vue v_echeances_calc)."""
    conditions, args = [], []
    if filtres.get("facture_id"):
        conditions.append("c.facture_id = ?")
        args.append(filtres["facture_id"])
    if filtres.get("client_id"):
        conditions.append("f.client_id = ?")
        args.append(filtres["client_id"])
    if filtres.get("en_retard") is True:
        conditions.append("c.retard_jours > 0")
    if filtres.get("en_retard") is False:
        conditions.append("c.retard_jours = 0")
    if filtres.get("retard_min") is not None:
        conditions.append("c.retard_jours >= ?")
        args.append(filtres["retard_min"])
    if filtres.get("retard_max") is not None:
        conditions.append("c.retard_jours <= ?")
        args.append(filtres["retard_max"])
    if filtres.get("echeance_avant"):
        conditions.append("c.date_echeance < ?")
        args.append(filtres["echeance_avant"])
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = ("SELECT c.echeance_id AS id, c.facture_id, f.client_id, c.rang, c.date_echeance, "
           "c.montant_du, c.affecte, c.solde, c.retard_jours, c.etat, c.accord_id "
           "FROM v_echeances_calc c JOIN factures f ON f.id = c.facture_id" + where +
           " ORDER BY c.date_echeance, c.echeance_id")
    return [dict(r) for r in conn.execute(sql, args)]


def _historique_par_client(conn: sqlite3.Connection,
                           factures: dict[str, dict]) -> dict[str, tuple[int, int]]:
    """Par client : (nb de factures soldées en retard, nb de factures soldées). Une facture
    soldée est « en retard » si au moins une échéance a reçu un PAIEMENT daté après sa date
    d'échéance (les avoirs ne comptent pas comme des retards)."""
    en_retard = {r[0] for r in conn.execute(
        "SELECT DISTINCT e.facture_id FROM affectations a "
        "JOIN paiements p ON p.id = a.paiement_id "
        "JOIN echeances e ON e.id = a.echeance_id WHERE p.date_paiement > e.date_echeance")}
    stats: dict[str, list[int]] = {}
    for f in factures.values():
        if f["statut"] != "SOLDEE":
            continue
        s = stats.setdefault(f["client_id"], [0, 0])
        s[1] += 1
        if f["id"] in en_retard:
            s[0] += 1
    return {c: (a, b) for c, (a, b) in stats.items()}


def priorisation(conn: sqlite3.Connection) -> list[dict]:
    """Factures ECHUE classées avec la décomposition de leur score."""
    factures = factures_calculees(conn)
    historique = _historique_par_client(conn, factures)
    p = parametres_priorisation(conn)
    plus_ancienne = {r[0]: r[1] for r in conn.execute(
        "SELECT facture_id, MIN(date_echeance) FROM v_echeances_calc "
        "WHERE etat = 'ACTIVE' AND retard_jours > 0 GROUP BY facture_id")}
    lignes = []
    for f in factures.values():
        if f["statut"] != "ECHUE":
            continue
        nb_retard, nb_soldees = historique.get(f["client_id"], (0, 0))
        s: ScorePriorite = score(f["retard_jours"], f["solde"],
                                 ratio_retard(nb_retard, nb_soldees), p)
        lignes.append({"facture_id": f["id"], "numero": f["numero"],
                       "client_id": f["client_id"], "retard_jours": f["retard_jours"],
                       "solde": f["solde"], **s.affichable(),
                       "_tri": cle_de_tri(Decimal(s.total), plus_ancienne[f["id"]], f["id"])})
    lignes.sort(key=lambda x: x["_tri"])
    for i, ligne in enumerate(lignes, 1):
        ligne["rang"] = i
        del ligne["_tri"]
    return lignes


def contexte_calcul(conn: sqlite3.Connection) -> str:
    return clock.date_reference(conn).isoformat()
