"""Imports du portefeuille, paiements et avoirs (écriture) et leur consultation."""
import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.commun import Page, paginer
from app.api.deps import authentifie, get_conn
from app.errors import FichierTropGros, Introuvable
from app.journal import utilisateur
from app.security import Utilisateur
from app.services import imports as svc_imports
from app.services import paiements as svc

routeur = APIRouter(prefix="/api", tags=["Imports, paiements et avoirs"])


def _lire(f: UploadFile | None) -> bytes | None:
    if f is None:
        return None
    contenu = f.file.read(svc_imports.TAILLE_MAX + 1)
    if len(contenu) > svc_imports.TAILLE_MAX:
        raise FichierTropGros(f"Le fichier {f.filename} dépasse 5 Mo.")
    return contenu


@routeur.post("/imports", summary="Importe un lot (clients, préférences, factures, échéances)")
def importer(clients: Annotated[UploadFile, File()], factures: Annotated[UploadFile, File()],
             echeances: Annotated[UploadFile, File()],
             preferences_contact: Annotated[UploadFile | None, File()] = None,
             accords_echeancier: Annotated[UploadFile | None, File()] = None,
             u: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> JSONResponse:
    fichiers = {"clients": _lire(clients), "factures": _lire(factures),
                "echeances": _lire(echeances)}
    for nom, f in (("preferences_contact", preferences_contact),
                   ("accords_echeancier", accords_echeancier)):
        contenu = _lire(f)
        if contenu is not None:
            fichiers[nom] = contenu
    code, corps = svc_imports.importer_portefeuille(conn, fichiers, utilisateur(u.id))
    return JSONResponse(corps, status_code=code)


@routeur.get("/imports", summary="Historique des imports")
def liste_imports(page: Page = Depends(), _: Utilisateur = Depends(authentifie),
                  conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    lignes = [{"id": r["id"], "fichiers": json.loads(r["fichiers"]),
               "date_import": r["date_import"], "nb_lignes": r["nb_lignes"],
               "nb_rejets": r["nb_rejets"]}
              for r in conn.execute("SELECT * FROM imports ORDER BY id")]
    return paginer(lignes, page, {"id", "date_import", "nb_lignes", "nb_rejets"})


@routeur.get("/imports/{import_id}", summary="Rapport détaillé d'un import")
def detail_import(import_id: str, _: Utilisateur = Depends(authentifie),
                  conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    r = conn.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
    if r is None:
        raise Introuvable(f"Import {import_id} introuvable.")
    return {"id": r["id"], "fichiers": json.loads(r["fichiers"]), "empreinte": r["empreinte"],
            "date_import": r["date_import"], "nb_lignes": r["nb_lignes"],
            "nb_rejets": r["nb_rejets"], "rejets": json.loads(r["rapport"])}


class PaiementEntree(BaseModel):
    client_id: str | None = Field(None, max_length=30)
    date_paiement: str = Field(min_length=10, max_length=10)
    montant: int
    mode: str
    reference_externe: str = Field(min_length=1, max_length=80)
    references_indiquees: list[str] = Field(default_factory=list, max_length=20)


@routeur.post("/paiements", summary="Enregistre un paiement simulé (201, ou 200 en cas de rejeu)")
def creer_paiement(corps: PaiementEntree, u: Utilisateur = Depends(authentifie),
                   conn: sqlite3.Connection = Depends(get_conn)) -> JSONResponse:
    res = svc.enregistrer_paiement(
        conn, client_id=corps.client_id, date_paiement=corps.date_paiement,
        montant=corps.montant, mode=corps.mode, reference_externe=corps.reference_externe,
        references_indiquees=corps.references_indiquees, acteur=utilisateur(u.id))
    return JSONResponse(res, status_code=200 if res["deja_enregistre"] else 201)


@routeur.post("/paiements/import", summary="Importe un fichier paiements.csv")
def importer_paiements(fichier: Annotated[UploadFile, File()],
                       u: Utilisateur = Depends(authentifie),
                       conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.importer_paiements(conn, _lire(fichier) or b"", utilisateur(u.id))


@routeur.get("/paiements", summary="Liste des paiements")
def liste_paiements(client_id: str | None = None, non_affecte: bool | None = None,
                    page: Page = Depends(), _: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    conditions, args = [], []
    if client_id:
        conditions.append("p.client_id = ?")
        args.append(client_id)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    lignes = []
    for r in conn.execute(
            "SELECT p.*, p.montant - COALESCE((SELECT SUM(montant_affecte) FROM affectations a "
            "WHERE a.paiement_id = p.id), 0) AS reste FROM paiements p" + where +
            " ORDER BY p.id", args):
        if non_affecte is not None and (r["reste"] > 0) != non_affecte:
            continue
        lignes.append({"id": r["id"], "client_id": r["client_id"],
                       "date_paiement": r["date_paiement"], "montant": r["montant"],
                       "mode": r["mode"], "reference_externe": r["reference_externe"],
                       "reste_non_affecte": r["reste"]})
    return paginer(lignes, page, {"id", "date_paiement", "montant", "reste_non_affecte"})


@routeur.get("/paiements/{paiement_id}", summary="Détail d'un paiement et de ses affectations")
def detail_paiement(paiement_id: str, _: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.lire_paiement(conn, paiement_id)


class LigneAffectation(BaseModel):
    echeance_id: str
    montant: int


class AffectationEntree(BaseModel):
    affectations: list[LigneAffectation] = Field(min_length=1, max_length=50)


@routeur.post("/paiements/{paiement_id}/affecter",
              summary="Affectation manuelle d'un paiement ambigu")
def affecter(paiement_id: str, corps: AffectationEntree, u: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.affecter_manuellement(conn, paiement_id,
                                     [x.model_dump() for x in corps.affectations],
                                     utilisateur(u.id))


class AvoirEntree(BaseModel):
    facture_id: str
    date: str = Field(min_length=10, max_length=10)
    montant: int
    motif: str = Field(min_length=1, max_length=200)


@routeur.post("/avoirs", summary="Enregistre un avoir (201, ou 200 en cas de rejeu)")
def creer_avoir(corps: AvoirEntree, u: Utilisateur = Depends(authentifie),
                conn: sqlite3.Connection = Depends(get_conn)) -> JSONResponse:
    res = svc.enregistrer_avoir(conn, facture_id=corps.facture_id, date_avoir=corps.date,
                                montant=corps.montant, motif=corps.motif,
                                acteur=utilisateur(u.id))
    return JSONResponse(res, status_code=200 if res["deja_enregistre"] else 201)


@routeur.post("/avoirs/import", summary="Importe un fichier avoirs.csv")
def importer_avoirs(fichier: Annotated[UploadFile, File()],
                    u: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.importer_avoirs(conn, _lire(fichier) or b"", utilisateur(u.id))


@routeur.get("/avoirs", summary="Liste des avoirs")
def liste_avoirs(facture_id: str | None = Query(None), page: Page = Depends(),
                 _: Utilisateur = Depends(authentifie),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    sql = "SELECT id, facture_id, date_avoir AS date, montant, motif FROM avoirs"
    args: list = []
    if facture_id:
        sql += " WHERE facture_id = ?"
        args.append(facture_id)
    return paginer([dict(r) for r in conn.execute(sql + " ORDER BY id", args)], page,
                   {"id", "date", "montant", "facture_id"})
