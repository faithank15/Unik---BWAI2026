"""Préférences de contact gérées par le gestionnaire (extension IA, section 1) : jours à éviter,
plage horaire, interlocuteur, provenance, import et effet sur le calendrier des relances."""
import io
import json

import pytest

from app.domain import imports as dom_imp
from app.domain.calendrier import indices_jours_evites, prochain_jour_permis
from tests.aides_relances import changer_date, envoyer, planifier, relances


def prefs(api, gest, client="CLI-0001"):
    return api.get(f"/api/clients/{client}", headers=gest).json()["preferences"]


# ---- règle pure ------------------------------------------------------------------------
def test_un_jour_a_eviter_se_traite_comme_un_jour_non_ouvre():
    from datetime import date
    mardi = date(2026, 12, 22)
    assert prochain_jour_permis(mardi, set(), {1}) == date(2026, 12, 23)
    assert prochain_jour_permis(mardi, set(), ()) == mardi
    # vendredi évité + samedi évité + dimanche non ouvré : reporté au lundi
    assert prochain_jour_permis(date(2026, 12, 18), set(), {4, 5}) == date(2026, 12, 21)


def test_conversion_des_noms_de_jours():
    assert indices_jours_evites("MARDI;VENDREDI") == {1, 4}
    assert indices_jours_evites(["SAMEDI"]) == {5} and indices_jours_evites("") == frozenset()
    assert indices_jours_evites(None) == frozenset()


def test_lecture_des_jours_dans_une_liste_fermee():
    assert dom_imp.lire_jours_a_eviter("VENDREDI;MARDI;MARDI") == "MARDI;VENDREDI"
    assert dom_imp.lire_jours_a_eviter("") == ""
    assert dom_imp.lire_jours_a_eviter("DIMANCHE") is None      # déjà exclu
    assert dom_imp.lire_jours_a_eviter("MARDI;JOUR") is None


def test_interlocuteur_nettoye_sans_caracteres_de_controle():
    assert dom_imp.nettoyer_interlocuteur("  M.\x00  Roméo\n\tGbènami \x07") == "M. Roméo Gbènami"
    assert dom_imp.nettoyer_interlocuteur("\x01\x02") is None and \
        dom_imp.nettoyer_interlocuteur(None) is None


# ---- saisie par le gestionnaire --------------------------------------------------------
def test_defauts_sans_jour_exclu_ni_plage(api, gest):
    p = prefs(api, gest)
    assert p["jours_a_eviter"] == [] and p["plage_horaire"] == "AUCUNE"
    assert p["provenance"]["canal_prefere"]["source"] == "IMPORT"


def test_le_gestionnaire_renseigne_les_preferences_avec_provenance_et_journal(
        api, gest, db_chargee):
    r = api.put("/api/clients/CLI-0001/preferences", headers=gest, json={
        "canal_prefere": "EMAIL", "jours_a_eviter": ["VENDREDI", "MARDI"],
        "plage_horaire": "MATIN", "interlocuteur": "Mme\x00 Awa   Soglo"})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["jours_a_eviter"] == ["MARDI", "VENDREDI"] and corps["plage_horaire"] == "MATIN"
    assert corps["interlocuteur"] == "Mme Awa Soglo"
    p = prefs(api, gest)
    assert p["provenance"]["jours_a_eviter"]["source"] == "GESTIONNAIRE"
    assert p["provenance"]["plage_horaire"]["date"] == "2026-12-15"
    assert p["provenance"]["canal_prefere"]["source"] == "GESTIONNAIRE"   # changé WHATSAPP -> EMAIL
    evt = db_chargee.execute("SELECT avant, apres, acteur_id FROM journal WHERE type_evenement = "
                             "'PREFERENCES_MODIFIEES' AND objet_id = 'CLI-0001'").fetchone()
    assert json.loads(evt["avant"])["preferences"]["canal_prefere"] == "WHATSAPP"
    apres = json.loads(evt["apres"])
    assert apres["canal_prefere"] == "EMAIL" and apres["jours_a_eviter"] == "MARDI;VENDREDI"
    assert evt["acteur_id"] == "USR-0001"


