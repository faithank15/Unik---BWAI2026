"""Tableau de bord, balance âgée, explication d'une facture, comparaison à la référence."""
import sqlite3

from fastapi import APIRouter, Depends

from app.api.deps import authentifie, get_conn
from app.security import Utilisateur
from app.services import tableau as svc

routeur = APIRouter(prefix="/api", tags=["Tableau de bord et explications"])


@routeur.get("/tableau-de-bord", summary="Indicateurs, chacun renvoyant à sa liste")
def tableau_de_bord(_: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.tableau_de_bord(conn)


@routeur.get("/tableau-de-bord/balance-agee", summary="Balance âgée par tranche de retard")
def balance_agee(_: Utilisateur = Depends(authentifie),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.balance_agee(conn)


@routeur.get("/evaluation/comparaison-reference",
             summary="Comparaison avec la règle « relancer tout ce qui est échu »")
def comparaison(_: Utilisateur = Depends(authentifie),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.comparaison_reference(conn)


@routeur.get("/factures/{facture_id}/explication",
             summary="Pièces et événements qui expliquent le résultat")
def explication(facture_id: str, _: Utilisateur = Depends(authentifie),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.explication_facture(conn, facture_id)
