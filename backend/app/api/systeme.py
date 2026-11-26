"""Santé, contexte, authentification."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app import clock, security
from app.api.deps import authentifie, get_conn, get_jeton
from app.domain.calendrier import est_jour_ouvre, nom_jour
from app.parametres import lire_booleen
from app.security import Utilisateur

routeur = APIRouter(prefix="/api", tags=["Système"])

VERSION = "0.1.0"


class UtilisateurSortie(BaseModel):
    id: str
    nom_utilisateur: str | None = None
    nom_affiche: str
    role: str


class ConnexionEntree(BaseModel):
    nom_utilisateur: str = Field(min_length=1, max_length=100)
    mot_de_passe: str = Field(min_length=1, max_length=200)


class ConnexionSortie(BaseModel):
    jeton: str
    expire_le: str
    utilisateur: UtilisateurSortie


def jours_feries(conn: sqlite3.Connection) -> set[date]:
    return {date.fromisoformat(r[0]) for r in conn.execute("SELECT date FROM jours_feries")}


@routeur.get("/sante", summary="État du service")
def sante(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    conn.execute("SELECT 1").fetchone()
    reglages = request.app.state.reglages
    try:
        simulation = lire_booleen(conn, "simulation_llm_indisponible")
    except Exception:  # base non initialisée
        simulation = False
    return {
        "statut": "ok",
        "version": VERSION,
        "base_de_donnees": "ok",
        "llm": {"configure": reglages.llm_configure, "simulation_indisponible": simulation,
                "disponible": reglages.llm_configure and not simulation},
    }


@routeur.get("/contexte", summary="Date de référence et mode démonstration")
def contexte(request: Request, _: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    d = clock.date_reference(conn)
    return {
        "date_reference": d.isoformat(),
        "jour_semaine": nom_jour(d),
        "jour_ouvre": est_jour_ouvre(d, jours_feries(conn)),
        "mode_demonstration": request.app.state.reglages.demo_hooks_enabled,
    }


@routeur.post("/auth/login", response_model=ConnexionSortie, summary="Connexion")
def login(corps: ConnexionEntree, request: Request,
          conn: sqlite3.Connection = Depends(get_conn)) -> ConnexionSortie:
    jeton, expire, u = security.connexion(
        conn, corps.nom_utilisateur, corps.mot_de_passe,
        request.app.state.reglages.session_ttl_heures)
    return ConnexionSortie(jeton=jeton, expire_le=expire, utilisateur=UtilisateurSortie(
        id=u.id, nom_affiche=u.nom_affiche, role=u.role))


@routeur.post("/auth/logout", summary="Révoque le jeton courant")
def logout(request: Request, u: Utilisateur = Depends(authentifie),
           conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    security.deconnexion(conn, get_jeton(request) or "", u)
    return {"statut": "deconnecte"}


@routeur.get("/auth/moi", response_model=UtilisateurSortie, summary="Utilisateur courant")
def moi(u: Utilisateur = Depends(authentifie)) -> UtilisateurSortie:
    return UtilisateurSortie(id=u.id, nom_utilisateur=u.nom_utilisateur,
                             nom_affiche=u.nom_affiche, role=u.role)
