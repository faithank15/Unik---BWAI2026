"""Pagination, tri et filtres identiques sur toutes les listes (spécification, section 4)."""
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import Query

from app.errors import Validation


class Page:
    """Paramètres `limite` (50 par défaut, 200 au maximum), `decalage` et `tri`."""

    def __init__(self, limite: int = Query(50, ge=1, le=200), decalage: int = Query(0, ge=0),
                 tri: str | None = Query(None, description="Champ, préfixé de - si décroissant")):
        self.limite, self.decalage, self.tri = limite, decalage, tri


def _cle(valeur: Any) -> Any:
    """Les nombres sérialisés en texte (scores) se trient comme des nombres."""
    if isinstance(valeur, str):
        try:
            return Decimal(valeur)
        except InvalidOperation:
            return valeur
    return valeur


def paginer(elements: list[dict[str, Any]], page: Page, champs_tri: set[str]) -> dict:
    if page.tri:
        champ = page.tri.lstrip("-")
        if champ not in champs_tri:
            raise Validation(f"Tri impossible sur « {champ} ».",
                             {"champs_autorises": sorted(champs_tri)})
        elements = sorted(elements, key=lambda e: (e.get(champ) is None, _cle(e.get(champ))),
                          reverse=page.tri.startswith("-"))
    total = len(elements)
    return {"total": total, "elements": elements[page.decalage:page.decalage + page.limite]}
