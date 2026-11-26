"""Routes de lecture du portefeuille : listes, filtres, tri, pagination, entrées hostiles."""
import pytest


def test_liste_des_factures_pagination_et_total(api, gest):
    r = api.get("/api/factures?limite=10&decalage=5", headers=gest).json()
    assert r["total"] == 120 and len(r["elements"]) == 10
    assert r["elements"][0]["id"] == "FAC-2026-0006"
    assert api.get("/api/factures?limite=200", headers=gest).json()["elements"].__len__() == 120


@pytest.mark.parametrize("params,attendu", [
    ("statut=ECHUE", 47), ("statut=SOLDEE", 38), ("statut=CONTESTEE", 4),
    ("statut=COUVERTE_PAR_ECHEANCIER", 3), ("statut=ANNULEE", 3), ("statut=NON_ECHUE", 25),
    ("client_id=CLI-0001", 4), ("q=FA-2026-0461", 1),
])
def test_filtres_des_factures(api, gest, params, attendu):
    assert api.get(f"/api/factures?{params}&limite=200", headers=gest).json()["total"] == attendu


def test_filtres_retard_et_solde(api, gest):
    r = api.get("/api/factures?retard_min=30&solde_min=1&limite=200", headers=gest).json()
    assert r["total"] > 0
    assert all(f["retard_jours"] >= 30 and f["solde"] >= 1 for f in r["elements"])


def test_tri_croissant_et_decroissant(api, gest):
    asc = api.get("/api/factures?tri=solde&limite=200", headers=gest).json()["elements"]
    desc = api.get("/api/factures?tri=-solde&limite=200", headers=gest).json()["elements"]
    assert [f["solde"] for f in asc] == sorted(f["solde"] for f in asc)
    assert [f["solde"] for f in desc] == sorted((f["solde"] for f in asc), reverse=True)


def test_N04_tri_inconnu_et_limite_hors_bornes(api, gest):
    for url in ("/api/factures?tri=nimporte", "/api/factures?limite=0",
                "/api/factures?limite=201", "/api/factures?decalage=-1"):
        r = api.get(url, headers=gest)
        assert r.status_code == 400 and r.json()["erreur"]["code"] == "VALIDATION", url


@pytest.mark.parametrize("url", ["/api/factures", "/api/clients", "/api/echeances",
                                 "/api/priorisation", "/api/paiements", "/api/avoirs",
                                 "/api/imports"])
def test_N04_meme_forme_de_liste_partout(api, gest, url):
    r = api.get(url, headers=gest).json()
    assert set(r) >= {"total", "elements"} and isinstance(r["elements"], list)


def test_H01_injection_sql_dans_les_filtres(api, gest):
    for url in ("/api/factures?q=' OR 1=1 --", "/api/clients?q=%27%20OR%201%3D1%20--",
                "/api/factures?statut=ECHUE' OR '1'='1", "/api/factures?client_id=x'; DROP TABLE "
                "factures;--"):
        r = api.get(url, headers=gest)
        assert r.status_code == 200 and r.json()["total"] == 0, url
    assert api.get("/api/factures", headers=gest).json()["total"] == 120


def test_H02_facture_inexistante_404(api, gest):
    r = api.get("/api/factures/FAC-9999", headers=gest)
    assert r.status_code == 404 and r.json()["erreur"]["code"] == "INTROUVABLE"
    assert api.get("/api/clients/CLI-9999", headers=gest).status_code == 404
    assert api.get("/api/paiements/PAY-9999", headers=gest).status_code == 404


def test_detail_facture_echue_avec_priorite(api, gest):
    f = api.get("/api/factures/FAC-2026-0067", headers=gest).json()
    assert f["statut"] == "ECHUE" and f["retard_jours"] == 45
    assert f["priorite"]["rang"] >= 1 and set(f["priorite"]) == {
        "rang", "score", "points_anciennete", "points_solde", "points_historique"}
    assert f["client"]["id"] == "CLI-0005" and len(f["echeances"]) == 1
    assert f["echeances"][0]["retard_jours"] == 45


def test_detail_facture_soldee_sans_priorite(api, gest):
    f = api.get("/api/factures/FAC-2026-0001", headers=gest).json()
    assert f["statut"] == "SOLDEE" and f["priorite"] is None and f["solde"] == 0


