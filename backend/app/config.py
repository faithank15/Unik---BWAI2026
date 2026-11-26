"""Configuration technique lue depuis l'environnement et le fichier .env (jamais versionné).

Les paramètres métier (seuils, délais, date de référence) ne sont pas ici : ils vivent dans
la table `parametres` et se modifient par l'API.
"""
import os
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _lire_env_fichier(chemin: Path) -> dict[str, str]:
    valeurs: dict[str, str] = {}
    if not chemin.is_file():
        return valeurs
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeurs[cle.strip()] = valeur.strip().strip('"').strip("'")
    return valeurs


@dataclass(frozen=True)
class Reglages:
    database_path: str
    dataset_dir: str
    demo_hooks_enabled: bool
    cors_origins: tuple[str, ...]
    session_ttl_heures: int
    seed_mdp_gestionnaire: str
    seed_mdp_validateur: str
    llm_fournisseur: str
    llm_modele: str
    llm_api_key: str
    llm_timeout_secondes: int
    llm_reessais: int
    log_level: str

    @property
    def llm_configure(self) -> bool:
        return bool(self.llm_api_key)


def charger_reglages(env_fichier: Path | None = None) -> Reglages:
    """Lit .env puis l'environnement (qui l'emporte). Les chemins relatifs partent de la
    racine du dépôt."""
    fichier = _lire_env_fichier(env_fichier if env_fichier else RACINE / ".env")
    env = {**fichier, **os.environ}

    def chemin(cle: str, defaut: str) -> str:
        p = Path(env.get(cle, defaut))
        return str(p if p.is_absolute() else (RACINE / p).resolve())

    return Reglages(
        database_path=chemin("DATABASE_PATH", "./data/recouvrement.db"),
        dataset_dir=chemin("DATASET_DIR", "./dataset"),
        demo_hooks_enabled=env.get("DEMO_HOOKS_ENABLED", "true").lower() == "true",
        cors_origins=tuple(o.strip() for o in env.get(
            "CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()),
        session_ttl_heures=int(env.get("SESSION_TTL_HEURES", "8")),
        seed_mdp_gestionnaire=env.get("SEED_MDP_GESTIONNAIRE", ""),
        seed_mdp_validateur=env.get("SEED_MDP_VALIDATEUR", ""),
        llm_fournisseur=env.get("LLM_FOURNISSEUR", "gemini"),
        llm_modele=env.get("LLM_MODELE", ""),
        llm_api_key=env.get("LLM_API_KEY", ""),
        llm_timeout_secondes=int(env.get("LLM_TIMEOUT_SECONDES", "15")),
        llm_reessais=int(env.get("LLM_REESSAIS", "2")),
        log_level=env.get("LOG_LEVEL", "INFO"),
    )
