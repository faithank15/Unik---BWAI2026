#!/usr/bin/env python3
"""Exporte le contrat d'API (openapi.json) depuis l'application. À relancer après toute
modification de route : le test de contrat compare ce fichier à l'application."""
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app.config import Reglages  # noqa: E402
from app.main import creer_app  # noqa: E402


def contrat() -> dict:
    reglages = Reglages(
        database_path=":memory:", dataset_dir="", demo_hooks_enabled=True,
        cors_origins=("http://localhost:5173",), session_ttl_heures=8, seed_mdp_gestionnaire="",
        seed_mdp_validateur="", llm_fournisseur="gemini", llm_modele="", llm_api_key="",
        llm_timeout_secondes=15, llm_reessais=2, log_level="WARNING")
    return creer_app(reglages).openapi()


def serialiser(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    (RACINE / "openapi.json").write_text(serialiser(contrat()), encoding="utf-8")
    print("openapi.json exporté")
