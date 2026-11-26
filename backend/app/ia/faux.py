"""Faux LLM pour les tests : sorties prédéfinies par message_id, pannes et sorties malformées."""
from collections.abc import Callable
from typing import Any

from app.ia.adaptateur import Indisponible


class FauxLLM:
    def __init__(self, reponses: dict[str, Any] | None = None, defaut: Any = None):
        self.reponses = dict(reponses or {})
        self.defaut = defaut
        self.appels: list[dict] = []
        self.avant_appel: Callable[[dict], None] | None = None

    def programmer(self, message_id: str, reponse: Any) -> None:
        self.reponses[message_id] = reponse

    def classer(self, entree: dict) -> Any:
        self.appels.append(entree)
        if self.avant_appel:
            self.avant_appel(entree)
        rep = self.reponses.get(entree["message_id"], self.defaut)
        if rep is None:
            raise Indisponible("Pas de réponse programmée.")
        if isinstance(rep, Exception):
            raise rep
        if isinstance(rep, list):                  # suites de réponses (réessais)
            rep = rep.pop(0) if len(rep) > 1 else rep[0]
            if isinstance(rep, Exception):
                raise rep
        return rep


def sortie(categorie: str, confiance: float = 0.95, **kw: Any) -> dict:
    """Sortie valide du classifieur, pour les tests."""
    base = {"categorie": categorie, "confiance": confiance, "copie_demandee": False,
            "date_promise": None, "montant_promis": None, "facture_citee": None,
            "justification": "test"}
    base.update(kw)
    return base
