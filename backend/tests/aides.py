"""Aides communes aux tests d'import et de scénarios."""
from tests.verite import DATASET, lire_csv

NOMINAL = ["clients", "preferences_contact", "factures", "echeances"]


def fichiers_nominal(sauf: tuple[str, ...] = ()) -> dict[str, tuple[str, bytes, str]]:
    """Fichiers du lot nominal pour un envoi multipart (5 fichiers, accords compris)."""
    out = {n: (f"{n}.csv", (DATASET / "lot_nominal" / f"{n}.csv").read_bytes(), "text/csv")
           for n in NOMINAL if n not in sauf}
    out["accords_echeancier"] = ("accords_echeancier.csv",
                                 (DATASET / "etat_initial" / "accords_echeancier.csv").read_bytes(),
                                 "text/csv")
    return out


def fichiers_defectueux() -> dict[str, tuple[str, bytes, str]]:
    return {n: (f"{n}.csv", (DATASET / "lot_defectueux" / f"{n}.csv").read_bytes(), "text/csv")
            for n in ("clients", "factures", "echeances")}


def corps_paiement(ligne: dict[str, str]) -> dict:
    """Corps JSON d'un paiement à partir d'une ligne d'un fichier d'événements."""
    return {"client_id": ligne["client_id"] or None, "date_paiement": ligne["date_paiement"],
            "montant": int(ligne["montant"]), "mode": ligne["mode"],
            "reference_externe": ligne["reference_externe"],
            "references_indiquees": [x for x in ligne["references_indiquees"].split(";") if x]}


def evenement(nom: str) -> dict[str, str]:
    return lire_csv(f"evenements/{nom}.csv")[0]


def compter(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
