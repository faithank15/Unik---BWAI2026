"""Dossiers : contestations, promesses de paiement, accords d'échéancier (spécification, 10).

Leurs effets sur les relances passent uniquement par les suspensions du moteur (section 7.3),
jamais par un statut stocké sur la facture. Chaque événement qui peut rendre une relance
injustifiée déclenche l'annulation immédiate (section 7.9).
"""
import json
import sqlite3
from datetime import date, timedelta

from app import clock
from app.db import prochain_id, transaction
from app.domain.imports import lire_date
from app.errors import AccesRefuse, Introuvable, RegleMetier, Validation
from app.journal import Acteur, journaliser
from app.parametres import lire_entier
from app.services import relances as svc_relances
from app.services.revue import resoudre_revues


def _facture(conn: sqlite3.Connection, facture_id: str) -> sqlite3.Row:
    f = conn.execute("SELECT f.*, v.solde FROM factures f JOIN v_factures_solde v ON "
                     "v.facture_id = f.id WHERE f.id = ?", (facture_id,)).fetchone()
    if f is None:
        raise Introuvable(f"Facture {facture_id} introuvable.")
    return f


# ---- contestations ----------------------------------------------------------------------
def ouvrir_contestation_tx(conn: sqlite3.Connection, facture_id: str, motif: str,
                           acteur: Acteur, echeance_id: str | None = None,
                           message_source_id: str | None = None) -> tuple[dict, bool]:
    """Une seule contestation OUVERTE par facture et échéance : une seconde demande renvoie
    l'existante. Retourne (contestation, créée)."""
    f = _facture(conn, facture_id)
    ex = conn.execute("SELECT * FROM contestations WHERE facture_id = ? AND statut = 'OUVERTE' "
                      "AND COALESCE(echeance_id, '') = COALESCE(?, '')",
                      (facture_id, echeance_id)).fetchone()
    if ex:
        return dict(ex), False
    if echeance_id and conn.execute("SELECT 1 FROM echeances WHERE id = ? AND facture_id = ?",
                                    (echeance_id, facture_id)).fetchone() is None:
        raise RegleMetier("ECHEANCE_HORS_FACTURE", "L'échéance n'appartient pas à la facture.")
    cid = prochain_id(conn, "CTE")
    ref = clock.date_reference(conn).isoformat()
    conn.execute("INSERT INTO contestations(id, facture_id, echeance_id, motif, "
                 "message_source_id, date_ouverture, statut) VALUES (?,?,?,?,?,?,'OUVERTE')",
                 (cid, facture_id, echeance_id, motif, message_source_id, ref))
    journaliser(conn, "CONTESTATION_OUVERTE", "CONTESTATION", cid, acteur=acteur,
                apres={"facture_id": facture_id, "echeance_id": echeance_id, "motif": motif})
    svc_relances.annuler_injustifiees(conn, f["client_id"], acteur)
    return dict(conn.execute("SELECT * FROM contestations WHERE id = ?", (cid,)).fetchone()), True


def ouvrir_contestation(conn: sqlite3.Connection, facture_id: str, motif: str, acteur: Acteur,
                        echeance_id: str | None = None) -> tuple[dict, bool]:
    if not motif.strip():
        raise Validation("Le motif est obligatoire.")
    with transaction(conn):
        return ouvrir_contestation_tx(conn, facture_id, motif, acteur, echeance_id)


RESOLUTIONS = ("REJETEE", "ACCEPTEE", "ABANDONNEE")


