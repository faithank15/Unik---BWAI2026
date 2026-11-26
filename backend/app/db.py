"""Connexions SQLite, transactions explicites et séquences d'identifiants.

Une connexion par requête ; `foreign_keys` est réactivé à l'ouverture de chaque connexion
car SQLite ne le conserve pas. Les transactions d'écriture sont `BEGIN IMMEDIATE` : le verrou
d'écriture de SQLite sérialise les traitements concurrents.
"""
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BUSY_TIMEOUT_MS = 5000
ATTENTE_MAX_S = 5.0


def connecter(chemin: str) -> sqlite3.Connection:
    conn = sqlite3.connect(chemin, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Ouvre `BEGIN IMMEDIATE`, valide ou annule, et réessaie tant que la base est occupée
    (dans la limite du délai d'attente). Les transactions ne s'imbriquent jamais."""
    debut = time.monotonic()
    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as e:
            occupee = "locked" in str(e).lower() or "busy" in str(e).lower()
            if not occupee or time.monotonic() - debut > ATTENTE_MAX_S:
                raise
            time.sleep(0.02)
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def prochain_id(conn: sqlite3.Connection, prefixe: str) -> str:
    """Identifiant `PREFIXE-NNNN` tiré de la table `sequences`. À appeler dans la transaction
    de l'opération qui crée l'objet."""
    conn.execute("INSERT OR IGNORE INTO sequences(nom, valeur) VALUES (?, 0)", (prefixe,))
    conn.execute("UPDATE sequences SET valeur = valeur + 1 WHERE nom = ?", (prefixe,))
    n = conn.execute("SELECT valeur FROM sequences WHERE nom = ?", (prefixe,)).fetchone()[0]
    return f"{prefixe}-{n:04d}"


def appliquer_schema(conn: sqlite3.Connection) -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)


def positionner_sequence(conn: sqlite3.Connection, prefixe: str, table: str,
                         colonne: str = "id") -> None:
    """Place la séquence du préfixe au plus grand numéro existant (après un chargement)."""
    maxi = 0
    for (ident,) in conn.execute(f"SELECT {colonne} FROM {table} WHERE {colonne} LIKE ?",
                                 (f"{prefixe}-%",)):
        suffixe = ident[len(prefixe) + 1:]
        if suffixe.isdigit():
            maxi = max(maxi, int(suffixe))
    conn.execute("INSERT OR REPLACE INTO sequences(nom, valeur) VALUES (?, ?)", (prefixe, maxi))
