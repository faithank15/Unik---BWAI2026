"""Équivalence : classement et scores égaux à priorisation.csv."""
import pytest

from app.services import calculs
from tests.verite import lire_csv, signaler

pytestmark = pytest.mark.equivalence


def test_classement_et_scores(db_chargee):
    obtenu = calculs.priorisation(db_chargee)
    attendu = lire_csv("verite_terrain/priorisation.csv")
    assert len(obtenu) == len(attendu) == 47
    ecarts = []
    for v, p in zip(attendu, obtenu, strict=True):
        voulu = (int(v["rang"]), v["facture_id"], int(v["retard_jours"]), int(v["solde"]),
                 v["points_anciennete"], v["points_solde"], v["points_historique"], v["score"])
        recu = (p["rang"], p["facture_id"], p["retard_jours"], p["solde"],
                p["points_anciennete"], p["points_solde"], p["points_historique"], p["score"])
        if voulu != recu:
            ecarts.append(f"rang {v['rang']} : attendu {voulu}, obtenu {recu}")
    signaler(ecarts, len(attendu), "priorisation")


def test_scores_decroissants_et_bornes(db_chargee):
    scores = [float(p["score"]) for p in calculs.priorisation(db_chargee)]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
