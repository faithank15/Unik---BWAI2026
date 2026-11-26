import re


def test_sante_publique(client_api):
    r = client_api.get("/api/sante")
    assert r.status_code == 200
    corps = r.json()
    assert corps["statut"] == "ok" and corps["base_de_donnees"] == "ok"
    assert corps["llm"]["disponible"] is False  # aucune clé dans les tests


def test_contexte_exige_un_jeton(client_api):
    r = client_api.get("/api/contexte")
    assert r.status_code == 401
    assert r.json()["erreur"]["code"] == "NON_AUTHENTIFIE"


def test_contexte(client_api, entetes_gestionnaire):
    r = client_api.get("/api/contexte", headers=entetes_gestionnaire)
    assert r.status_code == 200
    assert r.json() == {"date_reference": "2026-12-15", "jour_semaine": "mardi",
                        "jour_ouvre": True, "mode_demonstration": True}


def test_contexte_jour_non_ouvre(client_api, entetes_gestionnaire, db, horloge):
    horloge("2026-12-25")
    c = client_api.get("/api/contexte", headers=entetes_gestionnaire).json()
    assert c["jour_semaine"] == "vendredi" and c["jour_ouvre"] is False


def test_N03_format_d_erreur_homogene(client_api):
    r = client_api.get("/api/introuvable")
    assert r.status_code == 404
    e = r.json()["erreur"]
    assert e["code"] == "INTROUVABLE" and "message" in e and "details" in e
    assert e["correlation_id"] == r.headers["X-Correlation-Id"]


def test_H03_corps_mal_forme(client_api):
    r = client_api.post("/api/auth/login", content="pas du json",
                        headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["erreur"]["code"] == "VALIDATION"
    r = client_api.post("/api/auth/login", json={"nom_utilisateur": "x"})
    assert r.status_code == 400
    assert r.json()["erreur"]["details"]["champs"][0]["champ"].endswith("mot_de_passe")


def test_correlation_id_recopie(client_api):
    r = client_api.get("/api/sante", headers={"X-Correlation-Id": "abc-123"})
    assert r.headers["X-Correlation-Id"] == "abc-123"


def test_correlation_id_genere(client_api):
    r = client_api.get("/api/sante")
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["X-Correlation-Id"])


def test_entetes_de_securite(client_api):
    r = client_api.get("/api/sante")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cache-Control"] == "no-store"


def test_cors_limite_a_l_origine_locale(client_api):
    ok = client_api.get("/api/sante", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    ko = client_api.get("/api/sante", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in ko.headers


def test_erreur_interne_sans_trace(reglages):
    from fastapi.testclient import TestClient

    from app.main import creer_app
    app = creer_app(reglages)

    @app.get("/api/_boom")
    def boom():
        raise ValueError("détail secret")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500
    assert r.json()["erreur"]["code"] == "ERREUR_INTERNE"
    assert "secret" not in r.text and "Traceback" not in r.text
