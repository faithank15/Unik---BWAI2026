"""Fixtures communes. Aucun accès réseau : les connexions sortantes (IP) échouent."""
import shutil
import socket
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import security
from app.config import RACINE, Reglages
from app.db import connecter
from app.ia.adaptateur import Adaptateur
from app.ia.faux import FauxLLM
from app.main import creer_app
from app.services.reset import reinitialiser

MDP_GESTIONNAIRE = "mdp-test-gestionnaire"
MDP_VALIDATEUR = "mdp-test-validateur"


class ReseauInterdit(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _bloquer_reseau(monkeypatch):
    original = socket.socket.connect

    def connect(self, adresse, *a, **k):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise ReseauInterdit(f"Accès réseau interdit pendant les tests : {adresse}")
        return original(self, adresse, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)


def faire_reglages(chemin_base: str) -> Reglages:
    return Reglages(
        database_path=chemin_base, dataset_dir=str(RACINE / "dataset"),
        demo_hooks_enabled=True, cors_origins=("http://localhost:5173",),
        session_ttl_heures=8, seed_mdp_gestionnaire=MDP_GESTIONNAIRE,
        seed_mdp_validateur=MDP_VALIDATEUR, llm_fournisseur="gemini", llm_modele="faux",
        llm_api_key="", llm_timeout_secondes=1, llm_reessais=0, log_level="WARNING")


@pytest.fixture(scope="session")
def base_modele(tmp_path_factory) -> Path:
    """Base vide (schéma, paramètres, comptes), construite une fois par session."""
    dossier = tmp_path_factory.mktemp("modele")
    chemin = dossier / "modele.db"
    reinitialiser(faire_reglages(str(chemin)), charger=False)
    return chemin


@pytest.fixture(scope="session")
def base_chargee(tmp_path_factory) -> Path:
    """Base avec le jeu de données au 2026-12-15, construite une fois par session."""
    dossier = tmp_path_factory.mktemp("chargee")
    chemin = dossier / "chargee.db"
    reinitialiser(faire_reglages(str(chemin)), charger=True)
    return chemin


def _copie(source: Path, tmp_path) -> Reglages:
    cible = tmp_path / "test.db"
    shutil.copyfile(source, cible)
    security.reinitialiser_limiteur()
    return faire_reglages(str(cible))


@pytest.fixture
def reglages(base_modele, tmp_path) -> Reglages:
    return _copie(base_modele, tmp_path)


@pytest.fixture
def reglages_charge(base_chargee, tmp_path) -> Reglages:
    return _copie(base_chargee, tmp_path)


@pytest.fixture
def db_chargee(reglages_charge) -> sqlite3.Connection:
    conn = connecter(reglages_charge.database_path)
    yield conn
    conn.close()


@pytest.fixture
def db(reglages) -> sqlite3.Connection:
    conn = connecter(reglages.database_path)
    yield conn
    conn.close()


@pytest.fixture
def horloge(db):
    """Change la date métier (date_reference) sans toucher à l'horloge technique."""
    def regler(jour: str) -> None:
        db.execute("UPDATE parametres SET valeur = ? WHERE cle = 'date_reference'", (jour,))
    return regler


@pytest.fixture
def client_api(reglages):
    app = creer_app(reglages)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def faux_llm():
    return FauxLLM()


@pytest.fixture
def api(reglages_charge, faux_llm):
    """Client d'API sur la base chargée (état initial du 2026-12-15), LLM remplacé par un faux
    (une sortie non programmée équivaut à une API indisponible)."""
    app = creer_app(reglages_charge, classeur=Adaptateur(faux_llm, modele="faux",
                                                         pause=lambda s: None))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def gest(api):
    return _jeton(api, "gestionnaire", MDP_GESTIONNAIRE)


@pytest.fixture
def valid(api):
    return _jeton(api, "validateur", MDP_VALIDATEUR)


def _jeton(client, nom, mdp) -> dict:
    r = client.post("/api/auth/login", json={"nom_utilisateur": nom, "mot_de_passe": mdp})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['jeton']}"}


@pytest.fixture
def entetes_gestionnaire(client_api):
    return _jeton(client_api, "gestionnaire", MDP_GESTIONNAIRE)


@pytest.fixture
def entetes_validateur(client_api):
    return _jeton(client_api, "validateur", MDP_VALIDATEUR)
