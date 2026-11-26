import sqlite3

import pytest
from fastapi import Depends

from app import security
from app.db import connecter
from tests.conftest import MDP_GESTIONNAIRE


def login(client, nom="gestionnaire", mdp=MDP_GESTIONNAIRE):
    return client.post("/api/auth/login", json={"nom_utilisateur": nom, "mot_de_passe": mdp})


def test_U04_connexion_jeton_opaque_et_session(client_api, db):
    r = login(client_api)
    assert r.status_code == 200
    corps = r.json()
    assert corps["utilisateur"] == {"id": "USR-0001", "nom_utilisateur": None,
                                    "nom_affiche": "Gestionnaire démo", "role": "GESTIONNAIRE"}
    assert len(corps["jeton"]) >= 40
    s = db.execute("SELECT * FROM sessions").fetchall()
    assert len(s) == 1
    assert s[0]["token_hash"] == security.empreinte_jeton(corps["jeton"])
    assert corps["jeton"] not in s[0]["token_hash"]
    assert s[0]["expire_le"] > s[0]["cree_le"]


def test_U05_mauvais_mot_de_passe_et_identifiant_inconnu_identiques(client_api):
    a = login(client_api, mdp="faux")
    b = login(client_api, nom="inconnu", mdp="faux")
    assert a.status_code == b.status_code == 401
    assert a.json()["erreur"]["message"] == b.json()["erreur"]["message"]
    assert a.json()["erreur"]["code"] == "NON_AUTHENTIFIE"


def test_U06_deconnexion_revoque_le_jeton(client_api, entetes_gestionnaire):
    assert client_api.get("/api/auth/moi", headers=entetes_gestionnaire).status_code == 200
    assert client_api.post("/api/auth/logout", headers=entetes_gestionnaire).status_code == 200
    r = client_api.get("/api/auth/moi", headers=entetes_gestionnaire)
    assert r.status_code == 401


def test_U02_jeton_invalide(client_api):
    for entete in ({"Authorization": "Bearer nimporte"}, {"Authorization": "Basic abc"}, {}):
        assert client_api.get("/api/auth/moi", headers=entete).status_code == 401


def test_U02_jeton_expire(client_api, entetes_gestionnaire, reglages):
    c = connecter(reglages.database_path)
    c.execute("UPDATE sessions SET expire_le = '2000-01-01T00:00:00+01:00'")
    c.close()
    r = client_api.get("/api/auth/moi", headers=entetes_gestionnaire)
    assert r.status_code == 401 and "expiré" in r.json()["erreur"]["message"]


def test_U07_mots_de_passe_haches_scrypt(db):
    for r in db.execute("SELECT mot_de_passe_hash FROM utilisateurs"):
        h = r[0]
        assert h.startswith("scrypt$") and h.count("$") == 5
        assert MDP_GESTIONNAIRE not in h
    assert security.verifier(MDP_GESTIONNAIRE,
                             db.execute("SELECT mot_de_passe_hash FROM utilisateurs "
                                        "WHERE id='USR-0001'").fetchone()[0])
    assert not security.verifier("autre", security.hacher("x"))
    assert not security.verifier("x", "format-invalide")


def test_sels_differents(db):
    assert security.hacher("a") != security.hacher("a")


def test_limiteur_5_echecs_puis_429(client_api):
    for _ in range(5):
        assert login(client_api, mdp="faux").status_code == 401
    r = login(client_api)  # même le bon mot de passe est refusé pendant le blocage
    assert r.status_code == 429
    assert r.json()["erreur"]["code"] == "TROP_DE_TENTATIVES"
    # un autre utilisateur n'est pas touché
    assert login(client_api, nom="validateur", mdp="faux").status_code == 401


def test_U08_aucun_secret_dans_le_journal(client_api, db):
    saisi = "mot-de-passe-saisi-unique-xyz"
    login(client_api, mdp=saisi)
    r = login(client_api)
    jeton = r.json()["jeton"]
    texte = " ".join(str(dict(x)) for x in db.execute("SELECT * FROM journal"))
    assert saisi not in texte
    assert MDP_GESTIONNAIRE not in texte
    assert jeton not in texte
    types = [x[0] for x in db.execute("SELECT type_evenement FROM journal")]
    assert "CONNEXION_ECHEC" in types and "CONNEXION" in types


def test_connexion_ecrit_un_evenement_avec_acteur_et_correlation(client_api, db):
    client_api.post("/api/auth/login", headers={"X-Correlation-Id": "corr-1"},
                    json={"nom_utilisateur": "validateur", "mot_de_passe": "mdp-test-validateur"})
    ligne = db.execute("SELECT * FROM journal WHERE type_evenement = 'CONNEXION'").fetchone()
    assert (ligne["acteur_type"], ligne["acteur_id"], ligne["correlation_id"]) == \
        ("UTILISATEUR", "USR-0002", "corr-1")


def test_J04_echec_ne_cree_pas_de_session(client_api, db):
    login(client_api, mdp="faux")
    assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_role_insuffisant_donne_403_et_journalise(reglages):
    """Une route réservée au VALIDATEUR, appelée par un GESTIONNAIRE."""
    from fastapi.testclient import TestClient

    from app.api.deps import exiger
    from app.main import creer_app
    app = creer_app(reglages)

    @app.post("/api/_reserve")
    def reserve(_=Depends(exiger("VALIDATEUR"))):
        return {"ok": True}

    with TestClient(app) as c:
        g = c.post("/api/auth/login", json={"nom_utilisateur": "gestionnaire",
                                            "mot_de_passe": MDP_GESTIONNAIRE}).json()["jeton"]
        v = c.post("/api/auth/login", json={"nom_utilisateur": "validateur",
                                            "mot_de_passe": "mdp-test-validateur"}).json()["jeton"]
        assert c.post("/api/_reserve").status_code == 401
        r = c.post("/api/_reserve", headers={"Authorization": f"Bearer {g}"})
        assert r.status_code == 403 and r.json()["erreur"]["code"] == "ACCES_REFUSE"
        assert c.post("/api/_reserve", headers={"Authorization": f"Bearer {v}"}).status_code == 200
    conn = sqlite3.connect(reglages.database_path)
    assert conn.execute("SELECT COUNT(*) FROM journal WHERE type_evenement='ACCES_REFUSE'"
                        ).fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("champ", ["nom_utilisateur", "mot_de_passe"])
def test_champ_obligatoire(client_api, champ):
    corps = {"nom_utilisateur": "a", "mot_de_passe": "b"}
    del corps[champ]
    assert client_api.post("/api/auth/login", json=corps).status_code == 400
