import sqlite3
import threading

import pytest

from app.clock import date_reference
from app.db import connecter, prochain_id, transaction
from app.journal import journaliser


def test_schema_24_tables_3_vues(db):
    noms = {(r["type"], r["name"]) for r in db.execute(
        "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    tables = [n for t, n in noms if t == "table"]
    vues = [n for t, n in noms if t == "view"]
    assert len(tables) == 24, sorted(tables)     # 23 + redactions (extension IA)
    assert len(vues) == 3


def test_cles_etrangeres_actives_sur_chaque_connexion(reglages):
    for _ in range(2):
        c = connecter(reglages.database_path)
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        c.close()


def test_mode_wal(db):
    assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_date_reference_vient_du_parametre(db, horloge):
    assert str(date_reference(db)) == "2026-12-15"
    horloge("2026-12-20")
    assert str(date_reference(db)) == "2026-12-20"


def test_transaction_valide(db):
    with transaction(db):
        db.execute("INSERT INTO jours_feries VALUES ('2030-01-01', 'test')")
    assert db.execute("SELECT COUNT(*) FROM jours_feries WHERE date='2030-01-01'"
                      ).fetchone()[0] == 1


def test_transaction_annule_en_cas_d_erreur(db):
    with pytest.raises(RuntimeError):
        with transaction(db):
            db.execute("INSERT INTO jours_feries VALUES ('2030-01-02', 'test')")
            raise RuntimeError("boum")
    assert db.execute("SELECT COUNT(*) FROM jours_feries WHERE date='2030-01-02'"
                      ).fetchone()[0] == 0


def test_sequences_identifiants(db):
    with transaction(db):
        a, b, c = prochain_id(db, "CLI"), prochain_id(db, "CLI"), prochain_id(db, "PAY")
    assert (a, b, c) == ("CLI-0001", "CLI-0002", "PAY-0001")


def test_sequence_annulee_avec_la_transaction(db):
    with pytest.raises(RuntimeError):
        with transaction(db):
            prochain_id(db, "CLI")
            raise RuntimeError
    with transaction(db):
        assert prochain_id(db, "CLI") == "CLI-0001"


def test_ecritures_concurrentes_serialisees(reglages):
    """Plusieurs threads, chacun sa connexion : aucune identifiant en double."""
    ids, erreurs = [], []

    def tache():
        try:
            c = connecter(reglages.database_path)
            for _ in range(5):
                with transaction(c):
                    ids.append(prochain_id(c, "REL"))
            c.close()
        except Exception as e:  # noqa: BLE001
            erreurs.append(e)

    threads = [threading.Thread(target=tache) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not erreurs
    assert len(ids) == 30 and len(set(ids)) == 30


def test_J01_journal_refuse_modification_et_suppression(db):
    with transaction(db):
        journaliser(db, "TEST", "OBJ", "1")
    with pytest.raises(sqlite3.DatabaseError, match="ajout seulement"):
        db.execute("UPDATE journal SET type_evenement = 'X'")
    with pytest.raises(sqlite3.DatabaseError, match="ajout seulement"):
        db.execute("DELETE FROM journal")


def test_journal_renseigne_date_reference_et_nettoie_les_secrets(db):
    with transaction(db):
        journaliser(db, "TEST", "OBJ", "1", details={"mot_de_passe": "secret", "texte": "x" * 300})
    ligne = db.execute("SELECT * FROM journal WHERE type_evenement = 'TEST'").fetchone()
    assert ligne["date_reference"] == "2026-12-15"
    assert "secret" not in ligne["details"]
    assert len(ligne["details"]) < 300
