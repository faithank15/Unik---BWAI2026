"""Paramètres métier et routes d'administration de démonstration."""
import sqlite3

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import authentifie, exiger, get_conn
from app.errors import Introuvable
from app.journal import utilisateur
from app.security import Utilisateur
from app.services import relances
from app.services.parametres import ecrire_parametre
from app.services.reset import reinitialiser

routeur = APIRouter(prefix="/api", tags=["Paramètres et démonstration"])


def hooks_actifs(request: Request) -> None:
    """Si DEMO_HOOKS_ENABLED est faux, les routes d'administration répondent 404."""
    if not request.app.state.reglages.demo_hooks_enabled:
        raise Introuvable("Ressource introuvable.")


@routeur.get("/parametres", summary="Tous les paramètres métier")
def lister_parametres(_: Utilisateur = Depends(authentifie),
                      conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return {"elements": [dict(r) for r in conn.execute(
        "SELECT cle, valeur, type, description FROM parametres ORDER BY cle")]}


class ParametreEntree(BaseModel):
    valeur: str


@routeur.put("/parametres/{cle}", summary="Modifie un paramètre (journalisé)")
def modifier_parametre(cle: str, corps: ParametreEntree,
                       u: Utilisateur = Depends(exiger("VALIDATEUR")),
                       conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return ecrire_parametre(conn, cle, corps.valeur, utilisateur(u.id))


@routeur.post("/admin/reset", summary="Recharge le jeu de données")
def reset(request: Request, _h: None = Depends(hooks_actifs),
          _: Utilisateur = Depends(exiger("VALIDATEUR"))) -> dict:
    return reinitialiser(request.app.state.reglages)


class DateEntree(BaseModel):
    date: str


@routeur.post("/admin/date-reference", summary="Fixe la date de référence")
def fixer_date(corps: DateEntree, _h: None = Depends(hooks_actifs),
               u: Utilisateur = Depends(exiger("VALIDATEUR")),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return ecrire_parametre(conn, "date_reference", corps.date, utilisateur(u.id))


class AvancerEntree(BaseModel):
    jours: int = Field(ge=1, le=60)
    executer: bool = False


@routeur.post("/admin/avancer", summary="Avance la date de référence (avec exécution facultative)")
def avancer(corps: AvancerEntree, request: Request, _h: None = Depends(hooks_actifs),
            u: Utilisateur = Depends(exiger("VALIDATEUR")),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return relances.avancer(conn, corps.jours, corps.executer, utilisateur(u.id),
                            request.app.state.classeur)
