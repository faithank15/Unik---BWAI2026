"""Équivalence : statut et solde des 120 factures et soldes des 147 échéances égaux à la
vérité terrain (statuts_factures.csv, soldes_echeances.csv)."""
import pytest

from app.services import calculs
from tests.verite import lire_csv, signaler

pytestmark = pytest.mark.equivalence


def test_statuts_et_soldes_des_factures(db_chargee):
    calculees = calculs.factures_calculees(db_chargee)
    attendu = lire_csv("verite_terrain/statuts_factures.csv")
    ecarts = []
    for v in attendu:
        f = calculees[v["facture_id"]]
        obtenu = (f["statut"], f["solde"], int(f["partiellement_payee"]))
        voulu = (v["statut"], int(v["solde_facture"]), int(v["partiellement_payee"]))
        if obtenu != voulu:
            ecarts.append(f"{v['facture_id']} : attendu {voulu}, obtenu {obtenu}")
    assert len(attendu) == 120 == len(calculees)
    signaler(ecarts, len(attendu), "statuts et soldes des factures")


def test_soldes_et_retards_des_echeances(db_chargee):
    calculees = {e["id"]: e for e in calculs.echeances_calculees(db_chargee)}
    attendu = lire_csv("verite_terrain/soldes_echeances.csv")
    ecarts = []
    for v in attendu:
        e = calculees[v["echeance_id"]]
        obtenu = (e["affecte"], e["solde"], e["retard_jours"])
        voulu = (int(v["affecte"]), int(v["solde"]), int(v["retard_jours"]))
        if obtenu != voulu:
            ecarts.append(f"{v['echeance_id']} : attendu {voulu}, obtenu {obtenu}")
    assert len(attendu) == len(calculees) == 147
    signaler(ecarts, len(attendu), "soldes et retards des échéances")


def test_repartition_des_statuts(db_chargee):
    from collections import Counter
    c = Counter(f["statut"] for f in calculs.factures_calculees(db_chargee).values())
    assert dict(c) == {"ANNULEE": 3, "SOLDEE": 38, "CONTESTEE": 4,
                       "COUVERTE_PAR_ECHEANCIER": 3, "NON_ECHUE": 25, "ECHUE": 47}
