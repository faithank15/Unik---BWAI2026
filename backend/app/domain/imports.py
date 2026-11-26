"""Validation des lignes d'import (spécification, section 8.1). Règles pures, sans base."""
import re
from datetime import date

RE_TELEPHONE = re.compile(r"^\+229\d{10}$")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_ENTIER = re.compile(r"^-?\d+$")

CONDITIONS = {"COMPTANT", "15_JOURS", "30_JOURS", "45_JOURS", "60_JOURS", "TRANCHES"}
CANAUX = {"WHATSAPP", "EMAIL"}
STATUTS_ACCORD = {"PROPOSE", "ACCEPTE", "RESPECTE", "ROMPU"}

ENTETES = {
    "clients": ["id", "raison_sociale", "secteur", "ville", "email", "whatsapp", "actif"],
    "preferences_contact": ["client_id", "canal_prefere", "canaux_autorises",
                            "consentement_relance", "interlocuteur"],
    "factures": ["id", "client_id", "numero", "date_emission", "montant_ttc",
                 "conditions_paiement", "taux_penalite_retard", "ref_facture_normalisee",
                 "statut_document"],
    "echeances": ["id", "facture_id", "rang", "date_echeance", "montant_du", "etat",
                  "accord_id"],
    "accords_echeancier": ["id", "facture_id", "date_accord", "statut", "nb_tranches"],
}
OBLIGATOIRES = ("clients", "factures", "echeances")
ENTETES_PAIEMENTS = ["id", "client_id", "date_paiement", "montant", "mode",
                     "reference_externe", "source", "statut", "references_indiquees"]
ENTETES_AVOIRS = ["id", "facture_id", "date", "montant", "motif"]


def lire_date(texte: str) -> date | None:
    """Date ISO AAAA-MM-JJ existante, sinon None."""
    if not RE_DATE.match(texte):
        return None
    try:
        return date.fromisoformat(texte)
    except ValueError:
        return None


def lire_entier(texte: str) -> int | None:
    return int(texte) if RE_ENTIER.match(texte) else None


def vide(valeur: str | None) -> bool:
    return valeur is None or not valeur.strip()


def champs_vides(ligne: dict[str, str], obligatoires: list[str]) -> list[str]:
    return [c for c in obligatoires if vide(ligne.get(c))]


def nettoyer(ligne: dict[str, str]) -> dict[str, str]:
    return {k: (v or "").strip() for k, v in ligne.items()}


def vers_none(texte: str) -> str | None:
    return texte if texte else None
