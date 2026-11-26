"""Dépendances FastAPI : connexion par requête, utilisateur courant, rôle minimal."""
import sqlite3
from collections.abc import Callable, Iterator

from fastapi import Depends, Request

from app import security
from app.db import connecter
from app.security import Utilisateur


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connecter(request.app.state.reglages.database_path)
    try:
        yield conn
    finally:
        conn.close()


def get_jeton(request: Request) -> str | None:
    entete = request.headers.get("Authorization", "")
    if entete.lower().startswith("bearer "):
        return entete[7:].strip() or None
    return None


def authentifie(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Utilisateur:
    return security.utilisateur_du_jeton(conn, get_jeton(request))


def exiger(role_minimal: str) -> Callable[..., Utilisateur]:
    """Chaque route déclare son rôle minimal ; 401 sans jeton valide, 403 sinon."""
    def dependance(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Utilisateur:
        u = security.utilisateur_du_jeton(conn, get_jeton(request))
        security.verifier_role(conn, u, role_minimal, f"{request.method} {request.url.path}")
        return u
    return dependance
