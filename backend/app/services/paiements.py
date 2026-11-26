"""Paiements simulés, avoirs et affectations (spécification, sections 6 et 8).

Chaque opération est idempotente, transactionnelle (BEGIN IMMEDIATE) et journalisée dans la
même transaction. Le verrou d'écriture sérialise les traitements concurrents : le second
constate que l'état a déjà changé.
"""
import csv
import io
import sqlite3
from typing import Any

from app import clock
from app.db import prochain_id, transaction
from app.domain.affectation import Cible, repartir, trier
from app.domain.imports import (
    ENTETES_AVOIRS,
    ENTETES_PAIEMENTS,
    lire_date,
    lire_entier,
    nettoyer,
    vide,
)
from app.errors import Conflit, Introuvable, RegleMetier, Validation
from app.journal import Acteur, journaliser
from app.services import effets
from app.services.revue import ouvrir_revue, resoudre_revues

MODES = {"MOBILE_MONEY", "VIREMENT", "ESPECES", "CHEQUE"}
TAILLE_MAX = 5 * 1024 * 1024


# ---- lecture ----------------------------------------------------------------------
def _cibles_facture(conn: sqlite3.Connection, facture_id: str) -> list[Cible]:
    return trier([Cible(r["echeance_id"], r["date_echeance"], r["solde"]) for r in conn.execute(
        "SELECT echeance_id, date_echeance, solde FROM v_echeances_calc "
        "WHERE facture_id = ? AND etat = 'ACTIVE' AND solde > 0", (facture_id,))])


def _cibles_client(conn: sqlite3.Connection, client_id: str) -> list[Cible]:
    return trier([Cible(r["echeance_id"], r["date_echeance"], r["solde"]) for r in conn.execute(
        "SELECT c.echeance_id, c.date_echeance, c.solde FROM v_echeances_calc c "
        "JOIN factures f ON f.id = c.facture_id "
        "WHERE f.client_id = ? AND c.etat = 'ACTIVE' AND c.solde > 0", (client_id,))])


def _ecrire_affectations(conn: sqlite3.Connection, repartition: list[tuple[str, int]],
                         source: tuple[str | None, str | None], mode: str,
                         date_aff: str) -> list[dict]:
    paiement_id, avoir_id = source
    sortie = []
    for echeance_id, montant in repartition:
        aid = prochain_id(conn, "AFF")
        conn.execute("INSERT INTO affectations(id, echeance_id, paiement_id, avoir_id, "
                     "montant_affecte, mode, date_affectation) VALUES (?,?,?,?,?,?,?)",
                     (aid, echeance_id, paiement_id, avoir_id, montant, mode, date_aff))
        sortie.append({"echeance_id": echeance_id, "montant_affecte": montant, "mode": mode})
    return sortie


def _factures_des(conn: sqlite3.Connection, echeances: list[str]) -> set[str]:
    return {conn.execute("SELECT facture_id FROM echeances WHERE id = ?", (e,)).fetchone()[0]
            for e in echeances}


def _client_de_facture(conn: sqlite3.Connection, facture_id: str) -> str:
    return conn.execute("SELECT client_id FROM factures WHERE id = ?", (facture_id,)
                        ).fetchone()[0]


def lire_paiement(conn: sqlite3.Connection, paiement_id: str) -> dict:
    p = conn.execute("SELECT * FROM paiements WHERE id = ?", (paiement_id,)).fetchone()
    if p is None:
        raise Introuvable(f"Paiement {paiement_id} introuvable.")
    aff = [{"echeance_id": r["echeance_id"], "montant_affecte": r["montant_affecte"],
            "mode": r["mode"]} for r in conn.execute(
        "SELECT echeance_id, montant_affecte, mode FROM affectations WHERE paiement_id = ? "
        "ORDER BY id", (paiement_id,))]
    reste = p["montant"] - sum(a["montant_affecte"] for a in aff)
    return {"id": p["id"], "client_id": p["client_id"], "date_paiement": p["date_paiement"],
            "montant": p["montant"], "mode": p["mode"],
            "reference_externe": p["reference_externe"], "source": p["source"],
            "statut": p["statut"], "affectations": aff, "reste_non_affecte": reste}


