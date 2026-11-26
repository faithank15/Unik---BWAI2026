"""Équivalence : les affectations calculées au chargement égalent affectations_attendues.csv
(paiements et avoirs, dont les 6 paiements sans référence affectés par ancienneté)."""
import pytest

from tests.verite import lire_csv, signaler

pytestmark = pytest.mark.equivalence


def test_affectations_calculees_au_chargement(db_chargee):
    obtenu = sorted((r["src"], r["echeance_id"], r["montant_affecte"], r["mode"])
                    for r in db_chargee.execute(
        "SELECT COALESCE(paiement_id, avoir_id) AS src, echeance_id, montant_affecte, mode "
        "FROM affectations"))
    attendu = sorted((a["paiement_id"], a["echeance_id"], int(a["montant_affecte"]), a["mode"])
                     for a in lire_csv("verite_terrain/affectations_attendues.csv"))
    manquantes = [f"manquante : {x}" for x in sorted(set(attendu) - set(obtenu))]
    en_trop = [f"en trop : {x}" for x in sorted(set(obtenu) - set(attendu))]
    signaler(manquantes + en_trop, len(attendu), "affectations")
    assert len(obtenu) == len(attendu) == 92


def test_aucune_echeance_sur_affectee(db_chargee):
    mauvaises = db_chargee.execute("SELECT echeance_id FROM v_echeances_calc WHERE solde < 0"
                                   ).fetchall()
    assert mauvaises == []


def test_paiements_non_identifiables_non_affectes_et_en_revue(db_chargee):
    ambigus = [r[0] for r in db_chargee.execute(
        "SELECT id FROM paiements WHERE client_id IS NULL ORDER BY id")]
    assert len(ambigus) == 2
    for pid in ambigus:
        assert db_chargee.execute("SELECT COUNT(*) FROM affectations WHERE paiement_id = ?",
                                  (pid,)).fetchone()[0] == 0
        revue = db_chargee.execute(
            "SELECT type, statut FROM file_revue WHERE objet_id = ?", (pid,)).fetchone()
        assert (revue["type"], revue["statut"]) == ("PAIEMENT_AMBIGU", "OUVERTE")
