"""Réinitialisation : supprime la base puis la recrée (le journal n'est jamais purgé ligne
par ligne, il disparaît avec le fichier) : schéma, paramètres, jours fériés, comptes de
démonstration, puis chargement du jeu de données (sauf `charger=False`)."""
import csv
import json
import os
from pathlib import Path

from app import security
from app.config import Reglages
from app.db import appliquer_schema, connecter, transaction
from app.errors import Validation
from app.journal import SYSTEME, journaliser
from app.parametres import DEFAUTS
from app.services.chargeur import charger_jeu


def _supprimer_base(chemin: str) -> None:
    for suffixe in ("", "-wal", "-shm"):
        try:
            os.remove(chemin + suffixe)
        except FileNotFoundError:
            pass


def reinitialiser(reglages: Reglages, charger: bool = True) -> dict:
    if not reglages.seed_mdp_gestionnaire or not reglages.seed_mdp_validateur:
        raise Validation("SEED_MDP_GESTIONNAIRE et SEED_MDP_VALIDATEUR doivent être définis "
                         "dans .env (voir .env.example).")
    _supprimer_base(reglages.database_path)
    Path(reglages.database_path).parent.mkdir(parents=True, exist_ok=True)
    dataset = Path(reglages.dataset_dir)
    params_fichier = dataset / "params.json"
    date_reference = None
    if params_fichier.is_file():
        date_reference = json.loads(params_fichier.read_text(encoding="utf-8"))["date_reference"]
    conn = connecter(reglages.database_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        appliquer_schema(conn)
        with transaction(conn):
            for cle, valeur, type_, description in DEFAUTS:
                if cle == "date_reference" and date_reference:
                    valeur = date_reference
                conn.execute("INSERT INTO parametres(cle, valeur, type, description) "
                             "VALUES (?,?,?,?)", (cle, valeur, type_, description))
            feries = dataset / "lot_nominal" / "jours_feries.csv"
            if feries.is_file():
                with feries.open(encoding="utf-8", newline="") as f:
                    for r in csv.DictReader(f):
                        conn.execute("INSERT INTO jours_feries(date, libelle) VALUES (?,?)",
                                     (r["date"], r["libelle"]))
            security.creer_utilisateur(conn, "gestionnaire", "Gestionnaire démo",
                                       "GESTIONNAIRE", reglages.seed_mdp_gestionnaire)
            security.creer_utilisateur(conn, "validateur", "Validateur démo", "VALIDATEUR",
                                       reglages.seed_mdp_validateur)
        bilan = None
        if charger and (dataset / "lot_nominal").is_dir():
            bilan = charger_jeu(conn, dataset)
        with transaction(conn):
            journaliser(conn, "RESET", "SYSTEME", None, acteur=SYSTEME,
                        details={"jeu_de_donnees": bool(bilan),
                                 "paiements": bilan["paiements"] if bilan else 0})
    finally:
        conn.close()
    return {"statut": "reinitialisee", "base": reglages.database_path}
