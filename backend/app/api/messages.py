"""Messages entrants et classification."""
import sqlite3

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.commun import Page, paginer
from app.api.deps import authentifie, get_conn
from app.journal import utilisateur
from app.security import Utilisateur
from app.services import messages as svc

routeur = APIRouter(prefix="/api", tags=["Messages et classification"])


class MessageEntree(BaseModel):
    client_id: str = Field(max_length=30)
    canal: str
    contenu: str = Field(min_length=1)
    facture_citee: str | None = Field(None, max_length=40)
    reference_externe: str | None = Field(None, max_length=80)


@routeur.post("/messages", summary="Simule la réception d'un message client (201)")
def recevoir(corps: MessageEntree, u: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> JSONResponse:
    m, cree = svc.recevoir_message(conn, corps.client_id, corps.canal, corps.contenu,
                                   corps.facture_citee, corps.reference_externe,
                                   utilisateur(u.id))
    return JSONResponse({"id": m["id"], "statut_traitement": m["statut_traitement"],
                         "facture_citee_id": m["facture_citee_id"]},
                        status_code=201 if cree else 200)


@routeur.get("/messages", summary="Liste des messages")
def liste(statut_traitement: str | None = Query(
              None, pattern="^(A_CLASSER|CLASSE|EN_REVUE|TRAITE)$"),
          categorie: str | None = None, client_id: str | None = None, page: Page = Depends(),
          _: Utilisateur = Depends(authentifie),
          conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(svc.lister_messages(conn, statut_traitement, categorie, client_id), page,
                   {"id", "date_reception", "client_id", "statut_traitement", "confiance"})


@routeur.get("/messages/{message_id}", summary="Détail avec résultat de classification")
def detail(message_id: str, _: Utilisateur = Depends(authentifie),
           conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.lire_message(conn, message_id)


@routeur.post("/messages/{message_id}/classer", summary="Relance la classification")
def classer(message_id: str, request: Request, synchrone: bool = False,
            u: Utilisateur = Depends(authentifie),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """`synchrone=true` fait le travail dans la requête (tests) ; sinon le worker s'en charge
    et la route ne fait que vérifier que le message existe."""
    if not synchrone:
        return svc.lire_message(conn, message_id)
    return svc.classer_message(conn, message_id, request.app.state.classeur)


class ValidationCategorie(BaseModel):
    categorie: str
    date_promise: str | None = None
    montant_promis: int | None = Field(None, gt=0)
    facture_id: str | None = None
    commentaire: str | None = Field(None, max_length=500)


@routeur.post("/messages/{message_id}/valider-categorie",
              summary="Classement humain et application de l'action")
def valider_categorie(message_id: str, corps: ValidationCategorie,
                      u: Utilisateur = Depends(authentifie),
                      conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.valider_categorie(conn, message_id, corps.categorie, utilisateur(u.id), u.role,
                                 corps.date_promise, corps.montant_promis, corps.facture_id,
                                 corps.commentaire)
