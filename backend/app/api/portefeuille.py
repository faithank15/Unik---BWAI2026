"""Clients, factures, échéances et priorisation (lecture) ; préférences de contact."""
import sqlite3

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import clock
from app.api.commun import Page, avec_raison_sociale, paginer
from app.api.deps import authentifie, get_conn
from app.domain import imports as dom
from app.errors import Introuvable, Validation
from app.journal import journaliser, utilisateur
from app.security import Utilisateur
from app.services import calculs
from app.services.revue import resoudre_revues

routeur = APIRouter(prefix="/api", tags=["Portefeuille"])


def _encours_par_client(conn: sqlite3.Connection) -> dict[str, dict]:
    sortie: dict[str, dict] = {}
    for f in calculs.factures_calculees(conn).values():
        if f["statut_document"] != "VALIDEE" or f["solde"] <= 0:
            continue
        e = sortie.setdefault(f["client_id"], {"encours": 0, "nb_factures_ouvertes": 0})
        e["encours"] += f["solde"]
        e["nb_factures_ouvertes"] += 1
    return sortie


def _suspension_par_facture(conn: sqlite3.Connection) -> dict[str, str]:
    """Motif de suspension des relances par facture (une facture ECHUE suspendue reste dans la
    liste, avec un indicateur et son motif)."""
    from app.services import relances
    sortie: dict[str, str] = {}
    for s in relances.suspensions(conn):
        sortie.setdefault(s["facture_id"], s["motif"])
    return sortie


def _client_resume(r: sqlite3.Row, encours: dict) -> dict:
    e = encours.get(r["id"], {"encours": 0, "nb_factures_ouvertes": 0})
    return {"id": r["id"], "raison_sociale": r["raison_sociale"], "secteur": r["secteur"],
            "ville": r["ville"], "canal_prefere": r["canal_prefere"],
            "consentement_relance": bool(r["consentement_relance"]) if
            r["consentement_relance"] is not None else False, **e}