def test_une_valeur_inchangee_garde_sa_provenance(api, gest):
    api.put("/api/clients/CLI-0001/preferences", headers=gest, json={"plage_horaire": "MATIN"})
    avant = prefs(api, gest)["provenance"]
    api.put("/api/clients/CLI-0001/preferences", headers=gest, json={"plage_horaire": "MATIN"})
    assert prefs(api, gest)["provenance"] == avant
    assert avant["interlocuteur"]["source"] == "IMPORT"          # jamais touché


@pytest.mark.parametrize("corps", [
    {"jours_a_eviter": ["DIMANCHE"]}, {"jours_a_eviter": ["MARDI", "FUNDI"]},
    {"plage_horaire": "SOIR"}, {"interlocuteur": "x" * 81}, {"canal_prefere": "SMS"},
])
def test_valeurs_hors_listes_fermees_refusees(api, gest, corps):
    r = api.put("/api/clients/CLI-0001/preferences", headers=gest, json=corps)
    assert r.status_code == 400 and r.json()["erreur"]["code"] == "VALIDATION"
    assert prefs(api, gest)["plage_horaire"] == "AUCUNE"


def test_les_preferences_ne_sont_jamais_un_prerequis(api, gest):
    """Un client dont seules les anciennes préférences existent reste relancé sans jour exclu."""
    planifier(api, gest)
    assert any(x["client_id"] == "CLI-0001" for x in relances(api, gest, date="2026-12-15"))


def test_preferences_exigent_un_jeton(api):
    assert api.put("/api/clients/CLI-0001/preferences", json={}).status_code == 401


# ---- import ----------------------------------------------------------------------------
def _lot(entete_prefs, ligne_prefs):
    clients = ("id,raison_sociale,secteur,ville,email,whatsapp,actif\n"
               "CLI-9001,Test SARL,Négoce,Cotonou,contact@client-9001.example,+2290100000001,1\n")
    factures = ("id,client_id,numero,date_emission,montant_ttc,conditions_paiement,"
                "taux_penalite_retard,ref_facture_normalisee,statut_document\n")
    echeances = "id,facture_id,rang,date_echeance,montant_du,etat,accord_id\n"
    return {"clients": ("clients.csv", io.BytesIO(clients.encode()), "text/csv"),
            "factures": ("factures.csv", io.BytesIO(factures.encode()), "text/csv"),
            "echeances": ("echeances.csv", io.BytesIO(echeances.encode()), "text/csv"),
            "preferences_contact": ("preferences_contact.csv",
                                    io.BytesIO((entete_prefs + "\n" + ligne_prefs + "\n").encode()),
                                    "text/csv")}


BASE = "client_id,canal_prefere,canaux_autorises,consentement_relance,interlocuteur"


def test_import_accepte_l_ancien_format_sans_colonnes_ajoutees(api, gest, db_chargee):
    r = api.post("/api/imports", headers=gest, files=_lot(
        BASE, "CLI-9001,EMAIL,EMAIL,1,M. Test"))
    assert r.status_code == 201 and r.json()["nb_rejets"] == 0, r.text
    p = db_chargee.execute("SELECT jours_a_eviter, plage_horaire, provenance FROM "
                           "preferences_contact WHERE client_id = 'CLI-9001'").fetchone()
    assert (p["jours_a_eviter"], p["plage_horaire"]) == ("", "AUCUNE")
    assert json.loads(p["provenance"])["jours_a_eviter"]["source"] == "IMPORT"


def test_import_des_nouvelles_colonnes_avec_provenance_import(api, gest, db_chargee):
    r = api.post("/api/imports", headers=gest, files=_lot(
        BASE + ",jours_a_eviter,plage_horaire",
        "CLI-9001,EMAIL,EMAIL,1,M. Test,VENDREDI;MARDI,APRES_MIDI"))
    assert r.status_code == 201 and r.json()["nb_rejets"] == 0, r.text
    p = db_chargee.execute("SELECT * FROM preferences_contact WHERE client_id = 'CLI-9001'"
                           ).fetchone()
    assert (p["jours_a_eviter"], p["plage_horaire"]) == ("MARDI;VENDREDI", "APRES_MIDI")
    assert json.loads(p["provenance"])["plage_horaire"] == {"source": "IMPORT",
                                                              "date": "2026-12-15"}


@pytest.mark.parametrize("jours, plage", [("DIMANCHE", "MATIN"), ("MARDI", "SOIR"),
                                            ("MARDI;FOO", "AUCUNE")])
