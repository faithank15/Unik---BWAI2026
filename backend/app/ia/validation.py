"""Validation de la sortie du classifieur (document IA, règles V1 à V8).

Le modèle propose, le code valide : aucune sortie n'a de conséquence avant d'avoir passé ces
règles. Une sortie invalide (V1 à V3) ou à date incohérente (V4, V5) lève `SortieInvalide` ; le
repli est alors AUTRE_INCERTAIN, confiance 0, envoyé en revue humaine. V6 et V7 corrigent la
valeur fautive et posent un drapeau (message en revue).
"""
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

CATEGORIES = ("DEJA_PAYE", "PROMESSE_PAIEMENT", "CONTESTATION", "DEMANDE_ECHEANCIER",
              "DEMANDE_DELAI", "DEMANDE_COPIE_FACTURE", "AUTRE_INCERTAIN")
CATEGORIES_AVEC_DATE = ("PROMESSE_PAIEMENT", "DEMANDE_DELAI")
CHAMPS = {"categorie", "confiance", "copie_demandee", "date_promise", "montant_promis",
          "facture_citee", "justification"}
LONGUEUR_JUSTIFICATION = 200
HORIZON_JOURS = 365


class SortieInvalide(Exception):
    def __init__(self, motif: str, detail: str):
        super().__init__(detail)
        self.motif = motif          # FORMAT_INVALIDE, DATE_INVALIDE ou DATE_INCOHERENTE
        self.detail = detail


@dataclass(frozen=True)
class Resultat:
    categorie: str
    confiance: float
    copie_demandee: bool
    date_promise: date | None
    montant_promis: int | None
    facture_citee: str | None
    justification: str
    drapeaux: tuple[str, ...] = ()
    motif_repli: str | None = None


def repli(motif: str) -> Resultat:
    """Résultat de repli : jamais silencieux, journalisé par l'appelant."""
    return Resultat("AUTRE_INCERTAIN", 0.0, False, None, None, None, "", (), motif)


def _nombre(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def valider(brut: Any, entree: dict) -> Resultat:
    if isinstance(brut, (str, bytes)):
        try:
            brut = json.loads(brut)
        except ValueError as e:
            raise SortieInvalide("FORMAT_INVALIDE", "JSON invalide") from e
    if not isinstance(brut, dict):                                     # V1
        raise SortieInvalide("FORMAT_INVALIDE", "l'objet attendu n'est pas un objet JSON")
    if set(brut) != CHAMPS:
        raise SortieInvalide("FORMAT_INVALIDE", f"champs manquants ou en trop : "
                             f"{sorted(set(brut) ^ CHAMPS)}")
    if brut["categorie"] not in CATEGORIES:                            # V2
        raise SortieInvalide("FORMAT_INVALIDE", "catégorie hors des 7 valeurs")
    if not _nombre(brut["confiance"]) or not 0 <= brut["confiance"] <= 1:   # V3
        raise SortieInvalide("FORMAT_INVALIDE", "confiance hors de [0, 1]")
    if not isinstance(brut["copie_demandee"], bool) or not isinstance(brut["justification"], str):
        raise SortieInvalide("FORMAT_INVALIDE", "type de champ invalide")
    reception = date.fromisoformat(entree["date_reception"][:10])
    d = None
    if brut["date_promise"] is not None:                               # V4
        try:
            if not isinstance(brut["date_promise"], str) or len(brut["date_promise"]) != 10:
                raise ValueError
            d = date.fromisoformat(brut["date_promise"])
        except ValueError as e:
            raise SortieInvalide("DATE_INVALIDE", "date_promise n'est pas une date ISO") from e
        if not reception <= d <= reception + timedelta(days=HORIZON_JOURS):
            raise SortieInvalide("DATE_INVALIDE", "date_promise hors de [réception, +365 j]")
        if brut["categorie"] not in CATEGORIES_AVEC_DATE:              # V5
            raise SortieInvalide("DATE_INCOHERENTE",
                                 "date_promise pour une catégorie qui n'en porte pas")
    drapeaux: list[str] = []
    montant = brut["montant_promis"]                                   # V6
    if montant is not None and (isinstance(montant, bool) or not isinstance(montant, int)
                                or montant <= 0):
        montant = None
        drapeaux.append("MONTANT_INVALIDE")
    facture = brut["facture_citee"]                                    # V7
    if facture is not None and (not isinstance(facture, str)
                                or facture not in entree["factures_ouvertes"]):
        facture = None
        drapeaux.append("REFERENCE_INCONNUE")
    return Resultat(brut["categorie"], float(brut["confiance"]), brut["copie_demandee"], d,
                    montant, facture, brut["justification"][:LONGUEUR_JUSTIFICATION],  # V8
                    tuple(drapeaux))
