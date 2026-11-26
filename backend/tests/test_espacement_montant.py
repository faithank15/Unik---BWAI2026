"""Espacement selon le montant (extension IA, section 3.1) : règle pure et effet sur le moteur.

Coefficients (en dixièmes) : x1 jusqu'à 100 000 FCFA, x1,5 de 100 001 à 500 000, x2 au-delà ;
l'espacement standard (2 jours, 5 en rattrapage) est multiplié puis arrondi au jour supérieur.
Les attendus sont posés à la main, indépendamment du code.
"""
import pytest

from app.domain import relances as dom
from tests.aides_relances import changer_date, envoyer, planifier, relances

P = dom.ParamsRelances(jours={"P": -3, "R1": 1, "R2": 7, "R3": 15})


@pytest.mark.parametrize("total, rattrapage, attendu", [
    (0, False, 2), (100_000, False, 2), (100_001, False, 3), (500_000, False, 3),
    (500_001, False, 4), (1_200_000, False, 4),
    (0, True, 5), (100_000, True, 5), (100_001, True, 8), (500_000, True, 8),
    (500_001, True, 10), (1_200_000, True, 10),
])
def test_ecart_minimal_par_tranche_aux_bornes(total, rattrapage, attendu):
    assert dom.ecart_minimal(rattrapage, P, total) == attendu


def test_sans_montant_l_espacement_reste_le_standard():
    assert dom.ecart_minimal(False, P) == 2 and dom.ecart_minimal(True, P) == 5


def test_l_arrondi_se_fait_au_jour_superieur():
    assert 2 * 15 / 10 == 3 and 5 * 15 / 10 == 7.5      # 7,5 jours -> 8
    assert dom.ecart_minimal(True, P, 300_000) == 8


def test_les_coefficients_sont_des_parametres():
    p = dom.ParamsRelances(jours=P.jours, coef_espacement_moyen=20, coef_espacement_gros=30,
                           seuil_espacement_moyen=50_000)
    assert dom.ecart_minimal(False, p, 50_000) == 2
    assert dom.ecart_minimal(False, p, 50_001) == 4
    assert dom.ecart_minimal(False, p, 500_001) == 6


def test_le_delai_d_escalade_ne_depend_pas_du_montant():
    from datetime import date
    assert dom.escalade_due(date(2026, 12, 1), date(2026, 12, 6), P)
    assert not dom.escalade_due(date(2026, 12, 1), date(2026, 12, 5), P)


def test_les_parametres_sont_lisibles_et_modifiables(api, gest, valid):
    elements = api.get("/api/parametres", headers=gest).json()["elements"]
    lus = {p["cle"]: p["valeur"] for p in elements}
    assert (lus["seuil_espacement_moyen"], lus["coef_espacement_moyen_dixiemes"],
            lus["coef_espacement_gros_dixiemes"]) == ("100000", "15", "20")
    r = api.put("/api/parametres/coef_espacement_gros_dixiemes", headers=valid,
                json={"valeur": "30"})
    assert r.status_code == 200
    assert api.put("/api/parametres/coef_espacement_gros_dixiemes", headers=gest,
                   json={"valeur": "30"}).status_code == 403


def test_un_gros_montant_est_differe_de_quatre_jours_et_journalise(api, gest, valid):
    """CLI-0019 : total 600 000 FCFA, dernier envoi le 12/12 : 3 jours < 4 requis le 15/12."""
    planifier(api, gest)
    assert [x for x in relances(api, gest, client_id="CLI-0019", date="2026-12-15")
            if x["statut"] != "SAUTEE"] == []
    evts = [e for e in api.get(
        "/api/journal?type_evenement=RELANCE_REPORTEE_ESPACEMENT&limite=200",
        headers=gest).json()["elements"] if e["objet_id"] == "CLI-0019"]
    d = evts[-1]["details"].replace(" ", "")
    assert '"ecart_minimal":4' in d and '"total":600000' in d
    assert '"prochaine_date_possible":"2026-12-16"' in d


def test_le_coefficient_se_lit_dans_le_total_courant_a_l_envoi(api, gest, valid):
    """Revérification à l'envoi : le coefficient suit le solde courant, jamais un total figé."""
    planifier(api, gest)
    envoyer(api, gest)
    changer_date(api, valid, "2026-12-16")
    planifier(api, gest)
    assert not [x for x in relances(api, gest, client_id="CLI-0030", date="2026-12-16")
                if x["statut"] == "ENVOYEE_SIM"]


def test_le_tableau_de_bord_affiche_la_prochaine_relance_et_la_raison(api, gest):
    """Section 3.3 : un gros montant poussé plus loin reste visible, avec sa raison."""
    planifier(api, gest)
    reportees = api.get("/api/tableau-de-bord", headers=gest).json()["relances_reportees"]
    ligne = next(r for r in reportees if r["client_id"] == "CLI-0019")
    assert ligne["raison"] == "ESPACEMENT_MINIMAL" and ligne["total"] == 600_000
    assert ligne["dernier_envoi"] == "2026-12-12" and ligne["ecart_minimal_jours"] == 4
    assert ligne["prochaine_date_possible"] == "2026-12-16"
