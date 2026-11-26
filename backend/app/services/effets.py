"""Effets de bord communs après une affectation (paiement ou avoir).

Spécification 8.2 étape 5 : promesses passées à TENUE quand leur facture est soldée, puis
annulation immédiate des relances devenues injustifiées (section 7.9, jalon M2).
"""
import sqlite3

from app.journal import Acteur, journaliser


def promesses_tenues(conn: sqlite3.Connection, factures: set[str], acteur: Acteur) -> list[str]:
    """Passe à TENUE les promesses EN_COURS dont la facture est soldée."""
    tenues: list[str] = []
    for fid in sorted(factures):
        solde = conn.execute("SELECT solde FROM v_factures_solde WHERE facture_id = ?",
                             (fid,)).fetchone()
        if solde is None or solde[0] != 0:
            continue
        for (pid,) in conn.execute("SELECT id FROM promesses_paiement WHERE facture_id = ? "
                                   "AND statut = 'EN_COURS'", (fid,)).fetchall():
            conn.execute("UPDATE promesses_paiement SET statut = 'TENUE' WHERE id = ?", (pid,))
            journaliser(conn, "PROMESSE_TENUE", "PROMESSE", pid,
                        avant={"statut": "EN_COURS"}, apres={"statut": "TENUE"}, acteur=acteur)
            tenues.append(pid)
    from app.services import dossiers
    dossiers.marquer_accords_respectes(conn, factures, acteur)
    return tenues


def annuler_relances_injustifiees(conn: sqlite3.Connection, client_id: str | None,
                                  acteur: Acteur) -> list[dict]:
    """Annulation immédiate des relances devenues injustifiées (section 7.9)."""
    from app.services import relances
    return relances.annuler_injustifiees(conn, client_id, acteur)
