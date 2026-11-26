"""Chargement du jeu de données au `reset` (spécification, section 16).

Réutilise l'import du portefeuille (donc ses validations) puis enregistre avoirs et paiements
par les mêmes services que l'API, dans l'ordre des dates, pour que les affectations soient
calculées et non copiées. Charge enfin l'état initial (promesses, contestations, relances
historiques) et positionne les séquences. Les relances historiques n'ont pas d'événement de
journal : leur trace est dans leurs lignes de base.
"""
import csv
import sqlite3
from pathlib import Path

from app import clock
from app.db import positionner_sequence, transaction
from app.domain.imports import lire_entier
from app.errors import ErreurMetier
from app.journal import SYSTEME
from app.services.imports import importer_portefeuille
from app.services.paiements import enregistrer_avoir, enregistrer_paiement


def _csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def charger_jeu(conn: sqlite3.Connection, dataset: Path) -> dict:
    lot, initial = dataset / "lot_nominal", dataset / "etat_initial"
    noms = {"clients": lot / "clients.csv", "preferences_contact": lot / "preferences_contact.csv",
            "factures": lot / "factures.csv", "echeances": lot / "echeances.csv",
            "accords_echeancier": initial / "accords_echeancier.csv"}
    for chemin in noms.values():
        if not chemin.is_file():
            raise ErreurMetier(f"Jeu de données incomplet : {chemin} est absent.")
    _, rapport = importer_portefeuille(conn, {n: p.read_bytes() for n, p in noms.items()},
                                       SYSTEME)
    if rapport["nb_rejets"]:
        raise ErreurMetier(f"Le lot nominal contient {rapport['nb_rejets']} rejets : "
                           f"{rapport['rejets'][:3]}")
    # Avoirs et paiements, dans l'ordre des dates (puis des identifiants)
    evenements = []
    for p in _csv(lot / "paiements.csv"):
        evenements.append((p["date_paiement"], p["id"], "PAY", p))
    for a in _csv(lot / "avoirs.csv"):
        evenements.append((a["date"], a["id"], "AVO", a))
    evenements.sort(key=lambda e: (e[0], e[1]))
    for _, _, genre, r in evenements:
        if genre == "PAY":
            enregistrer_paiement(
                conn, client_id=r["client_id"] or None, date_paiement=r["date_paiement"],
                montant=lire_entier(r["montant"]), mode=r["mode"],
                reference_externe=r["reference_externe"],
                references_indiquees=[x for x in r["references_indiquees"].split(";") if x],
                acteur=SYSTEME, paiement_id=r["id"])
        else:
            enregistrer_avoir(conn, facture_id=r["facture_id"], date_avoir=r["date"],
                              montant=lire_entier(r["montant"]), motif=r["motif"],
                              acteur=SYSTEME, avoir_id=r["id"])
    _charger_etat_initial(conn, initial)
    with transaction(conn):
        for prefixe, table in (("CLI", "clients"), ("PAY", "paiements"), ("AVO", "avoirs"),
                               ("ECH", "echeances"), ("ACC", "accords_echeancier"),
                               ("CTE", "contestations"), ("PRO", "promesses_paiement"),
                               ("REL", "relances"), ("IMP", "imports"),
                               ("MSG", "messages_entrants"), ("ENV", "envois_simules")):
            positionner_sequence(conn, prefixe, table)
    return {"portefeuille": rapport, "paiements": sum(1 for e in evenements if e[2] == "PAY"),
            "avoirs": sum(1 for e in evenements if e[2] == "AVO")}


def _charger_etat_initial(conn: sqlite3.Connection, initial: Path) -> None:
    with transaction(conn):
        for r in _csv(initial / "contestations.csv"):
            conn.execute(
                "INSERT INTO contestations(id, facture_id, echeance_id, motif, "
                "message_source_id, date_ouverture, statut, date_cloture) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (r["id"], r["facture_id"], r["echeance_id"] or None, r["motif"],
                 r["message_source_id"] or None, r["date_ouverture"], r["statut"],
                 r["date_cloture"] or None))
        for r in _csv(initial / "promesses_paiement.csv"):
            conn.execute(
                "INSERT INTO promesses_paiement(id, client_id, facture_id, date_promise, "
                "montant_promis, message_source_id, origine, statut) "
                "VALUES (?,?,?,?,?,?,'PROMESSE',?)",
                (r["id"], r["client_id"], r["facture_id"], r["date_promise"],
                 lire_entier(r["montant_promis"]) if r["montant_promis"] else None,
                 r["message_source_id"] or None, r["statut"]))
        clients = {r["id"]: r for r in conn.execute("SELECT * FROM clients")}
        for r in _csv(initial / "relances_historique.csv"):
            conn.execute(
                "INSERT INTO relances(id, client_id, canal, etape, date_prevue, date_envoi, "
                "statut, motif, contenu, cle_idempotence) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["id"], r["client_id"], r["canal"], r["etape"], r["date_prevue"],
                 r["date_envoi"] or None, r["statut"], r["motif"] or None, r["contenu"],
                 r["cle_idempotence"]))
            if r["statut"] == "ENVOYEE_SIM":
                c = clients[r["client_id"]]
                contenu = r["contenu"]
                objet = None
                if r["canal"] == "EMAIL" and contenu.startswith("Objet :"):
                    objet, _, contenu = contenu.partition("\n\n")
                    objet = objet[len("Objet :"):].strip()
                conn.execute(
                    "INSERT INTO envois_simules(id, relance_id, canal, destinataire, objet, "
                    "contenu, horodatage) VALUES (?,?,?,?,?,?,?)",
                    (f"ENV-{r['id'][4:]}", r["id"], r["canal"],
                     c["email"] if r["canal"] == "EMAIL" else c["whatsapp"], objet, contenu,
                     f"{r['date_envoi']}T09:00:00+01:00"))
        for r in _csv(initial / "relance_lignes_historique.csv"):
            conn.execute(
                "INSERT INTO relance_lignes(relance_id, echeance_id, etape_echeance, "
                "solde_au_moment_de_l_envoi) VALUES (?,?,?,?)",
                (r["relance_id"], r["echeance_id"], r["etape_echeance"],
                 lire_entier(r["solde_au_moment_de_l_envoi"])
                 if r["solde_au_moment_de_l_envoi"] else None))
    _ = clock  # l'horloge technique n'intervient pas dans le chargement
