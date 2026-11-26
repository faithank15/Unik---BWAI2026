"""Jours ouvrés et fériés. Règles pures, sans base ni HTTP.

Un jour est non ouvré s'il s'agit d'un dimanche ou d'un jour férié ; le samedi est ouvré.
"""
from collections.abc import Container
from datetime import date, timedelta

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def est_jour_ouvre(d: date, feries: Container[date]) -> bool:
    return d.weekday() != 6 and d not in feries


def prochain_jour_ouvre(d: date, feries: Container[date]) -> date:
    """`d` lui-même s'il est ouvré, sinon le premier jour ouvré qui suit."""
    while not est_jour_ouvre(d, feries):
        d += timedelta(days=1)
    return d


def nom_jour(d: date) -> str:
    return JOURS_FR[d.weekday()]