@routeur.get("/clients", summary="Liste des clients")
def liste_clients(q: str | None = None,
                  canal: str | None = Query(None, pattern="^(WHATSAPP|EMAIL)$"),
                  avec_encours: bool | None = None, page: Page = Depends(),
                  _: Utilisateur = Depends(authentifie),
                  conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    conditions, args = [], []
    if q:
        conditions.append("c.raison_sociale LIKE ? ESCAPE '\\'")
        args.append("%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if canal:
        conditions.append("p.canal_prefere = ?")
        args.append(canal)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    encours = _encours_par_client(conn)
    lignes = [_client_resume(r, encours) for r in conn.execute(
        "SELECT c.*, p.canal_prefere, p.consentement_relance FROM clients c "
        "LEFT JOIN preferences_contact p ON p.client_id = c.id" + where + " ORDER BY c.id",
        args)]
    if avec_encours is not None:
        lignes = [x for x in lignes if (x["encours"] > 0) == avec_encours]
    return paginer(lignes, page, {"id", "raison_sociale", "encours", "ville"})


@routeur.get("/clients/{client_id}", summary="Détail d'un client")
def detail_client(client_id: str, _: Utilisateur = Depends(authentifie),
                  conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    c = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if c is None:
        raise Introuvable(f"Client {client_id} introuvable.")
    p = conn.execute("SELECT * FROM preferences_contact WHERE client_id = ?",
                     (client_id,)).fetchone()
    factures = [f for f in calculs.factures_calculees(conn).values()
                if f["client_id"] == client_id]
    encours = sum(f["solde"] for f in factures
                  if f["statut_document"] == "VALIDEE" and f["solde"] > 0)
    relances = [dict(r) for r in conn.execute(
        "SELECT id, canal, etape, date_prevue, date_envoi, statut, motif FROM relances "
        "WHERE client_id = ? ORDER BY date_prevue DESC, id DESC LIMIT 10", (client_id,))]
    return {
        "id": c["id"], "raison_sociale": c["raison_sociale"], "secteur": c["secteur"],
        "ville": c["ville"], "email": c["email"], "whatsapp": c["whatsapp"],
        "actif": bool(c["actif"]),
        "preferences": None if p is None else {
            "canal_prefere": p["canal_prefere"],
            "canaux_autorises": p["canaux_autorises"].split(";"),
            "consentement_relance": bool(p["consentement_relance"]),
            "interlocuteur": p["interlocuteur"]},
        "encours": encours,
        "factures": [{k: f[k] for k in ("id", "numero", "montant_ttc", "statut", "solde",
                                        "retard_jours")} for f in factures],
        "relances_recentes": relances,
    }


class PreferencesEntree(BaseModel):
    canal_prefere: str | None = Field(None, pattern="^(WHATSAPP|EMAIL)$")
    canaux_autorises: list[str] | None = None
    consentement_relance: bool | None = None
    interlocuteur: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200)
    whatsapp: str | None = Field(None, max_length=30)


@routeur.put("/clients/{client_id}/preferences", summary="Met à jour les préférences de contact")
def modifier_preferences(client_id: str, corps: PreferencesEntree,
                         u: Utilisateur = Depends(authentifie),
                         conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    from app.db import transaction
    with transaction(conn):
        c = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if c is None:
            raise Introuvable(f"Client {client_id} introuvable.")
        p = conn.execute("SELECT * FROM preferences_contact WHERE client_id = ?",
                         (client_id,)).fetchone()
        avant = {"email": c["email"], "whatsapp": c["whatsapp"],
                 "preferences": dict(p) if p else None}
        email = c["email"] if corps.email is None else (corps.email or None)
        whatsapp = c["whatsapp"] if corps.whatsapp is None else (corps.whatsapp or None)
        if email and not dom.RE_EMAIL.match(email):
            raise Validation("Courriel mal formé.")
        if whatsapp and not dom.RE_TELEPHONE.match(whatsapp):
            raise Validation("Numéro WhatsApp mal formé (+229 suivi de 10 chiffres).")
        autorises = corps.canaux_autorises
        if autorises is not None and (not autorises or not set(autorises) <= dom.CANAUX):
            raise Validation("canaux_autorises doit contenir WHATSAPP et/ou EMAIL.")
        canal = corps.canal_prefere or (p["canal_prefere"] if p else None)
        aut = ";".join(autorises) if autorises is not None else (
            p["canaux_autorises"] if p else None)
        cons = (int(corps.consentement_relance) if corps.consentement_relance is not None
                else (p["consentement_relance"] if p else None))
        inter = corps.interlocuteur if corps.interlocuteur is not None else (
            p["interlocuteur"] if p else None)
        if canal is None or aut is None or cons is None:
            raise Validation("Un client sans préférences exige canal_prefere, "
                             "canaux_autorises et consentement_relance.")
        if canal not in aut.split(";"):
            raise Validation("Le canal préféré doit faire partie des canaux autorisés.")
        conn.execute("UPDATE clients SET email = ?, whatsapp = ? WHERE id = ?",
                     (email, whatsapp, client_id))
        conn.execute("INSERT INTO preferences_contact(client_id, canal_prefere, "
                     "canaux_autorises, consentement_relance, interlocuteur) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(client_id) DO UPDATE SET canal_prefere = excluded.canal_prefere, "
                     "canaux_autorises = excluded.canaux_autorises, consentement_relance = "
                     "excluded.consentement_relance, interlocuteur = excluded.interlocuteur",
                     (client_id, canal, aut, cons, inter))
        journaliser(conn, "PREFERENCES_MODIFIEES", "CLIENT", client_id, avant=avant,
                    apres={"canal_prefere": canal, "canaux_autorises": aut,
                           "consentement_relance": cons, "email": email, "whatsapp": whatsapp},
                    acteur=utilisateur(u.id))
        valide = bool(cons) and any(
            (x == "EMAIL" and email) or (x == "WHATSAPP" and whatsapp) for x in aut.split(";"))
        resolues = 0
        if valide:
            for t in ("CONSENTEMENT_ABSENT", "CANAL_INVALIDE"):
                resolues += resoudre_revues(conn, t, "CLIENT", client_id,
                                            "PREFERENCES_MISES_A_JOUR", utilisateur(u.id))
    return {"client_id": client_id, "canal_prefere": canal, "canaux_autorises": aut.split(";"),
            "consentement_relance": bool(cons), "interlocuteur": inter,
            "revues_resolues": resolues}


@routeur.get("/factures", summary="Liste calculée des factures")
def liste_factures(statut: str | None = None, client_id: str | None = None,
                   suspendue: bool | None = None,
                   retard_min: int | None = Query(None, ge=0),
                   solde_min: int | None = Query(None, ge=0), q: str | None = None,
                   page: Page = Depends(), _: Utilisateur = Depends(authentifie),
                   conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    lignes = []
    susp = _suspension_par_facture(conn)
    for f in calculs.factures_calculees(conn).values():
        if statut and f["statut"] != statut:
            continue
        if suspendue is not None and (f["id"] in susp) != suspendue:
            continue
        if client_id and f["client_id"] != client_id:
            continue
        if retard_min is not None and f["retard_jours"] < retard_min:
            continue
        if solde_min is not None and f["solde"] < solde_min:
            continue
        if q and q.lower() not in f["numero"].lower():
            continue
        lignes.append({**{k: f[k] for k in ("id", "numero", "client_id", "date_emission",
                                             "montant_ttc", "statut", "partiellement_payee",
                                             "solde", "affecte", "retard_jours")},
                       "suspension": susp.get(f["id"])})
    avec_raison_sociale(conn, lignes)
    return paginer(lignes, page, {"id", "numero", "client_id", "montant_ttc", "solde",
                                  "retard_jours", "date_emission", "statut"})


@routeur.get("/factures/{facture_id}", summary="Détail d'une facture")
def detail_facture(facture_id: str, _: Utilisateur = Depends(authentifie),
                   conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    f = calculs.factures_calculees(conn).get(facture_id)
    if f is None:
        raise Introuvable(f"Facture {facture_id} introuvable.")
    client = conn.execute("SELECT id, raison_sociale FROM clients WHERE id = ?",
                          (f["client_id"],)).fetchone()
    prio = next((p for p in calculs.priorisation(conn) if p["facture_id"] == facture_id), None)
    return {
        "id": f["id"], "numero": f["numero"], "client": dict(client),
        "date_emission": f["date_emission"], "montant_ttc": f["montant_ttc"],
        "conditions_paiement": f["conditions_paiement"],
        "taux_penalite_retard": f["taux_penalite_retard"], "statut": f["statut"],
        "partiellement_payee": f["partiellement_payee"], "solde": f["solde"],
        "affecte": f["affecte"], "retard_jours": f["retard_jours"],
        "suspension": _suspension_par_facture(conn).get(facture_id),
        "echeances": calculs.echeances_calculees(conn, facture_id=facture_id),
        "priorite": None if prio is None else {
            "rang": prio["rang"], "score": prio["score"],
            "points_anciennete": prio["points_anciennete"],
            "points_solde": prio["points_solde"],
            "points_historique": prio["points_historique"]},
    }


@routeur.get("/echeances", summary="Liste des échéances")
def liste_echeances(facture_id: str | None = None, client_id: str | None = None,
                    en_retard: bool | None = None, echeance_avant: str | None = None,
                    retard_min: int | None = Query(None, ge=0),
                    retard_max: int | None = Query(None, ge=0), page: Page = Depends(),
                    _: Utilisateur = Depends(authentifie),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    if echeance_avant and dom.lire_date(echeance_avant) is None:
        raise Validation("echeance_avant doit être une date AAAA-MM-JJ.")
    return paginer(calculs.echeances_calculees(
        conn, facture_id=facture_id, client_id=client_id, en_retard=en_retard,
        echeance_avant=echeance_avant, retard_min=retard_min, retard_max=retard_max), page,
        {"id", "facture_id", "date_echeance", "solde", "retard_jours", "montant_du"})


@routeur.get("/priorisation", summary="Factures échues classées avec leur score")
def priorisation(page: Page = Depends(), _: Utilisateur = Depends(authentifie),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    susp = _suspension_par_facture(conn)
    lignes = [{**x, "suspension": susp.get(x["facture_id"])} for x in calculs.priorisation(conn)]
    avec_raison_sociale(conn, lignes)
    return {**paginer(lignes, page,
                      {"rang", "retard_jours", "solde", "score", "facture_id"}),
            "date_reference": clock.date_reference(conn).isoformat()}
