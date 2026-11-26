"""Journal en ajout seulement. Chaque événement s'écrit dans la même transaction que
l'opération qu'il décrit. Jamais de mot de passe, de jeton ni de clé d'API ; le texte d'un
message client est tronqué à 200 caractères."""
import contextvars
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from app import clock

correlation_courante: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None)

CLES_SECRETES = {"mot_de_passe", "mot_de_passe_hash", "jeton", "token", "token_hash",
                 "llm_api_key", "api_key", "authorization"}
LONGUEUR_MAX_TEXTE = 200


@dataclass(frozen=True)
class Acteur:
    type: str          # SYSTEME, IA ou UTILISATEUR
    id: str | None = None


SYSTEME = Acteur("SYSTEME")
IA = Acteur("IA")


def utilisateur(id_: str) -> Acteur:
    return Acteur("UTILISATEUR", id_)


def _nettoyer(valeur: Any) -> Any:
    if isinstance(valeur, dict):
        return {k: ("***" if k.lower() in CLES_SECRETES else _nettoyer(v))
                for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_nettoyer(v) for v in valeur]
    if isinstance(valeur, str) and len(valeur) > LONGUEUR_MAX_TEXTE:
        return valeur[:LONGUEUR_MAX_TEXTE] + "…"
    return valeur


def _json(valeur: Any) -> str | None:
    if valeur is None:
        return None
    return json.dumps(_nettoyer(valeur), ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, default=str)


def journaliser(conn: sqlite3.Connection, type_evenement: str, objet_type: str | None = None,
                objet_id: str | None = None, avant: Any = None, apres: Any = None,
                details: Any = None, acteur: Acteur = SYSTEME) -> int:
    ref = conn.execute("SELECT valeur FROM parametres WHERE cle = 'date_reference'").fetchone()
    cur = conn.execute(
        "INSERT INTO journal(horodatage, date_reference, acteur_type, acteur_id, "
        "type_evenement, objet_type, objet_id, avant, apres, details, correlation_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (clock.maintenant(), ref[0] if ref else "", acteur.type, acteur.id, type_evenement,
         objet_type, objet_id, _json(avant), _json(apres), _json(details),
         correlation_courante.get()))
    return int(cur.lastrowid)


# Catalogue des événements (spécification, section 11). Chaque opération sensible en écrit un,
# dans la même transaction. `PREFERENCES_MODIFIEES` est un ajout de l'implémentation.
CATALOGUE = frozenset({
    "IMPORT_TERMINE", "IMPORT_DEJA_FAIT",
    "PAIEMENT_ENREGISTRE", "PAIEMENT_REJOUE", "PAIEMENT_AFFECTE", "PAIEMENT_NON_AFFECTE",
    "REFERENCE_INTROUVABLE", "AVOIR_ENREGISTRE",
    "RELANCE_PLANIFIEE", "RELANCE_SAUTEE", "RELANCE_SUSPENDUE", "RELANCE_REPORTEE_ESPACEMENT",
    "RELANCE_EN_ATTENTE_VALIDATION", "RELANCE_VALIDEE", "RELANCE_REJETEE",
    "RELANCE_ENVOYEE_SIM", "RELANCE_ANNULEE", "LIGNE_RETIREE", "ESCALADE_CREEE",
    "JOUR_NON_OUVRE",
    "MESSAGE_RECU", "MESSAGE_A_CLASSER", "MESSAGE_CLASSE", "CLASSIFICATION_REPLI",
    "MESSAGE_VALIDE",
    "PROMESSE_CREEE", "PROMESSE_TENUE", "PROMESSE_NON_TENUE", "PROMESSE_ANNULEE",
    "CONTESTATION_OUVERTE", "CONTESTATION_CLOTUREE",
    "ACCORD_PROPOSE", "ACCORD_ACCEPTE", "ACCORD_REFUSE", "ACCORD_RESPECTE",
    "REVUE_CREEE", "REVUE_RESOLUE",
    "PARAMETRE_MODIFIE", "DATE_REFERENCE_MODIFIEE", "RESET", "CONNEXION", "CONNEXION_ECHEC",
    "DECONNEXION", "ACCES_REFUSE",
})
