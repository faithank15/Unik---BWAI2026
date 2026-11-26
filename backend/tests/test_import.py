"""Import du portefeuille : lot nominal, lot défectueux, idempotence, rejets motivés."""
import sqlite3

import pytest

from app.db import connecter
from tests.aides import compter, fichiers_defectueux, fichiers_nominal
from tests.verite import lire_csv


@pytest.fixture
def vide(client_api, entetes_gestionnaire):
    """API sur une base vide : l'import part de zéro."""
    return client_api, entetes_gestionnaire


def importer(api, entetes, fichiers):
    return api.post("/api/imports", files=fichiers, headers=entetes)


def test_I01_lot_nominal(vide, reglages):
    api, h = vide
    r = importer(api, h, fichiers_nominal())
    assert r.status_code == 201, r.text
    corps = r.json()
    assert corps["statut"] == "TERMINE" and corps["nb_rejets"] == 0
    assert corps["import_id"] == "IMP-0001"
    c = connecter(reglages.database_path)
    assert (compter(c, "clients"), compter(c, "factures"), compter(c, "echeances")) == \
        (30, 120, 147)
    assert compter(c, "preferences_contact") == 30 and compter(c, "accords_echeancier") == 6
    assert c.execute("SELECT COUNT(*) FROM factures WHERE import_id = 'IMP-0001'"
                     ).fetchone()[0] == 120
    assert c.execute("SELECT type_evenement FROM journal WHERE type_evenement = "
                     "'IMPORT_TERMINE'").fetchone() is not None


def test_I03_meme_lot_deux_fois_aucun_doublon(vide, reglages):
    api, h = vide
    importer(api, h, fichiers_nominal())
    c = connecter(reglages.database_path)
    avant = {t: compter(c, t) for t in ("clients", "factures", "echeances", "imports")}
    r = importer(api, h, fichiers_nominal())
    assert r.status_code == 200
    assert r.json()["statut"] == "DEJA_IMPORTE" and r.json()["import_id"] == "IMP-0001"
    assert {t: compter(c, t) for t in avant} == avant
    assert c.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = 'IMPORT_DEJA_FAIT'"
                     ).fetchone()[0] == 1


def test_I04_fichier_modifie_seule_la_ligne_nouvelle_est_traitee(vide, reglages):
    api, h = vide
    importer(api, h, fichiers_nominal())
    f = fichiers_nominal()
    nom, contenu, mime = f["clients"]
    nouveau = contenu + (b"CLI-0031,Cabinet Nouveau Venu,BTP,Cotonou,"
                         b"contact@client-0031.example,+2290100000031,1\n")
    f["clients"] = (nom, nouveau, mime)
    r = importer(api, h, f)
    assert r.status_code == 201
    corps = r.json()
    assert corps["import_id"] == "IMP-0002"
    c = connecter(reglages.database_path)
    assert compter(c, "clients") == 31 and compter(c, "factures") == 120
    motifs = {x["motif_code"] for x in corps["rejets"]}
    assert motifs == {"DOUBLON_EXACT"}  # toutes les anciennes lignes sont reconnues