# ---- paiements --------------------------------------------------------------------
def _enregistrer_paiement(conn: sqlite3.Connection, *, client_id: str | None,
                          date_paiement: str, montant: int, mode: str,
                          reference_externe: str, references_indiquees: list[str],
                          acteur: Acteur, paiement_id: str | None = None) -> dict:
    """Corps de l'opération, à appeler dans une transaction ouverte."""
    if mode not in MODES:
        raise Validation(f"Mode de paiement inconnu : {mode}.")
    if montant <= 0:
        raise Validation("Le montant doit être strictement positif.")
    if vide(reference_externe):
        raise Validation("La référence externe est obligatoire.")
    d = lire_date(date_paiement)
    if d is None:
        raise Validation(f"Date de paiement invalide : {date_paiement}.")
    existant = conn.execute("SELECT * FROM paiements WHERE mode = ? AND reference_externe = ?",
                            (mode, reference_externe)).fetchone()
    if existant:
        memes = (existant["client_id"] == client_id and existant["date_paiement"] ==
                 date_paiement and existant["montant"] == montant)
        if not memes:
            raise Conflit("Cette référence de paiement existe déjà avec d'autres valeurs.",
                          {"paiement_id": existant["id"], "mode": mode,
                           "reference_externe": reference_externe})
        journaliser(conn, "PAIEMENT_REJOUE", "PAIEMENT", existant["id"], acteur=acteur,
                    details={"mode": mode, "reference_externe": reference_externe})
        res = lire_paiement(conn, existant["id"])
        return {**res, "relances_annulees": [], "promesses_tenues": [],
                "deja_enregistre": True}
    if d > clock.date_reference(conn):
        raise RegleMetier("DATE_FUTURE", "La date du paiement est postérieure à la date de "
                          "référence.", {"date_paiement": date_paiement})
    if client_id is not None and conn.execute("SELECT 1 FROM clients WHERE id = ?",
                                              (client_id,)).fetchone() is None:
        raise RegleMetier("CLIENT_INCONNU", f"Client {client_id} inconnu.")
    # Références indiquées : même client obligatoire, factures annulées refusées.
    factures_indiquees: list[str] = []
    introuvables: list[str] = []
    if client_id is not None:
        for numero in references_indiquees:
            f = conn.execute("SELECT id, statut_document FROM factures WHERE client_id = ? "
                             "AND numero = ?", (client_id, numero)).fetchone()
            if f is None:
                introuvables.append(numero)
            elif f["statut_document"] == "ANNULEE":
                raise RegleMetier("FACTURE_ANNULEE", f"La facture {numero} est annulée.",
                                  {"numero": numero})
            else:
                factures_indiquees.append(f["id"])
    else:
        introuvables = list(references_indiquees)
    pid = paiement_id or prochain_id(conn, "PAY")
    conn.execute("INSERT INTO paiements(id, client_id, date_paiement, montant, mode, "
                 "reference_externe) VALUES (?,?,?,?,?,?)",
                 (pid, client_id, date_paiement, montant, mode, reference_externe))
    journaliser(conn, "PAIEMENT_ENREGISTRE", "PAIEMENT", pid, acteur=acteur,
                apres={"client_id": client_id, "montant": montant, "mode": mode,
                       "date_paiement": date_paiement},
                details={"reference_externe": reference_externe})
    for numero in introuvables:
        journaliser(conn, "REFERENCE_INTROUVABLE", "PAIEMENT", pid, acteur=acteur,
                    details={"numero": numero})
    reste, affectations = montant, []
    if client_id is not None:
        for fid in factures_indiquees:
            rep, reste = repartir(reste, _cibles_facture(conn, fid))
            affectations += _ecrire_affectations(conn, rep, (pid, None), "INDIQUEE",
                                                 date_paiement)
        if reste > 0:
            rep, reste = repartir(reste, _cibles_client(conn, client_id))
            affectations += _ecrire_affectations(conn, rep, (pid, None), "AUTO_ANCIENNETE",
                                                 date_paiement)
    if client_id is None or reste > 0:
        ouvrir_revue(conn, "PAIEMENT_AMBIGU", "PAIEMENT", pid, client_id,
                     "Paiement non identifiable" if client_id is None
                     else "Reste non affecté", acteur)
        journaliser(conn, "PAIEMENT_NON_AFFECTE", "PAIEMENT", pid, acteur=acteur,
                    details={"reste": reste})
    if affectations:
        journaliser(conn, "PAIEMENT_AFFECTE", "PAIEMENT", pid, acteur=acteur,
                    apres={"affectations": affectations, "reste": reste})
    touchees = _factures_des(conn, [a["echeance_id"] for a in affectations])
    tenues = effets.promesses_tenues(conn, touchees, acteur)
    annulees = effets.annuler_relances_injustifiees(conn, client_id, acteur) \
        if affectations else []
    return {"id": pid, "client_id": client_id, "date_paiement": date_paiement,
            "montant": montant, "mode": mode, "reference_externe": reference_externe,
            "source": "SIMULE", "statut": "RECU", "affectations": affectations,
            "reste_non_affecte": reste, "relances_annulees": annulees,
            "promesses_tenues": tenues, "deja_enregistre": False}


