"""File de revue humaine : au plus une entrée par (type, objet). Une entrée résolue n'est
jamais recréée pour le même objet, ce qui rend la planification idempotente."""
import sqlite3

from app import clock
from app.db import prochain_id
from app.journal import Acteur, journaliser

PRIORITES = {
    "ESCALADE": 90, "LITIGE": 80, "GROS_MONTANT": 70, "VERIF_PAIEMENT": 60,
    "PAIEMENT_AMBIGU": 50, "DEMANDE_ECHEANCIER": 40, "PROMESSE_A_VALIDER": 40,
    "INCERTAIN": 30, "CANAL_INVALIDE": 20, "CONSENTEMENT_ABSENT": 20, "DEMANDE_COPIE": 10,
}


def ouvrir_revue(conn: sqlite3.Connection, type_: str, objet_type: str, objet_id: str,
                 client_id: str | None, motif: str | None, acteur: Acteur) -> str | None:
    """Retourne l'identifiant créé, ou None si une entrée existe déjà pour cet objet."""
    existe = conn.execute("SELECT id FROM file_revue WHERE type = ? AND objet_type = ? "
                          "AND objet_id = ?", (type_, objet_type, objet_id)).fetchone()
    if existe:
        return None
    rid = prochain_id(conn, "REV")
    ref = clock.date_reference(conn).isoformat()
    conn.execute(
        "INSERT INTO file_revue(id, type, objet_type, objet_id, client_id, priorite, statut, "
        "motif, date_reference_creation, cree_le) VALUES (?,?,?,?,?,?,'OUVERTE',?,?,?)",
        (rid, type_, objet_type, objet_id, client_id, PRIORITES[type_], motif, ref,
         clock.maintenant()))
    journaliser(conn, "REVUE_CREEE", "REVUE", rid, apres={"type": type_, "objet_id": objet_id},
                details={"motif": motif}, acteur=acteur)
    return rid


def resoudre_revues(conn: sqlite3.Connection, type_: str, objet_type: str, objet_id: str,
                    decision: str, acteur: Acteur, commentaire: str | None = None) -> int:
    """Résout les entrées ouvertes de cet objet ; retourne leur nombre."""
    lignes = conn.execute("SELECT id FROM file_revue WHERE type = ? AND objet_type = ? AND "
                          "objet_id = ? AND statut = 'OUVERTE'",
                          (type_, objet_type, objet_id)).fetchall()
    for (rid,) in lignes:
        conn.execute("UPDATE file_revue SET statut='RESOLUE', decision=?, commentaire=?, "
                     "decideur=?, resolu_le=? WHERE id=?",
                     (decision, commentaire, acteur.id, clock.maintenant(), rid))
        journaliser(conn, "REVUE_RESOLUE", "REVUE", rid, avant={"statut": "OUVERTE"},
                    apres={"statut": "RESOLUE", "decision": decision}, acteur=acteur)
    return len(lignes)
