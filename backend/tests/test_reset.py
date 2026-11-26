import sqlite3
import time

import pytest

from app.errors import Validation
from app.services.reset import reinitialiser
from tests.conftest import faire_reglages


def test_reset_cree_base_params_feries_et_comptes(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))
    reinitialiser(r, charger=False)
    c = sqlite3.connect(r.database_path)
    assert c.execute("SELECT valeur FROM parametres WHERE cle='date_reference'"
                     ).fetchone()[0] == "2026-12-15"
    assert c.execute("SELECT COUNT(*) FROM jours_feries").fetchone()[0] == 12
    assert [x[0] for x in c.execute("SELECT nom_utilisateur FROM utilisateurs ORDER BY id")] == \
        ["gestionnaire", "validateur"]
    assert c.execute("SELECT COUNT(*) FROM parametres").fetchone()[0] >= 20
    assert c.execute("SELECT type_evenement FROM journal").fetchall() == [("RESET",)]


def test_reset_deux_fois_donne_des_bases_identiques_hors_horodatages(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))

    def photo():
        reinitialiser(r, charger=False)
        c = sqlite3.connect(r.database_path)
        tables = [x[0] for x in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
            "('sessions','journal','utilisateurs')")]
        out = {t: c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in tables}
        out["journal"] = c.execute("SELECT date_reference, type_evenement FROM journal"
                                   ).fetchall()
        c.close()
        return out
    assert photo() == photo()


def test_reset_repart_d_une_base_vide(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))
    reinitialiser(r, charger=False)
    c = sqlite3.connect(r.database_path)
    c.execute("INSERT INTO jours_feries VALUES ('2031-01-01','x')")
    c.commit()
    c.close()
    reinitialiser(r, charger=False)
    c = sqlite3.connect(r.database_path)
    assert c.execute("SELECT COUNT(*) FROM jours_feries WHERE date='2031-01-01'"
                     ).fetchone()[0] == 0


def test_reset_exige_les_mots_de_passe_de_demo(tmp_path):
    from dataclasses import replace
    r = replace(faire_reglages(str(tmp_path / "x.db")), seed_mdp_validateur="")
    with pytest.raises(Validation):
        reinitialiser(r)


def test_RE01_reset_complet_en_moins_de_10_secondes(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))
    debut = time.monotonic()
    reinitialiser(r)
    assert time.monotonic() - debut < 10


def test_reset_charge_le_jeu_de_donnees(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))
    reinitialiser(r)
    c = sqlite3.connect(r.database_path)
    n = lambda t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    assert (n("clients"), n("factures"), n("echeances"), n("paiements"), n("avoirs")) == \
        (30, 120, 147, 84, 5)
    assert (n("contestations"), n("promesses_paiement"), n("accords_echeancier")) == (6, 6, 6)
    assert n("relances") == 74 and n("envois_simules") == 72  # 2 relances annulées
    assert c.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 1
    # séquences positionnées : le prochain paiement est PAY-0085
    assert c.execute("SELECT valeur FROM sequences WHERE nom = 'PAY'").fetchone()[0] == 84


def test_RE02_deux_resets_complets_identiques_hors_horodatages(tmp_path):
    r = faire_reglages(str(tmp_path / "x.db"))

    def photo():
        reinitialiser(r)
        c = sqlite3.connect(r.database_path)
        tables = [x[0] for x in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
            "('sessions','journal','utilisateurs','envois_simules')")]
        # Colonnes d'horodatage réel (heure de création, de début, de fin) : exclues, elles
        # changent d'une seconde à l'autre ; tout le reste doit être identique.
        horodatages = {"cree_le", "resolu_le", "debut", "fin", "horodatage"}
        out = {}
        for t in tables:
            cols = [x[1] for x in c.execute(f"PRAGMA table_info({t})")
                    if x[1] not in horodatages]
            out[t] = c.execute(f"SELECT {', '.join(cols)} FROM {t} ORDER BY 1,2").fetchall()
        out["journal"] = c.execute("SELECT date_reference, type_evenement, objet_id, avant, "
                                   "apres, details FROM journal ORDER BY id").fetchall()
        c.close()
        return out
    assert photo() == photo()
