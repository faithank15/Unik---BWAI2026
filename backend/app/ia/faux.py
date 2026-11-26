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


class FauxRedacteur(FauxLLM):
    """Faux LLM qui sait aussi rédiger : `programmer_redaction(cle, sortie)` par cas|ton|canal."""

    def __init__(self, redaction: Any = None, **kw: Any):
        super().__init__(**kw)
        self.redaction = redaction
        self.redactions: dict[str, Any] = {}
        self.contextes: list[dict] = []

    def programmer_redaction(self, cas: str, reponse: Any) -> None:
        self.redactions[cas] = reponse

    def rediger(self, contexte: dict) -> Any:
        self.contextes.append(contexte)
        rep = self.redactions.get(contexte["cas"], self.redaction)
        if rep is None:
            raise Indisponible("Pas de rédaction programmée.")
        if isinstance(rep, list):
            rep = rep.pop(0) if len(rep) > 1 else rep[0]
        if isinstance(rep, Exception):
            raise rep
        return rep


def redaction_valide(**kw: Any) -> dict:
    """Sortie valide du rédacteur, pour les tests (variables seulement, aucun chiffre)."""
    base = {"objet": "Rappel de règlement : facture {numero_facture}",
            "introduction": "Sauf erreur de notre part, la facture {numero_facture} échue le "
                            "{date_echeance} reste à régler. Nous supposons un simple oubli.",
            "conclusion": "Pourriez-vous procéder au règlement de {solde} d'ici le "
                          "{date_limite} ?",
            "ton_applique": "COURTOIS"}
    base.update(kw)
    return base


def sortie(categorie: str, confiance: float = 0.95, **kw: Any) -> dict:
    """Sortie valide du classifieur, pour les tests."""
    base = {"categorie": categorie, "confiance": confiance, "copie_demandee": False,
            "date_promise": None, "montant_promis": None, "facture_citee": None,
            "justification": "test"}
    base.update(kw)
    return base
