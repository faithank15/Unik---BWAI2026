"""Import du portefeuille (spécification, section 8.1).

Fichiers : clients, preferences_contact (facultatif), factures, echeances et, facultatif,
accords_echeancier (les échéances de tranche y renvoient par `accord_id`).

- Un en-tête manquant ou inconnu rejette le fichier entier (400).
- L'empreinte SHA-256 des fichiers triés par nom rend l'import idempotent : un lot déjà
  importé répond DEJA_IMPORTE sans rien écrire.
- Le rejet se fait par ligne. Une facture n'est acceptée que si sa ligne est valide et que
  toutes ses échéances sont valides et totalisent son montant ; sinon la facture et ses
  échéances sont rejetées ensemble. Le rapport liste un rejet par cause (sur la ligne qui
  porte le défaut) ; les lignes rejetées par ricochet n'y figurent pas.
- `nb_lignes` compte les lignes de clients, préférences, factures et accords ; les échéances
  font partie de leur facture.

Codes de rejet supplémentaires à ceux du document de données : IDENTIFIANT_EXISTANT_DIFFERENT
(spécification), VALEUR_INVALIDE, FACTURE_INCONNUE et ACCORD_INCONNU (voir QUESTIONS.md).
"""
import csv
import hashlib
import io
import json
import sqlite3
from typing import Any

from app import clock
from app.db import prochain_id, transaction
from app.domain import imports as dom
from app.errors import FichierTropGros, Validation
from app.journal import Acteur, journaliser

TAILLE_MAX = 5 * 1024 * 1024


