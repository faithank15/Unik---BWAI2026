"""Contestations, promesses, accords d'échéancier, file de revue et journal."""
import sqlite3

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.commun import Page, paginer
from app.api.deps import authentifie, exiger, get_conn
from app.errors import Introuvable, Validation
from app.journal import utilisateur
from app.security import Utilisateur
from app.services import dossiers as svc
from app.services import messages as svc_messages

routeur = APIRouter(prefix="/api", tags=["Dossiers, revue et journal"])


def _lister(conn: sqlite3.Connection, table: str, filtres: dict) -> list[dict]:
    cond, args = [], []
    for champ, valeur in filtres.items():
        if valeur:
            cond.append(f"{champ} = ?")
            args.append(valeur)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}{where} ORDER BY id", args)]


# ---- contestations ----------------------------------------------------------------------
class ContestationEntree(BaseModel):
    facture_id: str
    echeance_id: str | None = None
    motif: str = Field(min_length=1, max_length=300)


class ClotureEntree(BaseModel):
    resolution: str
    commentaire: str = Field(min_length=1, max_length=500)


@routeur.get("/contestations", summary="Liste des contestations")
def liste_contestations(statut: str | None = Query(None, pattern="^(OUVERTE|CLOTUREE)$"),
                        facture_id: str | None = None, page: Page = Depends(),
                        _: Utilisateur = Depends(authentifie),
                        conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(_lister(conn, "contestations", {"statut": statut, "facture_id": facture_id}),
                   page, {"id", "date_ouverture", "facture_id", "statut"})


@routeur.post("/contestations", summary="Ouvre une contestation (200 si déjà ouverte)")
def ouvrir_contestation(corps: ContestationEntree, u: Utilisateur = Depends(authentifie),
                        conn: sqlite3.Connection = Depends(get_conn)):
    from fastapi.responses import JSONResponse
    c, cree = svc.ouvrir_contestation(conn, corps.facture_id, corps.motif, utilisateur(u.id),
                                      corps.echeance_id)
    return JSONResponse(c, status_code=201 if cree else 200)


@routeur.post("/contestations/{contestation_id}/cloturer", summary="Clôture (VALIDATEUR)")
def cloturer(contestation_id: str, corps: ClotureEntree,
             u: Utilisateur = Depends(exiger("VALIDATEUR")),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.cloturer_contestation(conn, contestation_id, corps.resolution, corps.commentaire,
                                     utilisateur(u.id))


# ---- promesses --------------------------------------------------------------------------
class PromesseEntree(BaseModel):
    facture_id: str
    date_promise: str
    montant_promis: int | None = Field(None, gt=0)


@routeur.get("/promesses", summary="Liste des promesses")
def liste_promesses(statut: str | None = Query(
                        None, pattern="^(EN_COURS|TENUE|NON_TENUE|ANNULEE)$"),
                    facture_id: str | None = None, page: Page = Depends(),
                    _: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(_lister(conn, "promesses_paiement",
                           {"statut": statut, "facture_id": facture_id}), page,
                   {"id", "date_promise", "facture_id", "statut"})


@routeur.post("/promesses", status_code=201,
              summary="Crée une promesse (au-delà du plafond : VALIDATEUR)")
def creer_promesse(corps: PromesseEntree, u: Utilisateur = Depends(authentifie),
                   conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.creer_promesse(conn, corps.facture_id, corps.date_promise, corps.montant_promis,
                              utilisateur(u.id), u.role)


@routeur.post("/promesses/{promesse_id}/annuler", summary="Annule une promesse EN_COURS")
def annuler_promesse(promesse_id: str, u: Utilisateur = Depends(authentifie),
                     conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.annuler_promesse(conn, promesse_id, utilisateur(u.id))


# ---- accords ----------------------------------------------------------------------------
class Tranche(BaseModel):
    date_echeance: str
    montant: int = Field(gt=0)


class AccordEntree(BaseModel):
    facture_id: str
    tranches: list[Tranche] = Field(min_length=1, max_length=24)


@routeur.get("/accords", summary="Liste des accords d'échéancier")
def liste_accords(statut: str | None = Query(None, pattern="^(PROPOSE|ACCEPTE|RESPECTE|ROMPU)$"),
                  facture_id: str | None = None, page: Page = Depends(),
                  _: Utilisateur = Depends(authentifie),
                  conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return paginer(_lister(conn, "accords_echeancier",
                           {"statut": statut, "facture_id": facture_id}), page,
                   {"id", "date_accord", "facture_id", "statut"})


@routeur.post("/accords", status_code=201, summary="Propose un accord (au moins 2 tranches)")
def proposer(corps: AccordEntree, u: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.proposer_accord(conn, corps.facture_id, [t.model_dump() for t in corps.tranches],
                               utilisateur(u.id))


@routeur.post("/accords/{accord_id}/accepter", summary="Accepte et remplace les échéances")
def accepter(accord_id: str, u: Utilisateur = Depends(exiger("VALIDATEUR")),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.accepter_accord(conn, accord_id, utilisateur(u.id))


@routeur.post("/accords/{accord_id}/refuser", summary="Refuse la proposition")
def refuser(accord_id: str, u: Utilisateur = Depends(exiger("VALIDATEUR")),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc.refuser_accord(conn, accord_id, utilisateur(u.id))


# ---- revue humaine ----------------------------------------------------------------------
@routeur.get("/revue", summary="File de revue (priorité décroissante, puis création)")
def liste_revue(type: str | None = None,
                statut: str | None = Query(None, pattern="^(OUVERTE|RESOLUE)$"),
                client_id: str | None = None, page: Page = Depends(),
                _: Utilisateur = Depends(authentifie),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    lignes = _lister(conn, "file_revue", {"type": type, "statut": statut, "client_id": client_id})
    lignes.sort(key=lambda r: (-r["priorite"], r["cree_le"], r["id"]))
    if not page.tri:
        return {"total": len(lignes), "elements": lignes[page.decalage:page.decalage
                                                           + page.limite]}
    return paginer(lignes, page, {"id", "priorite", "cree_le", "type", "statut"})


@routeur.get("/revue/{revue_id}", summary="Détail avec l'objet concerné")
def detail_revue(revue_id: str, _: Utilisateur = Depends(authentifie),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    r = conn.execute("SELECT * FROM file_revue WHERE id = ?", (revue_id,)).fetchone()
    if r is None:
        raise Introuvable(f"Entrée de revue {revue_id} introuvable.")
    table = {"RELANCE": "relances", "MESSAGE": "messages_entrants", "PAIEMENT": "paiements",
             "ECHEANCE": "echeances", "FACTURE": "factures", "CLIENT": "clients"}[r["objet_type"]]
    objet = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (r["objet_id"],)).fetchone()
    return {**dict(r), "objet": dict(objet) if objet else None}


class ResolutionEntree(BaseModel):
    decision: str = Field(min_length=1, max_length=200)
    commentaire: str | None = Field(None, max_length=500)


@routeur.post("/revue/{revue_id}/resoudre", summary="Enregistre une décision « sans suite »")
def resoudre(revue_id: str, corps: ResolutionEntree, u: Utilisateur = Depends(authentifie),
             conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return svc_messages.resoudre_revue_manuelle(conn, revue_id, corps.decision,
                                                corps.commentaire, utilisateur(u.id), u.role)


# ---- journal ----------------------------------------------------------------------------
@routeur.get("/journal", summary="Journal d'audit (lecture seule)")
def journal(objet_type: str | None = None, objet_id: str | None = None,
            type_evenement: str | None = None, correlation_id: str | None = None,
            du: str | None = None, au: str | None = None, page: Page = Depends(),
            _: Utilisateur = Depends(authentifie),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    from app.domain.imports import lire_date
    for borne in (du, au):
        if borne and lire_date(borne) is None:
            raise Validation("du et au doivent être des dates AAAA-MM-JJ.")
    cond, args = [], []
    for champ, valeur in (("objet_type", objet_type), ("objet_id", objet_id),
                          ("type_evenement", type_evenement), ("correlation_id", correlation_id)):
        if valeur:
            cond.append(f"{champ} = ?")
            args.append(valeur)
    if du:
        cond.append("date_reference >= ?")
        args.append(du)
    if au:
        cond.append("date_reference <= ?")
        args.append(au)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    lignes = [dict(r) for r in conn.execute("SELECT * FROM journal" + where + " ORDER BY id",
                                            args)]
    return paginer(lignes, page, {"id", "horodatage", "type_evenement", "date_reference"})