def enregistrer_paiement(conn: sqlite3.Connection, **kw: Any) -> dict:
    with transaction(conn):
        return _enregistrer_paiement(conn, **kw)


def affecter_manuellement(conn: sqlite3.Connection, paiement_id: str, lignes: list[dict],
                          acteur: Acteur) -> dict:
    """Affectation manuelle d'un paiement ambigu : total ≤ montant non affecté, toutes les
    échéances du même client (qui devient le client du paiement s'il était vide), mode
    INDIQUEE. Les effets habituels s'appliquent et la revue est résolue."""
    if not lignes:
        raise Validation("Au moins une affectation est requise.")
    with transaction(conn):
        p = lire_paiement(conn, paiement_id)
        total = sum(int(ligne["montant"]) for ligne in lignes)
        if any(int(ligne["montant"]) <= 0 for ligne in lignes):
            raise Validation("Les montants affectés doivent être strictement positifs.")
        if total > p["reste_non_affecte"]:
            raise RegleMetier("SUR_AFFECTATION", "Le total dépasse le montant non affecté du "
                              "paiement.", {"reste_non_affecte": p["reste_non_affecte"]})
        clients, par_ech = set(), {}
        for ligne in lignes:
            e = conn.execute("SELECT c.echeance_id, c.solde, c.etat, f.client_id "
                             "FROM v_echeances_calc c JOIN factures f ON f.id = c.facture_id "
                             "WHERE c.echeance_id = ?", (ligne["echeance_id"],)).fetchone()
            if e is None:
                raise Introuvable(f"Échéance {ligne['echeance_id']} introuvable.")
            if e["etat"] != "ACTIVE":
                raise RegleMetier("ECHEANCE_REMPLACEE", "Cette échéance a été remplacée.",
                                  {"echeance_id": e["echeance_id"]})
            clients.add(e["client_id"])
            par_ech[e["echeance_id"]] = par_ech.get(e["echeance_id"], 0) + int(ligne["montant"])
            if par_ech[e["echeance_id"]] > e["solde"]:
                raise RegleMetier("SUR_AFFECTATION", "Le montant dépasse le solde de "
                                  "l'échéance.", {"echeance_id": e["echeance_id"],
                                                  "solde": e["solde"]})
        if len(clients) != 1:
            raise RegleMetier("CLIENTS_DIFFERENTS", "Toutes les échéances doivent appartenir "
                              "au même client.")
        client = clients.pop()
        if p["client_id"] and p["client_id"] != client:
            raise RegleMetier("CLIENTS_DIFFERENTS", "Les échéances n'appartiennent pas au "
                              "client du paiement.")
        if not p["client_id"]:
            conn.execute("UPDATE paiements SET client_id = ? WHERE id = ?", (client, paiement_id))
        affectations = _ecrire_affectations(conn, list(par_ech.items()), (paiement_id, None),
                                            "INDIQUEE", p["date_paiement"])
        journaliser(conn, "PAIEMENT_AFFECTE", "PAIEMENT", paiement_id, acteur=acteur,
                    apres={"affectations": affectations}, details={"manuelle": True})
        resoudre_revues(conn, "PAIEMENT_AMBIGU", "PAIEMENT", paiement_id,
                        "AFFECTATION_MANUELLE", acteur)
        tenues = effets.promesses_tenues(conn, _factures_des(conn, list(par_ech)), acteur)
        annulees = effets.annuler_relances_injustifiees(conn, client, acteur)
        res = lire_paiement(conn, paiement_id)
    return {**res, "relances_annulees": annulees, "promesses_tenues": tenues,
            "deja_enregistre": False}