def empreinte(fichiers: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for nom in sorted(fichiers):
        h.update(nom.encode() + b"\0" + fichiers[nom] + b"\0")
    return h.hexdigest()


def _lire(nom: str, contenu: bytes) -> list[dict[str, str]]:
    if len(contenu) > TAILLE_MAX:
        raise FichierTropGros(f"Le fichier {nom} dépasse 5 Mo.")
    try:
        texte = contenu.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise Validation(f"Le fichier {nom} n'est pas en UTF-8.") from e
    lecteur = csv.DictReader(io.StringIO(texte, newline=""))
    entetes = lecteur.fieldnames or []
    attendus = dom.ENTETES[nom]
    facultatifs = dom.ENTETES_FACULTATIFS.get(nom, [])
    if (len(set(entetes)) != len(entetes) or not set(attendus) <= set(entetes)
            or not set(entetes) <= set(attendus) | set(facultatifs)):
        raise Validation(f"En-têtes invalides dans {nom}.csv : un en-tête manquant ou inconnu "
                         "rejette le fichier entier.",
                         {"fichier": f"{nom}.csv", "attendus": attendus,
                          "facultatifs": facultatifs, "recus": entetes})
    return [dom.nettoyer(r) for r in lecteur]


class _Rapport:
    def __init__(self) -> None:
        self.rejets: list[dict[str, Any]] = []
        self.unites_rejetees: set[tuple[str, str]] = set()

    def rejeter(self, nom: str, ligne: int, code: str, detail: str,
                unite: tuple[str, str] | None = None) -> None:
        self.rejets.append({"fichier": f"{nom}.csv", "ligne": ligne, "motif_code": code,
                            "detail": detail})
        if unite:
            self.unites_rejetees.add(unite)


def importer_portefeuille(conn: sqlite3.Connection, fichiers: dict[str, bytes],
                          acteur: Acteur) -> tuple[int, dict]:
    """Retourne (code HTTP, corps). 201 pour un import terminé, 200 pour DEJA_IMPORTE."""
    inconnus = set(fichiers) - set(dom.ENTETES)
    manquants = [n for n in dom.OBLIGATOIRES if n not in fichiers]
    if inconnus or manquants:
        raise Validation("Fichiers d'import invalides.", {
            "inconnus": sorted(inconnus), "manquants": manquants})
    lignes = {nom: _lire(nom, contenu) for nom, contenu in fichiers.items()}
    cle = empreinte(fichiers)

    with transaction(conn):
        deja = conn.execute("SELECT id, nb_lignes, nb_rejets FROM imports WHERE empreinte = ?",
                            (cle,)).fetchone()
        if deja:
            journaliser(conn, "IMPORT_DEJA_FAIT", "IMPORT", deja["id"], acteur=acteur)
            return 200, {"import_id": deja["id"], "statut": "DEJA_IMPORTE",
                         "nb_lignes": deja["nb_lignes"], "nb_rejets": deja["nb_rejets"]}
        rap = _Rapport()
        a_inserer = _valider(conn, lignes, rap)
        import_id = prochain_id(conn, "IMP")
        nb_lignes = sum(len(lignes.get(n, [])) for n in
                        ("clients", "preferences_contact", "factures", "accords_echeancier"))
        nb_rejetees = len(rap.unites_rejetees)
        corps = {"import_id": import_id, "statut": "TERMINE", "nb_lignes": nb_lignes,
                 "nb_acceptees": nb_lignes - nb_rejetees, "nb_rejets": len(rap.rejets),
                 "rejets": rap.rejets}
        conn.execute(
            "INSERT INTO imports(id, fichiers, empreinte, date_import, nb_lignes, nb_rejets, "
            "rapport) VALUES (?,?,?,?,?,?,?)",
            (import_id, json.dumps(sorted(f"{n}.csv" for n in fichiers)), cle,
             clock.date_reference(conn).isoformat(), nb_lignes, len(rap.rejets),
             json.dumps(rap.rejets, ensure_ascii=False)))
        _inserer(conn, a_inserer, import_id)
        journaliser(conn, "IMPORT_TERMINE", "IMPORT", import_id, acteur=acteur,
                    details={"nb_lignes": nb_lignes, "nb_acceptees": corps["nb_acceptees"],
                             "nb_rejets": len(rap.rejets)})
    return 201, corps


# ---- validation -------------------------------------------------------------------
def _tuple_client(r: dict) -> tuple:
    return (r["raison_sociale"], dom.vers_none(r["secteur"]), dom.vers_none(r["ville"]),
            dom.vers_none(r["email"]), dom.vers_none(r["whatsapp"]), int(r["actif"]))


def _tuple_facture(r: dict) -> tuple:
    taux = float(r["taux_penalite_retard"]) if r["taux_penalite_retard"] else None
    return (r["client_id"], r["numero"], r["date_emission"], int(r["montant_ttc"]),
            r["conditions_paiement"], taux, dom.vers_none(r["ref_facture_normalisee"]),
            r["statut_document"] or "VALIDEE")


def _tuple_ech(r: dict) -> tuple:
    return (r["facture_id"], int(r["rang"]), r["date_echeance"], int(r["montant_du"]),
            r["etat"], dom.vers_none(r["accord_id"]))


def _valider(conn: sqlite3.Connection, lignes: dict[str, list[dict]], rap: _Rapport) -> dict:
    sortie: dict[str, list[dict]] = {k: [] for k in dom.ENTETES}

    # -- clients
    clients_db = {r["id"]: (r["raison_sociale"], r["secteur"], r["ville"], r["email"],
                            r["whatsapp"], r["actif"]) for r in conn.execute(
        "SELECT * FROM clients")}
    raisons_db = {v[0]: k for k, v in clients_db.items()}
    vus_clients: dict[str, tuple] = {}
    for n, r in enumerate(lignes["clients"], 2):
        unite = ("clients", r["id"] or f"ligne{n}")
        vides = dom.champs_vides(r, ["id", "raison_sociale", "actif"])
        if vides:
            rap.rejeter("clients", n, "CHAMP_OBLIGATOIRE_VIDE",
                        f"Champ(s) obligatoire(s) vide(s) : {', '.join(vides)}.", unite)
            continue
        if r["actif"] not in ("0", "1"):
            rap.rejeter("clients", n, "VALEUR_INVALIDE", "actif doit valoir 0 ou 1.", unite)
            continue
        if r["whatsapp"] and not dom.RE_TELEPHONE.match(r["whatsapp"]):
            rap.rejeter("clients", n, "TELEPHONE_MAL_FORME",
                        f"whatsapp {r['whatsapp']} hors format (+229 suivi de 10 chiffres).",
                        unite)
            continue
        if r["email"] and not dom.RE_EMAIL.match(r["email"]):
            rap.rejeter("clients", n, "EMAIL_MAL_FORME", f"email {r['email']} invalide.", unite)
            continue
        t = _tuple_client(r)
        connu = clients_db.get(r["id"]) or vus_clients.get(r["id"])
        if connu is not None:
            code = "DOUBLON_EXACT" if tuple(connu) == t else "IDENTIFIANT_EXISTANT_DIFFERENT"
            rap.rejeter("clients", n, code,
                        f"Le client {r['id']} existe déjà"
                        f"{'' if code == 'DOUBLON_EXACT' else ' avec d autres valeurs'}.", unite)
            continue
        autre = raisons_db.get(r["raison_sociale"]) or next(
            (k for k, v in vus_clients.items() if v[0] == r["raison_sociale"]), None)
        if autre:
            rap.rejeter("clients", n, "IDENTIFIANT_EXISTANT_DIFFERENT",
                        f"La raison sociale existe déjà pour le client {autre}.", unite)
            continue
        vus_clients[r["id"]] = t
        sortie["clients"].append(r)
    clients_ok = set(clients_db) | set(vus_clients)

    # -- préférences de contact
    prefs_db = {r["client_id"]: (r["canal_prefere"], r["canaux_autorises"],
                                 r["consentement_relance"], r["interlocuteur"],
                                 r["jours_a_eviter"], r["plage_horaire"])
                for r in conn.execute("SELECT * FROM preferences_contact")}
    vus_prefs: dict[str, tuple] = {}
    for n, r in enumerate(lignes.get("preferences_contact", []), 2):
        unite = ("preferences_contact", r["client_id"] or f"ligne{n}")
        vides = dom.champs_vides(r, ["client_id", "canal_prefere", "canaux_autorises",
                                     "consentement_relance"])
        if vides:
            rap.rejeter("preferences_contact", n, "CHAMP_OBLIGATOIRE_VIDE",
                        f"Champ(s) obligatoire(s) vide(s) : {', '.join(vides)}.", unite)
            continue
        autorises = r["canaux_autorises"].split(";")
        if (r["canal_prefere"] not in dom.CANAUX or r["consentement_relance"] not in ("0", "1")
                or not set(autorises) <= dom.CANAUX):
            rap.rejeter("preferences_contact", n, "VALEUR_INVALIDE",
                        "Canal ou consentement invalide.", unite)
            continue
        if r["client_id"] not in clients_ok:
            rap.rejeter("preferences_contact", n, "CLIENT_INCONNU",
                        f"Le client {r['client_id']} est inconnu.", unite)
            continue
        jours = dom.lire_jours_a_eviter(r.get("jours_a_eviter", ""))
        plage = r.get("plage_horaire") or "AUCUNE"
        inter = dom.nettoyer_interlocuteur(r["interlocuteur"])
        if (jours is None or plage not in dom.PLAGES_HORAIRES
                or (inter and len(inter) > dom.INTERLOCUTEUR_MAX)):
            rap.rejeter("preferences_contact", n, "VALEUR_INVALIDE",
                        "jours_a_eviter (lundi à samedi), plage_horaire (MATIN, APRES_MIDI, "
                        f"AUCUNE) ou interlocuteur (80 caractères) invalide pour "
                        f"{r['client_id']}.", unite)
            continue
        r["jours_a_eviter"], r["plage_horaire"], r["interlocuteur"] = jours, plage, inter or ""
        t = (r["canal_prefere"], r["canaux_autorises"], int(r["consentement_relance"]),
             inter, jours, plage)
        connu = prefs_db.get(r["client_id"]) or vus_prefs.get(r["client_id"])
        if connu is not None:
            code = "DOUBLON_EXACT" if tuple(connu) == t else "IDENTIFIANT_EXISTANT_DIFFERENT"
            rap.rejeter("preferences_contact", n, code,
                        f"Préférences déjà présentes pour {r['client_id']}.", unite)
            continue
        vus_prefs[r["client_id"]] = t
        sortie["preferences_contact"].append(r)

    # -- factures (contrôles propres à la ligne)
    fact_db = {r["id"]: (r["client_id"], r["numero"], r["date_emission"], r["montant_ttc"],
                         r["conditions_paiement"], r["taux_penalite_retard"],
                         r["ref_facture_normalisee"], r["statut_document"])
               for r in conn.execute("SELECT * FROM factures")}
    numeros_db = {(v[0], v[1]): k for k, v in fact_db.items()}
    vues_fact: dict[str, tuple] = {}
    numeros_vus: dict[tuple, str] = {}
    emissions: dict[str, str] = {k: v[2] for k, v in fact_db.items()}
    lignes_fact: dict[str, int] = {}
    factures_ok: dict[str, dict] = {}
    rejetees: set[str] = set()
    for n, r in enumerate(lignes["factures"], 2):
        unite = ("factures", r["id"] or f"ligne{n}")
        vides = dom.champs_vides(r, ["id", "client_id", "numero", "date_emission",
                                     "montant_ttc", "conditions_paiement"])
        if vides:
            rap.rejeter("factures", n, "CHAMP_OBLIGATOIRE_VIDE",
                        f"Champ(s) obligatoire(s) vide(s) : {', '.join(vides)}.", unite)
            rejetees.add(r["id"])
            continue
        if dom.lire_date(r["date_emission"]) is None:
            rap.rejeter("factures", n, "DATE_INVALIDE",
                        f"date_emission {r['date_emission']} n'existe pas ou est mal "
                        "formatée.", unite)
            rejetees.add(r["id"])
            continue
        montant = dom.lire_entier(r["montant_ttc"])
        if montant is None or montant <= 0:
            rap.rejeter("factures", n, "MONTANT_NON_POSITIF",
                        f"montant_ttc doit être un entier strictement positif (valeur : "
                        f"{r['montant_ttc']}).", unite)
            rejetees.add(r["id"])
            continue
        statut_doc = r["statut_document"] or "VALIDEE"
        taux_ok = not r["taux_penalite_retard"] or _decimal_ok(r["taux_penalite_retard"])
        if (r["conditions_paiement"] not in dom.CONDITIONS
                or statut_doc not in ("VALIDEE", "ANNULEE") or not taux_ok):
            rap.rejeter("factures", n, "VALEUR_INVALIDE",
                        "Condition de paiement, statut ou taux de pénalité invalide.", unite)
            rejetees.add(r["id"])
            continue
        if r["client_id"] not in clients_ok:
            rap.rejeter("factures", n, "CLIENT_INCONNU",
                        f"Le client {r['client_id']} est absent du fichier clients et de la "
                        "base.", unite)
            rejetees.add(r["id"])
            continue
        r["statut_document"] = statut_doc
        t = _tuple_facture(r)
        connu = fact_db.get(r["id"]) or vues_fact.get(r["id"])
        if connu is not None:
            code = "DOUBLON_EXACT" if tuple(connu) == t else "IDENTIFIANT_EXISTANT_DIFFERENT"
            rap.rejeter("factures", n, code,
                        f"La facture {r['id']} existe déjà"
                        f"{'' if code == 'DOUBLON_EXACT' else ' avec d autres valeurs'}.", unite)
            rejetees.add(r["id"])  # ses échéances sont rejetées par ricochet, sans rapport
            continue
        autre = numeros_db.get((r["client_id"], r["numero"])) or numeros_vus.get(
            (r["client_id"], r["numero"]))
        if autre:
            rap.rejeter("factures", n, "DOUBLON_NUMERO",
                        f"Le client {r['client_id']} a déjà une facture numéro {r['numero']} "
                        f"({autre}).", unite)
            rejetees.add(r["id"])
            continue
        vues_fact[r["id"]] = t
        numeros_vus[(r["client_id"], r["numero"])] = r["id"]
        emissions[r["id"]] = r["date_emission"]
        lignes_fact[r["id"]] = n
        factures_ok[r["id"]] = r

    # -- accords
    acc_db = {r["id"]: (r["facture_id"], r["date_accord"], r["statut"], r["nb_tranches"])
              for r in conn.execute("SELECT * FROM accords_echeancier")}
    accords_ok: dict[str, dict] = {}
    for n, r in enumerate(lignes.get("accords_echeancier", []), 2):
        unite = ("accords_echeancier", r["id"] or f"ligne{n}")
        vides = dom.champs_vides(r, ["id", "facture_id", "date_accord", "statut",
                                     "nb_tranches"])
        if vides:
            rap.rejeter("accords_echeancier", n, "CHAMP_OBLIGATOIRE_VIDE",
                        f"Champ(s) obligatoire(s) vide(s) : {', '.join(vides)}.", unite)
            continue
        nb = dom.lire_entier(r["nb_tranches"])
        if dom.lire_date(r["date_accord"]) is None:
            rap.rejeter("accords_echeancier", n, "DATE_INVALIDE",
                        f"date_accord {r['date_accord']} invalide.", unite)
            continue
        if r["statut"] not in dom.STATUTS_ACCORD or nb is None or nb < 2:
            rap.rejeter("accords_echeancier", n, "VALEUR_INVALIDE",
                        "Statut ou nombre de tranches invalide.", unite)
            continue
        if r["facture_id"] not in fact_db and r["facture_id"] not in factures_ok:
            rap.rejeter("accords_echeancier", n, "FACTURE_INCONNUE",
                        f"La facture {r['facture_id']} est inconnue.", unite)
            continue
        connu = acc_db.get(r["id"])
        t = (r["facture_id"], r["date_accord"], r["statut"], nb)
        if connu is not None or r["id"] in accords_ok:
            code = "DOUBLON_EXACT" if connu is not None and tuple(connu) == t \
                else "IDENTIFIANT_EXISTANT_DIFFERENT"
            rap.rejeter("accords_echeancier", n, code, f"L'accord {r['id']} existe déjà.",
                        unite)
            continue
        accords_ok[r["id"]] = r

    # -- échéances
    ech_db = {r["id"]: (r["facture_id"], r["rang"], r["date_echeance"], r["montant_du"],
                        r["etat"], r["accord_id"]) for r in conn.execute(
        "SELECT * FROM echeances")}
    ech_ok: dict[str, dict] = {}
    echs_par_facture: dict[str, list[dict]] = {}
    ricochet: set[str] = set()
    for n, r in enumerate(lignes["echeances"], 2):
        fid = r["facture_id"]
        if fid in rejetees:
            continue  # rejetée par ricochet avec sa facture
        unite = ("factures", fid)
        vides = dom.champs_vides(r, ["id", "facture_id", "rang", "date_echeance",
                                     "montant_du", "etat"])
        if vides:
            rap.rejeter("echeances", n, "CHAMP_OBLIGATOIRE_VIDE",
                        f"Champ(s) obligatoire(s) vide(s) : {', '.join(vides)}.",
                        unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        if dom.lire_date(r["date_echeance"]) is None:
            rap.rejeter("echeances", n, "DATE_INVALIDE",
                        f"date_echeance {r['date_echeance']} est mal formatée (attendu "
                        "AAAA-MM-JJ) ou inexistante.", unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        montant = dom.lire_entier(r["montant_du"])
        rang = dom.lire_entier(r["rang"])
        if montant is None or montant <= 0:
            rap.rejeter("echeances", n, "MONTANT_NON_POSITIF",
                        f"montant_du doit être un entier strictement positif (valeur : "
                        f"{r['montant_du']}).", unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        if rang is None or rang < 1 or r["etat"] not in ("ACTIVE", "REMPLACEE"):
            rap.rejeter("echeances", n, "VALEUR_INVALIDE", "Rang ou état invalide.",
                        unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        if fid not in emissions:
            rap.rejeter("echeances", n, "FACTURE_INCONNUE",
                        f"La facture {fid} est inconnue.")
            continue
        if r["date_echeance"] < emissions[fid]:
            rap.rejeter("echeances", n, "ECHEANCE_AVANT_EMISSION",
                        f"date_echeance {r['date_echeance']} est antérieure à date_emission "
                        f"{emissions[fid]}.", unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        if r["accord_id"] and r["accord_id"] not in acc_db and r["accord_id"] not in accords_ok:
            rap.rejeter("echeances", n, "ACCORD_INCONNU",
                        f"L'accord {r['accord_id']} est inconnu.",
                        unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        t = _tuple_ech(r)
        connu = ech_db.get(r["id"])
        if connu is not None or r["id"] in ech_ok:
            code = "DOUBLON_EXACT" if connu is not None and tuple(connu) == t \
                else "IDENTIFIANT_EXISTANT_DIFFERENT"
            rap.rejeter("echeances", n, code, f"L'échéance {r['id']} existe déjà.",
                        unite if fid in factures_ok else None)
            ricochet.add(fid)
            continue
        ech_ok[r["id"]] = r
        echs_par_facture.setdefault(fid, []).append(r)

    # -- cohérence : somme des échéances ACTIVE = montant_ttc
    for fid, r in list(factures_ok.items()):
        if fid in ricochet:
            rap.unites_rejetees.add(("factures", fid))
            rejetees.add(fid)
            del factures_ok[fid]
            continue
        somme = sum(int(e["montant_du"]) for e in echs_par_facture.get(fid, [])
                    if e["etat"] == "ACTIVE")
        if somme != int(r["montant_ttc"]):
            rap.rejeter("factures", lignes_fact[fid], "SOMME_ECHEANCES_DIFFERENTE",
                        f"La somme des échéances ({somme}) diffère du montant_ttc "
                        f"({r['montant_ttc']}).", ("factures", fid))
            rejetees.add(fid)
            del factures_ok[fid]

    sortie["factures"] = list(factures_ok.values())
    sortie["accords_echeancier"] = [a for a in accords_ok.values()
                                    if a["facture_id"] in fact_db or a["facture_id"] in factures_ok]
    for fid in factures_ok:
        sortie["echeances"] += echs_par_facture.get(fid, [])
    # Échéances nouvelles d'une facture déjà en base (hors rejet) : conservées.
    for fid, es in echs_par_facture.items():
        if fid in fact_db:
            sortie["echeances"] += es
    return sortie


def _decimal_ok(texte: str) -> bool:
    try:
        float(texte)
        return True
    except ValueError:
        return False


# ---- insertion --------------------------------------------------------------------
def _inserer(conn: sqlite3.Connection, s: dict, import_id: str) -> None:
    for r in s["clients"]:
        conn.execute("INSERT INTO clients(id, raison_sociale, secteur, ville, email, whatsapp, "
                     "actif) VALUES (?,?,?,?,?,?,?)",
                     (r["id"], r["raison_sociale"], dom.vers_none(r["secteur"]),
                      dom.vers_none(r["ville"]), dom.vers_none(r["email"]),
                      dom.vers_none(r["whatsapp"]), int(r["actif"])))
    aujourdhui = clock.date_reference(conn).isoformat()     # date métier : reset reproductible
    for r in s["preferences_contact"]:
        provenance = {champ: {"source": "IMPORT", "date": aujourdhui} for champ in (
            "canal_prefere", "jours_a_eviter", "plage_horaire", "interlocuteur")}
        conn.execute("INSERT INTO preferences_contact(client_id, canal_prefere, "
                     "canaux_autorises, consentement_relance, interlocuteur, jours_a_eviter, "
                     "plage_horaire, provenance) VALUES (?,?,?,?,?,?,?,?)",
                     (r["client_id"], r["canal_prefere"], r["canaux_autorises"],
                      int(r["consentement_relance"]), dom.vers_none(r["interlocuteur"]),
                      r["jours_a_eviter"], r["plage_horaire"],
                      json.dumps(provenance, sort_keys=True)))
    for r in s["factures"]:
        conn.execute(
            "INSERT INTO factures(id, client_id, numero, date_emission, montant_ttc, "
            "conditions_paiement, taux_penalite_retard, ref_facture_normalisee, "
            "statut_document, import_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["client_id"], r["numero"], r["date_emission"], int(r["montant_ttc"]),
             r["conditions_paiement"],
             float(r["taux_penalite_retard"]) if r["taux_penalite_retard"] else None,
             dom.vers_none(r["ref_facture_normalisee"]), r["statut_document"], import_id))
    for r in s["accords_echeancier"]:
        conn.execute("INSERT INTO accords_echeancier(id, facture_id, date_accord, statut, "
                     "nb_tranches) VALUES (?,?,?,?,?)",
                     (r["id"], r["facture_id"], r["date_accord"], r["statut"],
                      int(r["nb_tranches"])))
    for r in s["echeances"]:
        conn.execute("INSERT INTO echeances(id, facture_id, rang, date_echeance, montant_du, "
                     "etat, accord_id) VALUES (?,?,?,?,?,?,?)",
                     (r["id"], r["facture_id"], int(r["rang"]), r["date_echeance"],
                      int(r["montant_du"]), r["etat"], dom.vers_none(r["accord_id"])))