def cloturer_contestation(conn: sqlite3.Connection, contestation_id: str, resolution: str,
                          commentaire: str, acteur: Acteur) -> dict:
    """Clôture (VALIDATEUR) à la date de référence ; l'avoir d'une contestation acceptée se crée
    séparément. La reprise des relances n'a aucun traitement spécial."""
    if resolution not in RESOLUTIONS:
        raise Validation(f"Résolution inconnue : {resolution}.", {"valeurs": list(RESOLUTIONS)})
    if not commentaire.strip():
        raise Validation("Le commentaire est obligatoire.")
    with transaction(conn):
        c = conn.execute("SELECT * FROM contestations WHERE id = ?", (contestation_id,)
                         ).fetchone()
        if c is None:
            raise Introuvable(f"Contestation {contestation_id} introuvable.")
        if c["statut"] == "CLOTUREE":
            raise RegleMetier("CONTESTATION_DEJA_CLOTUREE", "Cette contestation est clôturée.")
        ref = clock.date_reference(conn).isoformat()
        conn.execute("UPDATE contestations SET statut = 'CLOTUREE', date_cloture = ?, "
                     "resolution = ? WHERE id = ?", (ref, resolution, contestation_id))
        journaliser(conn, "CONTESTATION_CLOTUREE", "CONTESTATION", contestation_id,
                    acteur=acteur, avant={"statut": "OUVERTE"},
                    apres={"statut": "CLOTUREE", "resolution": resolution},
                    details={"commentaire": commentaire})
        if c["message_source_id"]:
            resoudre_revues(conn, "LITIGE", "MESSAGE", c["message_source_id"],
                            f"CONTESTATION_{resolution}", acteur, commentaire)
        resoudre_revues(conn, "LITIGE", "FACTURE", c["facture_id"],
                        f"CONTESTATION_{resolution}", acteur, commentaire)
        return dict(conn.execute("SELECT * FROM contestations WHERE id = ?",
                                 (contestation_id,)).fetchone())


# ---- promesses --------------------------------------------------------------------------
def creer_promesse_tx(conn: sqlite3.Connection, facture_id: str, date_promise: date,
                      montant: int | None, origine: str, acteur: Acteur,
                      message_source_id: str | None = None) -> dict:
    """Une seule promesse EN_COURS par facture : en créer une nouvelle passe l'ancienne à
    ANNULEE."""
    f = _facture(conn, facture_id)
    for (ancienne,) in conn.execute("SELECT id FROM promesses_paiement WHERE facture_id = ? "
                                    "AND statut = 'EN_COURS'", (facture_id,)).fetchall():
        conn.execute("UPDATE promesses_paiement SET statut = 'ANNULEE' WHERE id = ?",
                     (ancienne,))
        journaliser(conn, "PROMESSE_ANNULEE", "PROMESSE", ancienne, acteur=acteur,
                    avant={"statut": "EN_COURS"}, apres={"statut": "ANNULEE"},
                    details={"remplacee_par_nouvelle": True})
    pid = prochain_id(conn, "PRO")
    conn.execute("INSERT INTO promesses_paiement(id, client_id, facture_id, date_promise, "
                 "montant_promis, message_source_id, origine, statut) "
                 "VALUES (?,?,?,?,?,?,?,'EN_COURS')",
                 (pid, f["client_id"], facture_id, date_promise.isoformat(), montant,
                  message_source_id, origine))
    journaliser(conn, "PROMESSE_CREEE", "PROMESSE", pid, acteur=acteur,
                apres={"facture_id": facture_id, "date_promise": date_promise.isoformat(),
                       "montant_promis": montant, "origine": origine})
    svc_relances.annuler_injustifiees(conn, f["client_id"], acteur)
    return dict(conn.execute("SELECT * FROM promesses_paiement WHERE id = ?", (pid,)).fetchone())


def creer_promesse(conn: sqlite3.Connection, facture_id: str, date_promise: str,
                   montant: int | None, acteur: Acteur, role: str) -> dict:
    """Promesse manuelle : date au moins égale à la date de référence ; au-delà du plafond,
    seul un VALIDATEUR peut la créer."""
    d = lire_date(date_promise)
    if d is None:
        raise Validation("date_promise doit être une date AAAA-MM-JJ.")
    if montant is not None and montant <= 0:
        raise Validation("montant_promis doit être strictement positif.")
    with transaction(conn):
        ref = clock.date_reference(conn)
        f = _facture(conn, facture_id)
        if f["statut_document"] != "VALIDEE" or f["solde"] <= 0:
            raise RegleMetier("FACTURE_NON_RELANCABLE",
                              "La facture est annulée ou déjà soldée.")
        if d < ref:
            raise RegleMetier("DATE_PASSEE", "La date promise précède la date de référence.")
        if d > ref + timedelta(days=lire_entier(conn, "plafond_promesse_jours")) \
                and role != "VALIDATEUR":
            raise AccesRefuse("Au-delà du plafond, seul un VALIDATEUR peut créer la promesse.",
                              {"role_requis": "VALIDATEUR"})
        return creer_promesse_tx(conn, facture_id, d, montant, "MANUELLE", acteur)