# ---- avoirs -----------------------------------------------------------------------
def _lire_avoir(conn: sqlite3.Connection, avoir_id: str) -> dict:
    a = conn.execute("SELECT * FROM avoirs WHERE id = ?", (avoir_id,)).fetchone()
    aff = [{"echeance_id": r["echeance_id"], "montant_affecte": r["montant_affecte"],
            "mode": r["mode"]} for r in conn.execute(
        "SELECT echeance_id, montant_affecte, mode FROM affectations WHERE avoir_id = ? "
        "ORDER BY id", (avoir_id,))]
    return {"id": a["id"], "facture_id": a["facture_id"], "date": a["date_avoir"],
            "montant": a["montant"], "motif": a["motif"], "affectations": aff}


def _enregistrer_avoir(conn: sqlite3.Connection, *, facture_id: str, date_avoir: str,
                       montant: int, motif: str, acteur: Acteur,
                       avoir_id: str | None = None) -> dict:
    if montant <= 0:
        raise Validation("Le montant doit être strictement positif.")
    if vide(motif):
        raise Validation("Le motif est obligatoire.")
    d = lire_date(date_avoir)
    if d is None:
        raise Validation(f"Date d'avoir invalide : {date_avoir}.")
    f = conn.execute("SELECT id, client_id FROM factures WHERE id = ?", (facture_id,)).fetchone()
    if f is None:
        raise Introuvable(f"Facture {facture_id} introuvable.")
    rejeu = conn.execute("SELECT id FROM avoirs WHERE facture_id = ? AND date_avoir = ? AND "
                         "montant = ? AND motif = ?", (facture_id, date_avoir, montant, motif)
                         ).fetchone()
    if rejeu:
        return {**_lire_avoir(conn, rejeu["id"]), "relances_annulees": [],
                "promesses_tenues": [], "deja_enregistre": True}
    if d > clock.date_reference(conn):
        raise RegleMetier("DATE_FUTURE", "La date de l'avoir est postérieure à la date de "
                          "référence.", {"date": date_avoir})
    solde = conn.execute("SELECT solde FROM v_factures_solde WHERE facture_id = ?",
                         (facture_id,)).fetchone()[0]
    if montant > solde:
        raise RegleMetier("AVOIR_SUPERIEUR_AU_SOLDE", "L'avoir dépasse le solde de la facture.",
                          {"solde": solde, "montant": montant})
    aid = avoir_id or prochain_id(conn, "AVO")
    conn.execute("INSERT INTO avoirs(id, facture_id, date_avoir, montant, motif) "
                 "VALUES (?,?,?,?,?)", (aid, facture_id, date_avoir, montant, motif))
    journaliser(conn, "AVOIR_ENREGISTRE", "AVOIR", aid, acteur=acteur,
                apres={"facture_id": facture_id, "montant": montant, "motif": motif})
    rep, reste = repartir(montant, _cibles_facture(conn, facture_id))
    assert reste == 0
    affectations = _ecrire_affectations(conn, rep, (None, aid), "AUTO_ANCIENNETE", date_avoir)
    journaliser(conn, "PAIEMENT_AFFECTE", "AVOIR", aid, acteur=acteur,
                apres={"affectations": affectations})
    tenues = effets.promesses_tenues(conn, {facture_id}, acteur)
    annulees = effets.annuler_relances_injustifiees(conn, f["client_id"], acteur)
    return {**_lire_avoir(conn, aid), "relances_annulees": annulees, "promesses_tenues": tenues,
            "deja_enregistre": False}


