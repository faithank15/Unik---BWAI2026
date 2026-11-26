"""Exceptions métier et format d'erreur de l'API (spécification, section 4)."""
from typing import Any


class ErreurMetier(Exception):
    http = 500
    code = "ERREUR_INTERNE"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class Validation(ErreurMetier):
    http, code = 400, "VALIDATION"


class NonAuthentifie(ErreurMetier):
    http, code = 401, "NON_AUTHENTIFIE"


class AccesRefuse(ErreurMetier):
    http, code = 403, "ACCES_REFUSE"


class Introuvable(ErreurMetier):
    http, code = 404, "INTROUVABLE"


class Conflit(ErreurMetier):
    http, code = 409, "CONFLIT"


class RegleMetier(ErreurMetier):
    http, code = 422, "REGLE_METIER"

    def __init__(self, regle: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, {"regle": regle, **(details or {})})


class TropDeTentatives(ErreurMetier):
    http, code = 429, "TROP_DE_TENTATIVES"


def corps_erreur(code: str, message: str, details: dict[str, Any] | None,
                 correlation_id: str | None) -> dict[str, Any]:
    erreur: dict[str, Any] = {"code": code, "message": message, "details": details or {}}
    if correlation_id:
        erreur["correlation_id"] = correlation_id
    return {"erreur": erreur}


class FichierTropGros(ErreurMetier):
    http, code = 413, "FICHIER_TROP_GROS"