def test_echeances_filtres(api, gest):
    r = api.get("/api/echeances?en_retard=true&limite=200", headers=gest).json()
    assert r["total"] > 0 and all(e["retard_jours"] > 0 for e in r["elements"])
    r = api.get("/api/echeances?facture_id=FAC-2026-0102", headers=gest).json()
    assert r["total"] == 4 and sum(e["etat"] == "REMPLACEE" for e in r["elements"]) == 1
    r = api.get("/api/echeances?echeance_avant=2026-09-01&limite=200", headers=gest).json()
    assert all(e["date_echeance"] < "2026-09-01" for e in r["elements"])
    assert api.get("/api/echeances?echeance_avant=pas-une-date", headers=gest
                   ).status_code == 400


def test_priorisation_decomposition_et_tri_par_score(api, gest):
    r = api.get("/api/priorisation?limite=200", headers=gest).json()
    assert r["total"] == 47 and r["date_reference"] == "2026-12-15"
    assert [x["rang"] for x in r["elements"]] == list(range(1, 48))
    premier = r["elements"][0]
    assert set(premier) >= {"points_anciennete", "points_solde", "points_historique", "score"}
    tri = api.get("/api/priorisation?tri=-score&limite=200", headers=gest).json()["elements"]
    scores = [float(x["score"]) for x in tri]
    assert scores == sorted(scores, reverse=True)


def test_clients_liste_filtres_et_encours(api, gest):
    r = api.get("/api/clients?limite=200", headers=gest).json()
    assert r["total"] == 30
    assert api.get("/api/clients?canal=EMAIL&limite=200", headers=gest).json()["total"] == 12
    avec = api.get("/api/clients?avec_encours=true&limite=200", headers=gest).json()
    assert 0 < avec["total"] <= 30 and all(c["encours"] > 0 for c in avec["elements"])
    assert api.get("/api/clients?q=Boutique&limite=200", headers=gest).json()["total"] >= 5


def test_detail_client(api, gest):
    c = api.get("/api/clients/CLI-0009", headers=gest).json()
    assert c["raison_sociale"] and c["preferences"]["consentement_relance"] is True
    assert c["encours"] > 0 and any(f["statut"] == "ECHUE" for f in c["factures"])
    assert len(c["relances_recentes"]) >= 1  # historique chargé


def test_preferences_mise_a_jour_resout_la_revue_de_contact(api, gest, db_chargee):
    from app.db import transaction
    from app.journal import SYSTEME
    from app.services.revue import ouvrir_revue
    with transaction(db_chargee):
        ouvrir_revue(db_chargee, "CONSENTEMENT_ABSENT", "CLIENT", "CLI-0027", "CLI-0027",
                     "test", SYSTEME)
    r = api.put("/api/clients/CLI-0027/preferences", headers=gest,
                json={"consentement_relance": True})
    assert r.status_code == 200 and r.json()["revues_resolues"] == 1
    assert db_chargee.execute("SELECT statut FROM file_revue WHERE objet_id='CLI-0027'"
                              ).fetchone()[0] == "RESOLUE"
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'PREFERENCES_MODIFIEES'").fetchone()[0] == 1


def test_preferences_validations(api, gest):
    for corps in ({"email": "pas-un-mail"}, {"whatsapp": "+22912"},
                  {"canal_prefere": "SMS"}, {"canaux_autorises": []},
                  {"canal_prefere": "EMAIL", "canaux_autorises": ["WHATSAPP"]}):
        assert api.put("/api/clients/CLI-0001/preferences", headers=gest, json=corps
                       ).status_code == 400, corps
    assert api.put("/api/clients/CLI-9999/preferences", headers=gest, json={}
                   ).status_code == 404


def test_client_sans_canal_valide_reste_sans_canal_apres_mise_a_jour_du_consentement(
        api, gest, db_chargee):
    r = api.put("/api/clients/CLI-0028/preferences", headers=gest,
                json={"consentement_relance": True})
    assert r.status_code == 200 and r.json()["revues_resolues"] == 0  # aucune coordonnée


@pytest.mark.parametrize("url", ["/api/clients", "/api/factures", "/api/echeances",
                                 "/api/priorisation", "/api/paiements", "/api/avoirs",
                                 "/api/imports", "/api/parametres"])
def test_U01_routes_protegees_sans_jeton(api, url):
    assert api.get(url).status_code == 401