def enregistrer_avoir(conn: sqlite3.Connection, **kw: Any) -> dict:
    with transaction(conn):
        return _enregistrer_avoir(conn, **kw)


# ---- imports de fichiers ----------------------------------------------------------
def _lire_csv(contenu: bytes, entetes_attendus: list[str], nom: str) -> list[dict[str, str]]:
    if len(contenu) > TAILLE_MAX:
        from app.errors import FichierTropGros
        raise FichierTropGros(f"Le fichier {nom} dépasse 5 Mo.")
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise Validation(f"Le fichier {nom} n'est pas en UTF-8.") from e
    lecteur = csv.DictReader(io.StringIO(texte, newline=""))
    entetes = lecteur.fieldnames or []
    if sorted(entetes) != sorted(entetes_attendus):
        raise Validation(f"En-têtes invalides dans {nom}.",
                         {"attendus": entetes_attendus, "recus": entetes})
    return [nettoyer(r) for r in lecteur]


def importer_paiements(conn: sqlite3.Connection, contenu: bytes, acteur: Acteur) -> dict:
    """Fichier paiements.csv traité dans une transaction, avec un rapport par ligne."""
    lignes = _lire_csv(contenu, ENTETES_PAIEMENTS, "paiements.csv")
    rapport: dict[str, Any] = {"enregistres": 0, "rejoues": 0, "conflits": 0, "rejets": []}
    with transaction(conn):
        for n, r in enumerate(lignes, 2):
            conn.execute("SAVEPOINT ligne")
            try:
                montant = lire_entier(r["montant"])
                if montant is None:
                    raise Validation(f"Montant invalide : {r['montant']}.")
                res = _enregistrer_paiement(
                    conn, client_id=r["client_id"] or None, date_paiement=r["date_paiement"],
                    montant=montant, mode=r["mode"], reference_externe=r["reference_externe"],
                    references_indiquees=[x for x in r["references_indiquees"].split(";") if x],
                    acteur=acteur, paiement_id=r["id"] or None)
                rapport["rejoues" if res["deja_enregistre"] else "enregistres"] += 1
                conn.execute("RELEASE ligne")
            except Conflit as e:
                conn.execute("ROLLBACK TO ligne")
                conn.execute("RELEASE ligne")
                rapport["conflits"] += 1
                rapport["rejets"].append({"ligne": n, "motif_code": "CONFLIT",
                                          "detail": e.message})
            except (Validation, RegleMetier) as e:
                conn.execute("ROLLBACK TO ligne")
                conn.execute("RELEASE ligne")
                rapport["rejets"].append({"ligne": n, "motif_code": e.details.get(
                    "regle", e.code), "detail": e.message})
    return rapport


def importer_avoirs(conn: sqlite3.Connection, contenu: bytes, acteur: Acteur) -> dict:
    lignes = _lire_csv(contenu, ENTETES_AVOIRS, "avoirs.csv")
    rapport: dict[str, Any] = {"enregistres": 0, "rejoues": 0, "conflits": 0, "rejets": []}
    with transaction(conn):
        for n, r in enumerate(lignes, 2):
            conn.execute("SAVEPOINT ligne")
            try:
                montant = lire_entier(r["montant"])
                if montant is None:
                    raise Validation(f"Montant invalide : {r['montant']}.")
                res = _enregistrer_avoir(conn, facture_id=r["facture_id"], date_avoir=r["date"],
                                         montant=montant, motif=r["motif"], acteur=acteur,
                                         avoir_id=r["id"] or None)
                rapport["rejoues" if res["deja_enregistre"] else "enregistres"] += 1
                conn.execute("RELEASE ligne")
            except (Validation, RegleMetier, Introuvable) as e:
                conn.execute("ROLLBACK TO ligne")
                conn.execute("RELEASE ligne")
                rapport["rejets"].append({"ligne": n, "motif_code": e.details.get(
                    "regle", e.code), "detail": e.message})
    return rapport
