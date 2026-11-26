"""Écriture validée et journalisée des paramètres métier."""
import sqlite3
from decimal import Decimal, InvalidOperation

from app.db import transaction
from app.domain import imports as dom
from app.errors import Introuvable, Validation
from app.journal import Acteur, journaliser


def valider_valeur(type_: str, valeur: str, cle: str) -> str:
    v = valeur.strip()
    if type_ == "ENTIER":
        if v == "" and cle == "simulation_interruption_apres":
            return ""
        if not dom.RE_ENTIER.match(v):
            raise Validation(f"{cle} doit être un entier.")
    elif type_ == "DECIMAL":
        try:
            Decimal(v)
        except InvalidOperation as e:
            raise Validation(f"{cle} doit être un nombre décimal.") from e
    elif type_ == "BOOLEEN":
        if v.lower() not in ("true", "false"):
            raise Validation(f"{cle} doit valoir true ou false.")
        v = v.lower()
    elif type_ == "DATE":
        if dom.lire_date(v) is None:
            raise Validation(f"{cle} doit être une date AAAA-MM-JJ.")
    elif not v:
        raise Validation(f"{cle} ne peut pas être vide.")
    return v


def ecrire_parametre_tx(conn: sqlite3.Connection, cle: str, valeur: str, acteur: Acteur) -> dict:
    """À appeler dans une transaction ouverte."""
    p = conn.execute("SELECT * FROM parametres WHERE cle = ?", (cle,)).fetchone()
    if p is None:
        raise Introuvable(f"Paramètre {cle} introuvable.")
    nouvelle = valider_valeur(p["type"], valeur, cle)
    conn.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (nouvelle, cle))
    journaliser(conn, "DATE_REFERENCE_MODIFIEE" if cle == "date_reference"
                else "PARAMETRE_MODIFIE", "PARAMETRE", cle,
                avant={"valeur": p["valeur"]}, apres={"valeur": nouvelle}, acteur=acteur)
    return {"cle": cle, "valeur": nouvelle, "type": p["type"]}


def ecrire_parametre(conn: sqlite3.Connection, cle: str, valeur: str, acteur: Acteur) -> dict:
    with transaction(conn):
        return ecrire_parametre_tx(conn, cle, valeur, acteur)
