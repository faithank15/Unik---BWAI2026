"""Relances et canaux simulés."""
import sqlite3

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.commun import Page, avec_raison_sociale, paginer
from app.api.deps import authentifie, exiger, get_conn
from app.domain.imports import lire_date
from app.errors import Validation
from app.journal import utilisateur
from app.security import Utilisateur
from app.services import redaction as svc_redaction
from app.services import relances as svc

routeur = APIRouter(prefix="/api", tags=["Relances et canaux simulés"])


@routeur.post("/relances/planifier", summary="Lance la planification du jour")
def planifier(u: Utilisateur = Depends(authentifie),
              conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.planifier(conn, utilisateur(u.id))


@routeur.post("/relances/envoyer", summary="Revérifie et envoie les relances PLANIFIEE du jour")
def envoyer(request: Request, u: Utilisateur = Depends(authentifie),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.envoyer_lot(conn, utilisateur(u.id), request.app.state.classeur)


class RelanceManuelleEntree(BaseModel):
    client_id: str = Field(min_length=1, max_length=30)
    canal: str | None = Field(None, pattern="^(WHATSAPP|EMAIL)$")
    facture_ids: list[str] | None = Field(None, max_length=50)
    commentaire: str | None = Field(None, max_length=200)


@routeur.post("/relances/manuelle", status_code=201,
              summary="Relance instantanée d'un client, message rédigé par le LLM (201, ou 200 "
                      "en cas de rejeu)")
def relance_manuelle(corps: RelanceManuelleEntree, request: Request, reponse: Response,
                     u: Utilisateur = Depends(authentifie),
                     conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    res = svc.relancer_manuellement(conn, corps.client_id, corps.canal, corps.facture_ids,
                                    corps.commentaire, utilisateur(u.id),
                                    request.app.state.classeur)
    if res["deja_fait"]:
        reponse.status_code = 200
    return {**res, "relance": svc.lire_relance(conn, res["relance_id"])}


@routeur.get("/redactions", summary="Rédactions de courriels générées par le LLM (cache)")
def redactions(statut: str | None = Query(None, pattern="^(A_RELIRE|RELUE)$"),
               page: Page = Depends(), _: Utilisateur = Depends(authentifie),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(svc_redaction.lister(conn, statut), page,
                   {"cle", "cas", "ton", "canal", "statut", "cree_le"})


class RelueEntree(BaseModel):
    cle: str = Field(min_length=1, max_length=200)


@routeur.post("/redactions/relue", summary="Marque une rédaction comme relue par une personne")
def redaction_relue(corps: RelueEntree, u: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc_redaction.marquer_relue(conn, corps.cle, utilisateur(u.id))


@routeur.get("/relances/suspensions", summary="Échéances suspendues avec leur motif")
def suspensions(page: Page = Depends(), _: Utilisateur = Depends(authentifie),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(avec_raison_sociale(conn, svc.suspensions(conn)), page,
                   {"echeance_id", "facture_id", "client_id", "motif", "date_echeance", "solde"})


@routeur.get("/relances", summary="Liste des relances")
def liste(statut: str | None = Query(None, pattern="^(PLANIFIEE|EN_ATTENTE_VALIDATION|"
                                     "ENVOYEE_SIM|ANNULEE|SAUTEE|ABSORBEE)$"),
          client_id: str | None = None,
          etape: str | None = Query(None, pattern="^(P|R1|R2|R3|GROUPE)$"),
          date: str | None = None, page: Page = Depends(),
          _: Utilisateur = Depends(authentifie),
          conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    if date and lire_date(date) is None:
        raise Validation("date doit être une date AAAA-MM-JJ.")
    return paginer(avec_raison_sociale(conn, svc.lister_relances(
        conn, statut, client_id, etape, date)), page,
                   {"id", "client_id", "date_prevue", "date_envoi", "statut", "etape"})


@routeur.get("/relances/{relance_id}", summary="Détail d'une relance")
def detail(relance_id: str, _: Utilisateur = Depends(authentifie),
           conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.lire_relance(conn, relance_id)


@routeur.post("/relances/{relance_id}/valider",
              summary="Valide une relance de gros montant puis revérifie et envoie")
def valider(relance_id: str, request: Request, u: Utilisateur = Depends(exiger("VALIDATEUR")),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    res = svc.valider_relance(conn, relance_id, utilisateur(u.id), request.app.state.classeur)
    return {**res, "relance": svc.lire_relance(conn, relance_id)}


@routeur.post("/relances/{relance_id}/rejeter", summary="Rejette la relance")
def rejeter(relance_id: str, u: Utilisateur = Depends(exiger("VALIDATEUR")),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    res = svc.rejeter_relance(conn, relance_id, utilisateur(u.id))
    return {**res, "relance": svc.lire_relance(conn, relance_id)}


@routeur.get("/canaux/envois", summary="Boîte d'envoi simulée")
def envois(canal: str | None = Query(None, pattern="^(WHATSAPP|EMAIL)$"),
           client_id: str | None = None, page: Page = Depends(),
           _: Utilisateur = Depends(authentifie),
           conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(avec_raison_sociale(conn, svc.boite_envoi(conn, canal, client_id)), page,
                   {"id", "horodatage", "client_id", "canal", "date_envoi"})