def annuler_promesse(conn: sqlite3.Connection, promesse_id: str, acteur: Acteur) -> dict:
    with transaction(conn):
        p = conn.execute("SELECT * FROM promesses_paiement WHERE id = ?", (promesse_id,)
                         ).fetchone()
        if p is None:
            raise Introuvable(f"Promesse {promesse_id} introuvable.")
        if p["statut"] != "EN_COURS":
            raise RegleMetier("PROMESSE_NON_EN_COURS", "Seule une promesse EN_COURS s'annule.")
        conn.execute("UPDATE promesses_paiement SET statut = 'ANNULEE' WHERE id = ?",
                     (promesse_id,))
        journaliser(conn, "PROMESSE_ANNULEE", "PROMESSE", promesse_id, acteur=acteur,
                    avant={"statut": "EN_COURS"}, apres={"statut": "ANNULEE"})
        return dict(conn.execute("SELECT * FROM promesses_paiement WHERE id = ?",
                                 (promesse_id,)).fetchone())


# ---- accords d'échéancier ---------------------------------------------------------------
def proposer_accord(conn: sqlite3.Connection, facture_id: str, tranches: list[dict],
                    acteur: Acteur) -> dict:
    """Proposition (statut PROPOSE, sans effet sur les échéances). Les tranches sont conservées
    dans l'événement ACCORD_PROPOSE du journal jusqu'à l'acceptation."""
    if len(tranches) < 2:
        raise RegleMetier("TRANCHES_INSUFFISANTES", "Un accord compte au moins deux tranches.")
    dates = []
    for t in tranches:
        d = lire_date(str(t.get("date_echeance", "")))
        if d is None or int(t.get("montant", 0)) <= 0:
            raise Validation("Chaque tranche exige une date AAAA-MM-JJ et un montant positif.")
        dates.append(d)
    with transaction(conn):
        ref = clock.date_reference(conn)
        f = _facture(conn, facture_id)
        if f["statut_document"] != "VALIDEE" or f["solde"] <= 0:
            raise RegleMetier("FACTURE_NON_RELANCABLE", "La facture est annulée ou soldée.")
        if conn.execute("SELECT 1 FROM v_echeances_calc WHERE facture_id = ? AND etat = "
                        "'ACTIVE' AND affecte > 0", (facture_id,)).fetchone():
            raise RegleMetier("ACCORD_IMPOSSIBLE_PAIEMENT_PARTIEL",
                              "Un accord n'est possible que sur une facture sans paiement.")
        if sum(int(t["montant"]) for t in tranches) != f["montant_ttc"]:
            raise RegleMetier("SOMME_TRANCHES_DIFFERENTE",
                              "La somme des tranches doit égaler le montant TTC.",
                              {"montant_ttc": f["montant_ttc"]})
        if any(b <= a for a, b in zip(dates, dates[1:], strict=False)) or dates[0] < ref:
            raise RegleMetier("DATES_INVALIDES", "Dates croissantes et au moins égales à la "
                              "date de référence exigées.")
        aid = prochain_id(conn, "ACC")
        conn.execute("INSERT INTO accords_echeancier(id, facture_id, date_accord, statut, "
                     "nb_tranches) VALUES (?,?,?,'PROPOSE',?)",
                     (aid, facture_id, ref.isoformat(), len(tranches)))
        journaliser(conn, "ACCORD_PROPOSE", "ACCORD", aid, acteur=acteur,
                    apres={"facture_id": facture_id, "tranches": [
                        {"date_echeance": t["date_echeance"], "montant": int(t["montant"])}
                        for t in tranches]})
        return dict(conn.execute("SELECT * FROM accords_echeancier WHERE id = ?",
                                 (aid,)).fetchone())


