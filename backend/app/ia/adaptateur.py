"""Adaptateur unique du LLM : délai, réessais, validation stricte, coupe-circuit.

Le back-end ne connaît pas le fournisseur : tout passe par un objet qui sait `classer(entree)`.
Une panne ou une lenteur de l'API n'arrête jamais le système : `Indisponible` met le message en
file « à classer ». Aucune transaction ne doit être ouverte pendant l'appel (voir services).
"""
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from app.domain.redaction import Redaction, RedactionInvalide, valider_redaction
from app.ia.validation import Resultat, SortieInvalide, repli, valider

CONSIGNE = "consigne_v1"
CONSIGNE_REDACTION = "consigne_redaction_v1"
LONGUEUR_MAX_TEXTE = 2000
PAUSES_REESSAI = (1.0, 3.0)
RE_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Indisponible(Exception):
    """L'API du LLM est injoignable, lente, coupée ou simulée indisponible."""


class Classeur(Protocol):
    def classer(self, entree: dict) -> Any: ...


def construire_prompt_redaction(contexte: dict) -> str:
    """Consigne de rédaction versionnée + contexte catégoriel (jamais de nom, de montant ni de
    texte libre d'un client)."""
    consigne = (Path(__file__).parent / "consignes" / f"{CONSIGNE_REDACTION}.md").read_text(
        encoding="utf-8")
    lignes = "\n".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                       for k, v in contexte.items())
    return f"{consigne}\n\nContexte :\n{lignes}"


def nettoyer_texte(texte: str) -> str:
    """Tronque à 2 000 caractères et supprime les caractères de contrôle."""
    return RE_CONTROLE.sub("", texte)[:LONGUEUR_MAX_TEXTE]


def construire_prompt(entree: dict) -> str:
    """Consigne versionnée + message encadré par des balises ; toute occurrence de la balise
    de fermeture dans le texte est neutralisée avant l'envoi."""
    consigne = (Path(__file__).parent / "consignes" / f"{CONSIGNE}.md").read_text(
        encoding="utf-8")
    texte = entree["texte"].replace("</message>", "<\\/message>")
    contexte = (f"canal: {entree['canal']}\ndate_reception: {entree['date_reception']}\n"
                f"jour_semaine: {entree['jour_semaine']}\n"
                f"factures_ouvertes: {', '.join(entree['factures_ouvertes']) or 'aucune'}")
    return f"{consigne}\n\n{contexte}\n\n<message>\n{texte}\n</message>"


class Adaptateur:
    def __init__(self, client: Classeur | None, modele: str = "faux", reessais: int = 2,
                 pause: Callable[[float], None] = time.sleep,
                 horloge: Callable[[], float] = time.monotonic,
                 seuil_echecs: int = 3, duree_coupure: float = 120.0):
        self.client, self.modele, self.reessais = client, modele, reessais
        self._pause, self._horloge = pause, horloge
        self._seuil, self._duree = seuil_echecs, duree_coupure
        self._echecs = 0
        self._coupe_jusqua = 0.0

    @property
    def modele_version(self) -> str:
        return f"{self.modele}@{CONSIGNE}"

    @property
    def version_redaction(self) -> str:
        return f"{self.modele}@{CONSIGNE_REDACTION}"

    @property
    def coupe(self) -> bool:
        return self._coupe_jusqua > self._horloge()

    def classer(self, entree: dict, simulation_indisponible: bool = False) -> Resultat:
        """Retourne un résultat validé (éventuellement de repli) ou lève `Indisponible`."""
        if simulation_indisponible:
            raise Indisponible("Panne du LLM simulée.")
        if self.client is None:
            raise Indisponible("Aucun LLM configuré.")
        if self.coupe:
            raise Indisponible("Coupe-circuit ouvert.")
        erreurs = invalides = 0
        while True:
            try:
                brut = self.client.classer(entree)
            except Exception as e:  # noqa: BLE001 - toute panne du fournisseur
                erreurs += 1
                if erreurs > self.reessais:
                    self._echec()
                    raise Indisponible(f"Échec après {erreurs} tentatives : {e}") from e
                self._pause(PAUSES_REESSAI[min(erreurs - 1, len(PAUSES_REESSAI) - 1)])
                continue
            try:
                res = valider(brut, entree)
            except SortieInvalide as e:
                invalides += 1
                if invalides >= 2:          # une nouvelle tentative, puis repli
                    self._succes()
                    return repli(e.motif)
                continue
            self._succes()
            return res

    def rediger(self, contexte: dict, ton_plafond: str,
                simulation_indisponible: bool = False) -> Redaction:
        """Rédaction validée (W1 à W8), ou `Indisponible` (panne, lenteur, coupe-circuit), ou
        `RedactionInvalide` après une seconde tentative : l'appelant utilise alors le canevas
        fixe de l'étape. Aucune transaction ne doit être ouverte pendant l'appel."""
        if simulation_indisponible:
            raise Indisponible("Panne du LLM simulée.")
        if self.client is None or not hasattr(self.client, "rediger"):
            raise Indisponible("Aucun LLM de rédaction configuré.")
        if self.coupe:
            raise Indisponible("Coupe-circuit ouvert.")
        erreurs = invalides = 0
        while True:
            try:
                brut = self.client.rediger(contexte)
            except Exception as e:  # noqa: BLE001 - toute panne du fournisseur
                erreurs += 1
                if erreurs > self.reessais:
                    self._echec()
                    raise Indisponible(f"Échec après {erreurs} tentatives : {e}") from e
                self._pause(PAUSES_REESSAI[min(erreurs - 1, len(PAUSES_REESSAI) - 1)])
                continue
            try:
                red = valider_redaction(brut, ton_plafond)
            except RedactionInvalide:
                invalides += 1
                if invalides >= 2:          # une nouvelle tentative, puis repli
                    self._succes()
                    raise
                continue
            self._succes()
            return red

    def _echec(self) -> None:
        self._echecs += 1
        if self._echecs >= self._seuil:     # trois échecs de suite : plus d'appel pendant 120 s
            self._coupe_jusqua = self._horloge() + self._duree
            self._echecs = 0

    def _succes(self) -> None:
        self._echecs = 0