def test_import_rejette_les_valeurs_hors_listes(api, gest, db_chargee, jours, plage):
    r = api.post("/api/imports", headers=gest, files=_lot(
        BASE + ",jours_a_eviter,plage_horaire", f"CLI-9001,EMAIL,EMAIL,1,M. Test,{jours},{plage}"))
    assert r.status_code == 201
    assert [x["motif_code"] for x in r.json()["rejets"]] == ["VALEUR_INVALIDE"]
    assert db_chargee.execute("SELECT COUNT(*) FROM preferences_contact WHERE client_id = "
                              "'CLI-9001'").fetchone()[0] == 0


def test_import_rejette_une_colonne_inconnue_ou_un_interlocuteur_trop_long(api, gest):
    r = api.post("/api/imports", headers=gest, files=_lot(BASE + ",couleur",
                                                          "CLI-9001,EMAIL,EMAIL,1,M. Test,bleu"))
    assert r.status_code == 400
    r = api.post("/api/imports", headers=gest, files=_lot(
        BASE, "CLI-9001,EMAIL,EMAIL,1," + "x" * 81))
    assert [x["motif_code"] for x in r.json()["rejets"]] == ["VALEUR_INVALIDE"]


# ---- effet sur le calendrier des relances ----------------------------------------------
def test_la_relance_d_un_client_est_reportee_au_prochain_jour_permis(api, gest, valid):
    """CLI-0022 évite le vendredi : sa R1 du vendredi 18/12 est préparée le samedi 19/12."""
    changer_date(api, valid, "2026-12-18")
    planifier(api, gest)
    assert not [x for x in relances(api, gest, client_id="CLI-0022", date="2026-12-18")
                if x["statut"] != "SAUTEE"]
    changer_date(api, valid, "2026-12-19")
    planifier(api, gest)
    r = [x for x in relances(api, gest, client_id="CLI-0022", date="2026-12-19")
         if x["etape"] == "R1"]
    assert len(r) == 1 and r[0]["motif"] == "JOUR_NON_OUVRE_REPORTE"


def test_modifier_les_preferences_change_la_date_de_relance(api, gest, valid):
    api.put("/api/clients/CLI-0022/preferences", headers=gest, json={
        "jours_a_eviter": ["VENDREDI", "SAMEDI"]})
    for jour in ("2026-12-18", "2026-12-19"):
        changer_date(api, valid, jour)
        planifier(api, gest)
        assert not [x for x in relances(api, gest, client_id="CLI-0022", date=jour)
                    if x["etape"] == "R1"]
    changer_date(api, valid, "2026-12-21")                      # le dimanche est déjà exclu
    planifier(api, gest)
    assert [x for x in relances(api, gest, client_id="CLI-0022", date="2026-12-21")
            if x["etape"] == "R1"]


def test_sur_un_jour_a_eviter_meme_un_rattrapage_n_est_pas_prepare(api, gest, valid):
    """CLI-0026 évite le samedi : sa R2 du samedi 19/12 attend le lundi 21/12."""
    changer_date(api, valid, "2026-12-19")
    planifier(api, gest)
    assert not [x for x in relances(api, gest, client_id="CLI-0026", date="2026-12-19")
                if x["statut"] != "SAUTEE"]
    changer_date(api, valid, "2026-12-21")
    planifier(api, gest)
    assert [x for x in relances(api, gest, client_id="CLI-0026", date="2026-12-21")
            if x["etape"] == "R2"]


def test_envoi_un_jour_a_eviter_est_reporte_et_la_plage_horaire_est_enregistree(
        api, gest, valid):
    changer_date(api, valid, "2026-12-19")
    planifier(api, gest)
    envoyer(api, gest)
    boite = api.get("/api/canaux/envois?client_id=CLI-0022&limite=200", headers=gest
                    ).json()["elements"]
    envoi = [e for e in boite if e["date_envoi"] == "2026-12-19"]
    assert envoi and envoi[0]["plage_horaire"] == "MATIN"
    # un client sans préférence de plage : aucune plage enregistrée
    autres = [e for e in api.get("/api/canaux/envois?limite=200", headers=gest).json()["elements"]
              if e["client_id"] == "CLI-0001"]
    assert all(e["plage_horaire"] is None for e in autres)
