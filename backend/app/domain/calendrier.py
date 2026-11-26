"""Jours ouvrés et fériés. Règles pures, sans base ni HTTP.

Un jour est non ouvré s'il s'agit d'un dimanche ou d'un jour férié ; le samedi est ouvré.
"""
from collections.abc import Container, Iterable
from datetime import date, timedelta

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def est_jour_ouvre(d: date, feries: Container[date]) -> bool:
    return d.weekday() != 6 and d not in feries


def prochain_jour_ouvre(d: date, feries: Container[date]) -> date:
    """`d` lui-même s'il est ouvré, sinon le premier jour ouvré qui suit."""
    while not est_jour_ouvre(d, feries):
        d += timedelta(days=1)
    return d


JOURS_PREFERENCES = ("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI")


def indices_jours_evites(noms: str | Iterable[str] | None) -> frozenset[int]:
    """Jours de la semaine (0 = lundi) qu'un client préfère éviter. Accepte la forme stockée
    'MARDI;VENDREDI' ou une liste. Un nom inconnu est ignoré (la saisie est validée en amont)."""
    if not noms:
        return frozenset()
    liste = noms.split(";") if isinstance(noms, str) else list(noms)
    return frozenset(JOURS_PREFERENCES.index(n) for n in liste if n in JOURS_PREFERENCES)


def prochain_jour_permis(d: date, feries: Container[date],
                         evites: Container[int] = ()) -> date:
    """`d` s'il est ouvré et non évité par le client, sinon le premier jour permis qui suit.
    Un jour à éviter se traite comme un jour non ouvré pour ce client (extension IA, 1.4)."""
    while not est_jour_ouvre(d, feries) or d.weekday() in evites:
        d += timedelta(days=1)
    return d


def nom_jour(d: date) -> str:
    return JOURS_FR[d.weekday()]
