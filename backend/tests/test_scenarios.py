"""Scénarios S01 à S06 de bout en bout, par l'API, comparés à verite_terrain/scenarios/Sxx.json.
Les scénarios S07 et suivants arrivent avec les jalons M2 et M3."""
from app.db import connecter
from tests.aides import compter, corps_paiement, evenement, fichiers_nominal
from tests.verite import lire_scenario


def test_S01_import_nominal_rejoue_deux_fois_aucun_doublon(client_api, entetes_gestionnaire,
                                                           reglages):
    attendu = lire_scenario("S01")["attendu"]
    r1 = client_api.post("/api/imports", files=fichiers_nominal(), headers=entetes_gestionnaire)
    assert r1.status_code == 201
    c = connecter(reglages.database_path)
    assert r1.json()["statut"] == attendu["premiere"]["statut"]
    assert compter(c, "clients") == attendu["premiere"]["clients"]
    assert compter(c, "factures") == attendu["premiere"]["factures"]
    assert compter(c, "echeances") == attendu["premiere"]["echeances"]
    avant = {t: compter(c, t) for t in ("clients", "factures", "echeances")}
    r2 = client_api.post("/api/imports", files=fichiers_nominal(), headers=entetes_gestionnaire)
    assert r2.json()["statut"] == attendu["seconde"]["statut"]
    assert {t: compter(c, t) for t in avant} == avant


def test_S02_lot_defectueux(client_api, entetes_gestionnaire):
    from tests.aides import fichiers_defectueux
    attendu = lire_scenario("S02")["attendu"]
    client_api.post("/api/imports", files=fichiers_nominal(), headers=entetes_gestionnaire)
    r = client_api.post("/api/imports", files=fichiers_defectueux(),
                        headers=entetes_gestionnaire).json()
    assert (r["nb_lignes"], r["nb_acceptees"], r["nb_rejets"]) == (
        attendu["nb_lignes"], attendu["nb_acceptees"], attendu["nb_rejets"])
    assert sorted((x["fichier"], x["ligne"], x["motif_code"]) for x in r["rejets"]) == \
        sorted((x["fichier"], x["ligne"], x["motif_code"]) for x in attendu["rejets"])


def test_S03_paiements_partiels(api, gest):
    attendu = lire_scenario("S03")["attendu"]
    assert len(attendu) == 8
    for a in attendu:
        f = api.get(f"/api/factures/{a['facture_id']}", headers=gest).json()
        assert (f["statut"], f["solde"], int(f["partiellement_payee"])) == (
            a["statut"], int(a["solde_facture"]), int(a["partiellement_payee"])), a["facture_id"]


def test_S04_paiement_couvrant_plusieurs_factures(api, gest, db_chargee):
    attendu = lire_scenario("S04")["attendu"]
    r = api.post("/api/paiements", json=corps_paiement(evenement("paiement_multifactures")),
                 headers=gest)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["id"] == attendu["paiement"]
    assert sorted((a["echeance_id"], a["montant_affecte"], a["mode"]) for a in
                  p["affectations"]) == sorted((a["echeance_id"], a["montant_affecte"],
                                                a["mode"]) for a in attendu["affectations"])
    assert p["reste_non_affecte"] == attendu["reste_non_affecte"] == 0
    for fid in attendu["factures_soldees"]:
        assert api.get(f"/api/factures/{fid}", headers=gest).json()["statut"] == "SOLDEE"


def test_S05_paiement_ambigu(api, gest, db_chargee):
    attendu = lire_scenario("S05")["attendu"]
    r = api.post("/api/paiements", json=corps_paiement(evenement("paiement_ambigu")),
                 headers=gest)
    p = r.json()
    assert p["id"] == attendu["paiement"] and p["affectations"] == []
    assert p["reste_non_affecte"] == attendu["reste_non_affecte"]
    revue = db_chargee.execute("SELECT type, objet_type, objet_id, statut FROM file_revue "
                               "WHERE objet_id = ?", (p["id"],)).fetchone()
    assert dict(revue) == {"type": attendu["revue"]["type"],
                           "objet_type": attendu["revue"]["objet_type"],
                           "objet_id": attendu["revue"]["objet_id"], "statut": "OUVERTE"}
    assert any(x["id"] == p["id"] for x in api.get(
        "/api/paiements?non_affecte=true", headers=gest).json()["elements"])


def test_S06_paiement_rejoue(api, gest, db_chargee):
    attendu = lire_scenario("S06")["attendu"]
    nb = compter(db_chargee, "paiements")
    nb_aff = compter(db_chargee, "affectations")
    r = api.post("/api/paiements", json=corps_paiement(evenement("paiement_rejoue")),
                 headers=gest)
    assert r.status_code == attendu["http"] == 200
    assert r.json()["deja_enregistre"] is attendu["deja_enregistre"]
    assert compter(db_chargee, "paiements") == nb == attendu["nb_paiements_inchange"]
    assert compter(db_chargee, "affectations") == nb_aff
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = ?",
                              (attendu["evenement"],)).fetchone()[0] == 1


def test_S01_apres_reset_le_lot_nominal_est_deja_importe(api, gest, db_chargee):
    r = api.post("/api/imports", files=fichiers_nominal(), headers=gest)
    assert r.status_code == 200 and r.json()["statut"] == "DEJA_IMPORTE"
    assert compter(db_chargee, "clients") == 30
