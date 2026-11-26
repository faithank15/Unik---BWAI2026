"""Tests unitaires des règles pures : statuts (T-C), affectation (T-A), priorisation (T-P)."""
from decimal import Decimal

import pytest

from app.domain.affectation import Cible, repartir, trier
from app.domain.priorisation import ParametresPriorisation, ratio_retard, score
from app.domain.soldes import EntreeStatut, evaluer_statut, partiellement_payee

P = ParametresPriorisation()


def statut(**kw):
    base = dict(statut_document="VALIDEE", solde=100, contestation_ouverte=False,
                accord_accepte=False, retard_max=0)
    return evaluer_statut(EntreeStatut(**{**base, **kw}))[0]


def test_C01_non_echue():
    assert statut() == "NON_ECHUE"


def test_C02_echue_un_jour():
    assert statut(retard_max=1) == "ECHUE"


def test_C05_solde_nul_est_soldee():
    assert statut(solde=0) == "SOLDEE"


def test_C08_annulee_l_emporte_sur_contestee():
    assert statut(statut_document="ANNULEE", contestation_ouverte=True) == "ANNULEE"


def test_C09_soldee_l_emporte_sur_contestee():
    assert statut(solde=0, contestation_ouverte=True) == "SOLDEE"


def test_C10_contestee_l_emporte_sur_echeancier():
    assert statut(contestation_ouverte=True, accord_accepte=True) == "CONTESTEE"


def test_C11_echeancier_l_emporte_sur_echue_seulement_sans_tranche_manquee():
    assert statut(accord_accepte=True, retard_max=0) == "COUVERTE_PAR_ECHEANCIER"
    assert statut(accord_accepte=True, retard_max=6) == "ECHUE"


@pytest.mark.parametrize("fort,faible,kw_fort,kw_faible", [
    ("ANNULEE", "SOLDEE", dict(statut_document="ANNULEE"), dict(solde=0)),
    ("SOLDEE", "CONTESTEE", dict(solde=0), dict(contestation_ouverte=True)),
    ("CONTESTEE", "COUVERTE_PAR_ECHEANCIER", dict(contestation_ouverte=True),
     dict(accord_accepte=True)),
    ("ECHUE", "NON_ECHUE", dict(retard_max=3), dict()),
])
def test_ordre_de_priorite_des_statuts_par_paires(fort, faible, kw_fort, kw_faible):
    assert statut(**kw_fort) == fort
    assert statut(**kw_faible) == faible
    assert statut(**kw_fort, **kw_faible) == fort


def test_regles_ecartees_listent_les_motifs():
    s, ecartees = evaluer_statut(EntreeStatut("VALIDEE", 240000, False, False, 5))
    assert s == "ECHUE"
    assert [e["regle"] for e in ecartees] == ["ANNULEE", "SOLDEE", "CONTESTEE",
                                              "COUVERTE_PAR_ECHEANCIER"]
    assert all(e["motif"] for e in ecartees)


def test_partiellement_payee():
    assert partiellement_payee(50, 50)
    assert not partiellement_payee(0, 100)
    assert not partiellement_payee(100, 0)


# ---- affectation ---------------------------------------------------------------------
def cibles(*soldes):
    return [Cible(f"ECH-{i}", f"2026-12-{10 + i}", s) for i, s in enumerate(soldes, 1)]


def test_A03_reparti_dans_l_ordre_avec_reliquat_reporte():
    rep, reste = repartir(250, cibles(100, 100, 100))
    assert rep == [("ECH-1", 100), ("ECH-2", 100), ("ECH-3", 50)] and reste == 0


def test_A05_excedent_non_affecte_jamais_de_solde_negatif():
    rep, reste = repartir(500, cibles(100, 100))
    assert sum(m for _, m in rep) == 200 and reste == 300


def test_montant_nul_n_ecrit_rien():
    assert repartir(0, cibles(100)) == ([], 0)


def test_jamais_plus_que_le_solde():
    rep, _ = repartir(1000, cibles(30))
    assert rep == [("ECH-1", 30)]


def test_tri_par_date_puis_identifiant():
    c = [Cible("ECH-9", "2026-12-01", 1), Cible("ECH-2", "2026-12-01", 1),
         Cible("ECH-1", "2026-12-05", 1)]
    assert [x.echeance_id for x in trier(c)] == ["ECH-2", "ECH-9", "ECH-1"]


# ---- priorisation --------------------------------------------------------------------
def test_P01():
    s = score(15, 500_000, None, P)
    assert (s.anciennete, s.montant, s.historique, s.total) == (
        Decimal("20"), Decimal("17.5"), Decimal("12.5"), Decimal("50.00"))


def test_P02_retard_plafonne():
    assert score(45, 500_000, None, P).total == Decimal("70.00")


def test_P03_montant_plafonne():
    assert score(15, 2_000_000, None, P).total == Decimal("67.50")


def test_exemple_de_la_specification():
    s = score(5, 240_000, ratio_retard(1, 4), P)
    assert s.affichable() == {"points_anciennete": "6.67", "points_solde": "8.40",
                              "points_historique": "6.25", "score": "21.32"}


def test_P06_composantes_exactes_sans_arrondi_intermediaire():
    s = score(3, 200_000, None, ParametresPriorisation())
    assert s.anciennete == Decimal("4") and s.montant == Decimal("7")
    assert s.total == Decimal("23.50")


def test_arrondi_demi_vers_le_haut_explicite():
    p = ParametresPriorisation(plafond_retard_jours=1600, plafond_solde=1_000_000,
                               poids_anciennete=40, poids_historique=25)
    # 1/1600 * 40 = 0.025 exactement -> 0.03 (ROUND_HALF_UP), pas 0.02 (arrondi bancaire)
    assert score(1, 0, Decimal(0), p).total == Decimal("0.03")


def test_historique_ratio():
    assert ratio_retard(0, 0) is None
    assert ratio_retard(1, 4) == Decimal("0.25")
    assert score(0, 0, Decimal(1), P).historique == Decimal(25)