def test_I05_identifiant_existant_avec_donnees_differentes(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    f = fichiers_nominal()
    nom, contenu, mime = f["clients"]
    lignes = contenu.decode().splitlines()
    lignes[1] = lignes[1].replace("Cotonou", "Parakou", 1)
    f["clients"] = (nom, ("\n".join(lignes) + "\n").encode(), mime)
    r = importer(api, h, f)
    assert r.status_code == 201
    codes = [(x["ligne"], x["motif_code"]) for x in r.json()["rejets"]
             if x["fichier"] == "clients.csv"]
    assert (2, "IDENTIFIANT_EXISTANT_DIFFERENT") in codes


def test_I06_fichier_trop_gros_refuse_sans_effet(vide, reglages):
    api, h = vide
    f = fichiers_nominal()
    nom, contenu, mime = f["clients"]
    f["clients"] = (nom, contenu + b"#" * (5 * 1024 * 1024 + 1), mime)
    r = importer(api, h, f)
    assert r.status_code == 413 and r.json()["erreur"]["code"] == "FICHIER_TROP_GROS"
    assert compter(connecter(reglages.database_path), "clients") == 0


def test_entete_inconnu_ou_manquant_rejette_le_fichier_entier(vide, reglages):
    api, h = vide
    f = fichiers_nominal()
    nom, contenu, mime = f["factures"]
    f["factures"] = (nom, contenu.replace(b"montant_ttc", b"montant_ht", 1), mime)
    r = importer(api, h, f)
    assert r.status_code == 400 and r.json()["erreur"]["code"] == "VALIDATION"
    assert "factures.csv" in r.json()["erreur"]["details"]["fichier"]
    f = fichiers_nominal()
    nom, contenu, mime = f["echeances"]
    f["echeances"] = (nom, contenu.replace(b",accord_id", b"", 1), mime)
    assert importer(api, h, f).status_code == 400
    assert compter(connecter(reglages.database_path), "factures") == 0


def test_fichier_obligatoire_absent(vide):
    api, h = vide
    r = importer(api, h, fichiers_nominal(sauf=("echeances",)))
    assert r.status_code == 400 and r.json()["erreur"]["code"] == "VALIDATION"


def test_fichier_non_utf8(vide):
    api, h = vide
    f = fichiers_nominal()
    nom, contenu, mime = f["clients"]
    f["clients"] = (nom, b"\xff\xfe" + contenu, mime)
    assert importer(api, h, f).status_code == 400


def test_import_exige_un_jeton(client_api):
    assert client_api.post("/api/imports", files=fichiers_nominal()).status_code == 401


def test_I09_montant_au_mauvais_format_date_invalide_echeance_avant_emission(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    f = {"clients": ("clients.csv", b"id,raison_sociale,secteur,ville,email,whatsapp,actif\n",
                     "text/csv"),
         "factures": ("factures.csv",
                      b"id,client_id,numero,date_emission,montant_ttc,conditions_paiement,"
                      b"taux_penalite_retard,ref_facture_normalisee,statut_document\n"
                      b"FAC-2026-7001,CLI-0001,X1,2026-12-01,12abc,30_JOURS,,,VALIDEE\n"
                      b"FAC-2026-7002,CLI-0001,X2,2026-13-01,1000,30_JOURS,,,VALIDEE\n"
                      b"FAC-2026-7003,CLI-0001,X3,2026-12-01,1000,30_JOURS,,,VALIDEE\n",
                      "text/csv"),
         "echeances": ("echeances.csv",
                       b"id,facture_id,rang,date_echeance,montant_du,etat,accord_id\n"
                       b"ECH-7003,FAC-2026-7003,1,2026-11-30,1000,ACTIVE,\n", "text/csv")}
    corps = importer(api, h, f).json()
    codes = {(x["fichier"], x["ligne"]): x["motif_code"] for x in corps["rejets"]}
    assert codes[("factures.csv", 2)] == "MONTANT_NON_POSITIF"
    assert codes[("factures.csv", 3)] == "DATE_INVALIDE"
    assert codes[("echeances.csv", 2)] == "ECHEANCE_AVANT_EMISSION"
    assert corps["nb_acceptees"] == 0


def test_facture_sans_echeance_rejetee_somme_differente(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    f = {"clients": ("clients.csv", b"id,raison_sociale,secteur,ville,email,whatsapp,actif\n",
                     "text/csv"),
         "factures": ("factures.csv",
                      b"id,client_id,numero,date_emission,montant_ttc,conditions_paiement,"
                      b"taux_penalite_retard,ref_facture_normalisee,statut_document\n"
                      b"FAC-2026-7010,CLI-0002,Z9,2026-12-01,5000,30_JOURS,,,VALIDEE\n",
                      "text/csv"),
         "echeances": ("echeances.csv",
                       b"id,facture_id,rang,date_echeance,montant_du,etat,accord_id\n",
                       "text/csv")}
    corps = importer(api, h, f).json()
    assert [x["motif_code"] for x in corps["rejets"]] == ["SOMME_ECHEANCES_DIFFERENTE"]


def test_S02_lot_defectueux_apres_le_nominal(vide, reglages):
    api, h = vide
    importer(api, h, fichiers_nominal())
    r = importer(api, h, fichiers_defectueux())
    assert r.status_code == 201
    corps = r.json()
    attendus = lire_csv("lot_defectueux/rejets_attendus.csv")
    obtenus = sorted((x["fichier"], x["ligne"], x["motif_code"]) for x in corps["rejets"])
    voulus = sorted((a["fichier"], int(a["ligne"]), a["motif_code"]) for a in attendus)
    assert obtenus == voulus
    assert (corps["nb_lignes"], corps["nb_acceptees"], corps["nb_rejets"]) == (25, 10, 15)
    c = connecter(reglages.database_path)
    assert compter(c, "clients") == 32 and compter(c, "factures") == 128
    ids = [r[0] for r in c.execute("SELECT id FROM factures WHERE id LIKE 'FAC-2026-90%' "
                                   "ORDER BY id")]
    assert ids == [f"FAC-2026-{n}" for n in range(9001, 9009)]
    # le rapport est conservé et consultable
    d = api.get(f"/api/imports/{corps['import_id']}", headers=h).json()
    assert len(d["rejets"]) == 15
    liste = api.get("/api/imports", headers=h).json()
    assert liste["total"] == 2


def test_lot_defectueux_rejoue_est_reconnu(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    importer(api, h, fichiers_defectueux())
    r = importer(api, h, fichiers_defectueux())
    assert r.status_code == 200 and r.json()["statut"] == "DEJA_IMPORTE"


def test_import_est_atomique(reglages, monkeypatch):
    """Une erreur pendant l'insertion annule tout : aucune ligne, aucun import enregistré."""
    from app.journal import SYSTEME
    from app.security import Utilisateur  # noqa: F401
    from app.services import imports as svc

    def boum(*a, **k):
        raise RuntimeError("panne pendant l'insertion")

    c = connecter(reglages.database_path)
    monkeypatch.setattr(svc, "_inserer", boum)
    f = {n: v[1] for n, v in fichiers_nominal().items()}
    with pytest.raises(RuntimeError):
        svc.importer_portefeuille(c, f, SYSTEME)
    assert compter(c, "clients") == 0 and compter(c, "imports") == 0


def test_cle_etrangere_non_contournee(reglages):
    c = connecter(reglages.database_path)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO factures(id, client_id, numero, date_emission, montant_ttc, "
                  "conditions_paiement) VALUES ('F','CLI-X','1','2026-01-01',1,'COMPTANT')")


def _lot(clients=b"", prefs=None, factures=b"", echeances=b"", accords=None):
    f = {"clients": ("clients.csv", b"id,raison_sociale,secteur,ville,email,whatsapp,actif\n"
                     + clients, "text/csv"),
         "factures": ("factures.csv",
                      b"id,client_id,numero,date_emission,montant_ttc,conditions_paiement,"
                      b"taux_penalite_retard,ref_facture_normalisee,statut_document\n"
                      + factures, "text/csv"),
         "echeances": ("echeances.csv",
                       b"id,facture_id,rang,date_echeance,montant_du,etat,accord_id\n"
                       + echeances, "text/csv")}
    if prefs is not None:
        f["preferences_contact"] = ("preferences_contact.csv",
                                    b"client_id,canal_prefere,canaux_autorises,"
                                    b"consentement_relance,interlocuteur\n" + prefs, "text/csv")
    if accords is not None:
        f["accords_echeancier"] = ("accords_echeancier.csv",
                                   b"id,facture_id,date_accord,statut,nb_tranches\n" + accords,
                                   "text/csv")
    return f


def test_rejets_clients_preferences_et_accords(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    lot = _lot(
        clients=(b"CLI-8001,Cabinet Un,BTP,Cotonou,a@b.example,+2290100008001,1\n"
                 b"CLI-8002,,BTP,Cotonou,,,1\n"
                 b"CLI-8003,Cabinet Trois,BTP,Cotonou,,,2\n"
                 b"CLI-0001,Autre Nom,BTP,Cotonou,,,1\n"),
        prefs=(b"CLI-8001,WHATSAPP,WHATSAPP;EMAIL,1,M. Un\n"
               b"CLI-9999,WHATSAPP,WHATSAPP,1,\n"
               b"CLI-8001,SMS,WHATSAPP,1,\n"
               b",WHATSAPP,WHATSAPP,1,\n"),
        accords=(b"ACC-8001,FAC-2026-9999,2026-12-01,ACCEPTE,3\n"
                 b"ACC-8002,FAC-2026-0001,2026-13-01,ACCEPTE,3\n"
                 b"ACC-8003,FAC-2026-0001,2026-12-01,ACCEPTE,1\n"
                 b"ACC-8004,FAC-2026-0001,2026-12-01,PROPOSE,3\n"))
    corps = importer(api, h, lot).json()
    par = {(x["fichier"], x["ligne"]): x["motif_code"] for x in corps["rejets"]}
    assert par[("clients.csv", 3)] == "CHAMP_OBLIGATOIRE_VIDE"
    assert par[("clients.csv", 4)] == "VALEUR_INVALIDE"
    assert par[("clients.csv", 5)] == "IDENTIFIANT_EXISTANT_DIFFERENT"
    assert ("clients.csv", 2) not in par
    assert par[("preferences_contact.csv", 3)] == "CLIENT_INCONNU"
    assert par[("preferences_contact.csv", 4)] == "VALEUR_INVALIDE"
    assert par[("preferences_contact.csv", 5)] == "CHAMP_OBLIGATOIRE_VIDE"
    assert par[("accords_echeancier.csv", 2)] == "FACTURE_INCONNUE"
    assert par[("accords_echeancier.csv", 3)] == "DATE_INVALIDE"
    assert par[("accords_echeancier.csv", 4)] == "VALEUR_INVALIDE"
    assert ("accords_echeancier.csv", 5) not in par


def test_echeance_orpheline_et_accord_inconnu(vide):
    api, h = vide
    importer(api, h, fichiers_nominal())
    lot = _lot(
        factures=b"FAC-2026-8101,CLI-0001,N1,2026-12-01,1000,30_JOURS,,,VALIDEE\n",
        echeances=(b"ECH-8101,FAC-2026-8101,1,2026-12-31,1000,ACTIVE,ACC-9999\n"
                   b"ECH-8102,FAC-2026-8888,1,2026-12-31,1000,ACTIVE,\n"
                   b"ECH-8103,FAC-2026-8101,0,2026-12-31,1000,ACTIVE,\n"))
    corps = importer(api, h, lot).json()
    par = {(x["fichier"], x["ligne"]): x["motif_code"] for x in corps["rejets"]}
    assert par[("echeances.csv", 2)] == "ACCORD_INCONNU"
    assert par[("echeances.csv", 3)] == "FACTURE_INCONNUE"
    assert par[("echeances.csv", 4)] == "VALEUR_INVALIDE"
    assert corps["nb_acceptees"] == 0  # la facture est rejetée par ricochet


def test_import_de_fichier_d_avoirs(api, gest, db_chargee):
    csv = ("id,facture_id,date,montant,motif\n"
           ",FAC-2026-0062,2026-12-15,5000,remise\n"
           ",FAC-2026-0062,2026-12-15,5000,remise\n"
           ",FAC-2026-9999,2026-12-15,5000,remise\n"
           ",FAC-2026-0062,2026-12-15,999999999,trop\n"
           ",FAC-2026-0062,2026-12-15,abc,x\n")
    r = api.post("/api/avoirs/import", headers=gest,
                 files={"fichier": ("avoirs.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    rap = r.json()
    assert (rap["enregistres"], rap["rejoues"]) == (1, 1) and len(rap["rejets"]) == 3
    assert {x["motif_code"] for x in rap["rejets"]} == {"INTROUVABLE", "AVOIR_SUPERIEUR_AU_SOLDE",
                                                         "VALIDATION"}
    assert compter(db_chargee, "avoirs") == 6


def test_import_de_paiements_entetes_invalides(api, gest):
    r = api.post("/api/paiements/import", headers=gest,
                 files={"fichier": ("p.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 400
