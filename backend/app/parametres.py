"""Paramètres métier par défaut (spécification, section 3) et accès typé."""
import sqlite3
from decimal import Decimal

# (clé, valeur par défaut, type, description)
DEFAUTS: list[tuple[str, str, str, str]] = [
    ("date_reference", "2026-12-15", "DATE", "Date métier du système"),
    ("seuil_gros_montant", "500000", "ENTIER",
     "Validation humaine au-dessus de ce solde cumulé par message"),
    ("rappel_preventif_actif", "true", "BOOLEEN", "Active l'étape P"),
    ("jours_p", "-3", "ENTIER", "Décalage de l'étape P par rapport à l'échéance"),
    ("jours_r1", "1", "ENTIER", "Décalage de l'étape R1"),
    ("jours_r2", "7", "ENTIER", "Décalage de l'étape R2"),
    ("jours_r3", "15", "ENTIER", "Décalage de l'étape R3"),
    ("espacement_normal_jours", "2", "ENTIER",
     "Écart minimal entre deux messages au même client et canal"),
    ("espacement_rattrapage_jours", "5", "ENTIER", "Écart minimal en rattrapage"),
    ("delai_escalade_jours", "5", "ENTIER", "Délai entre R3 envoyée et escalade"),
    ("marge_promesse_jours", "2", "ENTIER", "Marge après la date promise"),
    ("plafond_promesse_jours", "30", "ENTIER",
     "Au-delà, la promesse part en revue"),
    ("seuil_confiance_sensible", "0.60", "DECIMAL", "CONTESTATION et DEJA_PAYE"),
    ("seuil_confiance_prudent", "0.85", "DECIMAL", "PROMESSE_PAIEMENT et DEMANDE_DELAI"),
    ("plafond_retard_jours", "30", "ENTIER", "Plafond de la priorisation (ancienneté)"),
    ("plafond_solde", "1000000", "ENTIER", "Plafond de la priorisation (solde)"),
    ("poids_anciennete", "40", "ENTIER", "Pondération de l'ancienneté"),
    ("poids_solde", "35", "ENTIER", "Pondération du solde"),
    ("poids_historique", "25", "ENTIER", "Pondération de l'historique"),
    ("historique_neutre_points", "12.5", "DECIMAL",
     "Points d'historique d'un client sans facture soldée"),
    ("simulation_llm_indisponible", "false", "BOOLEEN",
     "Simule une panne du LLM (scénario S23)"),
    ("simulation_interruption_apres", "", "ENTIER",
     "Interrompt un lot après N éléments (scénario S19)"),
    ("nom_entreprise_emettrice", "Entreprise Démo", "TEXTE",
     "Nom de l'entreprise dans les messages types"),
]


def lire_texte(conn: sqlite3.Connection, cle: str) -> str:
    ligne = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    if ligne is None:
        raise KeyError(cle)
    return ligne[0]


def lire_entier(conn: sqlite3.Connection, cle: str) -> int:
    return int(lire_texte(conn, cle))


def lire_decimal(conn: sqlite3.Connection, cle: str) -> Decimal:
    """Les décimaux de la configuration se lisent en Decimal, jamais en flottant."""
    return Decimal(lire_texte(conn, cle))


def lire_booleen(conn: sqlite3.Connection, cle: str) -> bool:
    return lire_texte(conn, cle).lower() == "true"