def test_parametres_lecture_et_modification_reservee_au_validateur(api, gest, valid):
    p = api.get("/api/parametres", headers=gest).json()["elements"]
    assert {x["cle"] for x in p} >= {"date_reference", "seuil_gros_montant"}
    r = api.put("/api/parametres/seuil_gros_montant", headers=gest, json={"valeur": "400000"})
    assert r.status_code == 403
    r = api.put("/api/parametres/seuil_gros_montant", headers=valid, json={"valeur": "400000"})
    assert r.status_code == 200 and r.json()["valeur"] == "400000"
    assert api.put("/api/parametres/seuil_gros_montant", headers=valid,
                   json={"valeur": "beaucoup"}).status_code == 400
    assert api.put("/api/parametres/inconnu", headers=valid, json={"valeur": "1"}
                   ).status_code == 404


def test_changement_de_date_de_reference_recalcule_les_retards(api, gest, valid):
    avant = api.get("/api/factures/FAC-2026-0067", headers=gest).json()["retard_jours"]
    r = api.post("/api/admin/date-reference", headers=valid, json={"date": "2026-12-20"})
    assert r.status_code == 200
    apres = api.get("/api/factures/FAC-2026-0067", headers=gest).json()["retard_jours"]
    assert apres == avant + 5
    assert api.post("/api/admin/date-reference", headers=valid, json={"date": "2026-02-30"}
                    ).status_code == 400
    assert api.post("/api/admin/date-reference", headers=gest, json={"date": "2026-12-21"}
                    ).status_code == 403


def test_hooks_de_demonstration_desactives_donnent_404(reglages_charge, valid):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.main import creer_app
    from tests.conftest import MDP_VALIDATEUR
    app = creer_app(replace(reglages_charge, demo_hooks_enabled=False))
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={
            "nom_utilisateur": "validateur", "mot_de_passe": MDP_VALIDATEUR}).json()["jeton"]}
        assert c.post("/api/admin/reset", headers=h).status_code == 404
        assert c.post("/api/admin/date-reference", headers=h,
                      json={"date": "2026-12-20"}).status_code == 404


def test_admin_reset_recharge_le_jeu(api, valid, reglages_charge):
    api.post("/api/admin/date-reference", headers=valid, json={"date": "2026-12-20"})
    r = api.post("/api/admin/reset", headers=valid)
    assert r.status_code == 200
    # la base a été recréée : l'ancien jeton n'existe plus, on se reconnecte
    from tests.conftest import MDP_VALIDATEUR
    j = api.post("/api/auth/login", json={"nom_utilisateur": "validateur",
                                          "mot_de_passe": MDP_VALIDATEUR}).json()["jeton"]
    h = {"Authorization": f"Bearer {j}"}
    assert api.get("/api/contexte", headers=h).json()["date_reference"] == "2026-12-15"


def test_les_listes_donnent_le_nom_du_client(api, gest, valid):
    """Demande de l'interface : un nom par ligne sans charger les 30 clients (champ ajouté,
    contrat inchangé pour les lecteurs existants)."""
    from tests.aides_relances import envoyer, planifier
    planifier(api, gest)
    envoyer(api, gest)
    api.post("/api/messages", headers=gest, json={
        "client_id": "CLI-0001", "canal": "WHATSAPP", "contenu": "Bonjour"})
    noms = {c["id"]: c["raison_sociale"] for c in api.get(
        "/api/clients?limite=200", headers=gest).json()["elements"]}
    for url in ("/api/factures", "/api/priorisation", "/api/relances", "/api/relances/suspensions",
                "/api/canaux/envois", "/api/revue", "/api/messages", "/api/promesses"):
        elements = api.get(f"{url}?limite=200", headers=gest).json()["elements"]
        assert elements, url
        for e in elements:
            assert "client_raison_sociale" in e, url
            attendu = noms.get(e.get("client_id")) if e.get("client_id") else None
            assert e["client_raison_sociale"] == attendu, (url, e.get("client_id"))
    # une revue sans client (paiement non identifiable) a un nom nul, sans erreur
    revue = api.get("/api/revue?type=PAIEMENT_AMBIGU", headers=gest).json()["elements"]
    assert revue and all(r["client_raison_sociale"] is None for r in revue
                         if r["client_id"] is None)
