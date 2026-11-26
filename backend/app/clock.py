"""Seul module autorisé à lire l'horloge du système.

La date métier (retards, étapes de relance, promesses, jours ouvrés) vient du paramètre
`date_reference` de la base ; l'heure technique ne sert qu'au journal et aux traces.
"""
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

FUSEAU = timezone(timedelta(hours=1))  # +01:00 (Bénin)


def maintenant() -> str:
    """Horodatage technique ISO 8601 avec décalage +01:00."""
    return datetime.now(FUSEAU).isoformat(timespec="seconds")


def maintenant_dt() -> datetime:
    return datetime.now(FUSEAU)


def instant() -> float:
    """Temps monotone, pour les compteurs en mémoire (limitation de connexions)."""
    return time.monotonic()


def date_reference(conn: sqlite3.Connection) -> date:
    """Date métier du système, lue dans `parametres`."""
    ligne = conn.execute("SELECT valeur FROM parametres WHERE cle = 'date_reference'").fetchone()
    if ligne is None:
        raise RuntimeError("Le paramètre date_reference est absent : réinitialiser la base.")
    return date.fromisoformat(ligne[0])