def accepter_accord(conn: sqlite3.Connection, accord_id: str, acteur: Acteur) -> dict:
    """Acceptation (VALIDATEUR), dans une seule transaction : les échéances ACTIVE passent à
    REMPLACEE, les tranches sont créées, la revue DEMANDE_ECHEANCIER est résolue et les relances
    injustifiées sont annulées."""
    with transaction(conn):
        a = conn.execute("SELECT * FROM accords_echeancier WHERE id = ?", (accord_id,)
                         ).fetchone()
        if a is None:
            raise Introuvable(f"Accord {accord_id} introuvable.")
        if a["statut"] != "PROPOSE":
            raise RegleMetier("ACCORD_DEJA_TRAITE", f"L'accord est déjà {a['statut']}.")
        evt = conn.execute("SELECT apres FROM journal WHERE type_evenement = 'ACCORD_PROPOSE' "
                           "AND objet_id = ? ORDER BY id LIMIT 1", (accord_id,)).fetchone()
        tranches = json.loads(evt[0])["tranches"]
        f = _facture(conn, a["facture_id"])
        if conn.execute("SELECT 1 FROM v_echeances_calc WHERE facture_id = ? AND etat = "
                        "'ACTIVE' AND affecte > 0", (a["facture_id"],)).fetchone():
            raise RegleMetier("ACCORD_IMPOSSIBLE_PAIEMENT_PARTIEL",
                              "Un paiement a été affecté depuis la proposition.")
        conn.execute("UPDATE echeances SET etat = 'REMPLACEE' WHERE facture_id = ? AND "
                     "etat = 'ACTIVE'", (a["facture_id"],))
        for rang, t in enumerate(tranches, 1):
            conn.execute("INSERT INTO echeances(id, facture_id, rang, date_echeance, "
                         "montant_du, etat, accord_id) VALUES (?,?,?,?,?,'ACTIVE',?)",
                         (prochain_id(conn, "ECH"), a["facture_id"], rang, t["date_echeance"],
                          t["montant"], accord_id))
        conn.execute("UPDATE accords_echeancier SET statut = 'ACCEPTE', accepte_par = ? "
                     "WHERE id = ?", (acteur.id, accord_id))
        journaliser(conn, "ACCORD_ACCEPTE", "ACCORD", accord_id, acteur=acteur,
                    avant={"statut": "PROPOSE"}, apres={"statut": "ACCEPTE"})
        for (rid,) in conn.execute("SELECT objet_id FROM file_revue WHERE type = "
                                   "'DEMANDE_ECHEANCIER' AND statut = 'OUVERTE' AND "
                                   "client_id = ?", (f["client_id"],)).fetchall():
            resoudre_revues(conn, "DEMANDE_ECHEANCIER", "MESSAGE", rid, "ACCORD_ACCEPTE",
                            acteur)
        svc_relances.annuler_injustifiees(conn, f["client_id"], acteur)
        return dict(conn.execute("SELECT * FROM accords_echeancier WHERE id = ?",
                                 (accord_id,)).fetchone())


def refuser_accord(conn: sqlite3.Connection, accord_id: str, acteur: Acteur) -> dict:
    with transaction(conn):
        a = conn.execute("SELECT * FROM accords_echeancier WHERE id = ?", (accord_id,)
                         ).fetchone()
        if a is None:
            raise Introuvable(f"Accord {accord_id} introuvable.")
        if a["statut"] != "PROPOSE":
            raise RegleMetier("ACCORD_DEJA_TRAITE", f"L'accord est déjà {a['statut']}.")
        conn.execute("UPDATE accords_echeancier SET statut = 'ROMPU' WHERE id = ?",
                     (accord_id,))
        journaliser(conn, "ACCORD_REFUSE", "ACCORD", accord_id, acteur=acteur,
                    avant={"statut": "PROPOSE"}, apres={"statut": "ROMPU"},
                    details={"motif": "REFUSE"})
        return dict(conn.execute("SELECT * FROM accords_echeancier WHERE id = ?",
                                 (accord_id,)).fetchone())


def marquer_accords_respectes(conn: sqlite3.Connection, factures: set[str],
                              acteur: Acteur) -> list[str]:
    """RESPECTE : l'accord passe à RESPECTE quand toutes ses tranches sont soldées."""
    faits = []
    for fid in sorted(factures):
        for (aid,) in conn.execute("SELECT id FROM accords_echeancier WHERE facture_id = ? "
                                   "AND statut = 'ACCEPTE'", (fid,)).fetchall():
            reste = conn.execute("SELECT COUNT(*) FROM v_echeances_calc WHERE accord_id = ? "
                                 "AND etat = 'ACTIVE' AND solde > 0", (aid,)).fetchone()[0]
            if reste == 0:
                conn.execute("UPDATE accords_echeancier SET statut = 'RESPECTE' WHERE id = ?",
                             (aid,))
                journaliser(conn, "ACCORD_RESPECTE", "ACCORD", aid, acteur=acteur,
                            avant={"statut": "ACCEPTE"}, apres={"statut": "RESPECTE"})
                faits.append(aid)
    return faits
