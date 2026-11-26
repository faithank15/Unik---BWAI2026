"""Aucun secret versionné (critère d'acceptation 8) : motifs de clés connus, .env ignoré,
.env.example sans valeur, mots de passe de démonstration locaux absents du dépôt."""
import re
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
IGNORES = {".git", ".venv", "data", "__pycache__", ".pytest_cache", ".ruff_cache"}
MOTIFS = {
    "clé Google": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "clé de type sk-": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    "clé privée": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "jeton GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "clé AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def fichiers_du_depot():
    """Fichiers suivis ou à suivre (hors fichiers ignorés par git)."""
    sortie = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=RACINE, capture_output=True, text=True, check=True).stdout
    for rel in sortie.splitlines():
        p = RACINE / rel
        if p.is_file() and not (set(p.relative_to(RACINE).parts) & IGNORES) \
                and p.suffix not in (".pdf", ".db", ".png"):
            yield p


def test_aucun_motif_de_secret_dans_les_fichiers_du_depot():
    trouves = []
    for p in fichiers_du_depot():
        texte = p.read_text(encoding="utf-8", errors="ignore")
        for nom, motif in MOTIFS.items():
            if motif.search(texte):
                trouves.append(f"{p.relative_to(RACINE)} : {nom}")
    assert not trouves, trouves


def test_env_est_ignore_par_git_et_n_est_pas_suivi():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=RACINE).returncode == 0
    suivis = subprocess.run(["git", "ls-files", ".env"], cwd=RACINE, capture_output=True,
                            text=True).stdout
    assert suivis.strip() == ""


def test_env_example_sans_valeur_secrete():
    lignes = (RACINE / ".env.example").read_text(encoding="utf-8").splitlines()
    valeurs = dict(ligne.split("=", 1) for ligne in lignes
                   if "=" in ligne and not ligne.startswith("#"))
    for cle in ("LLM_API_KEY", "SEED_MDP_GESTIONNAIRE", "SEED_MDP_VALIDATEUR"):
        assert valeurs[cle].strip() == "", f"{cle} doit rester vide dans .env.example"


def test_les_mots_de_passe_de_demonstration_locaux_ne_sont_pas_dans_le_depot():
    env = RACINE / ".env"
    if not env.is_file():
        return
    secrets_locaux = [v.strip() for k, v in (
        ligne.split("=", 1) for ligne in env.read_text().splitlines()
        if "=" in ligne and not ligne.startswith("#"))
        if k in ("SEED_MDP_GESTIONNAIRE", "SEED_MDP_VALIDATEUR", "LLM_API_KEY") and len(
            v.strip()) >= 8]
    for p in fichiers_du_depot():
        texte = p.read_text(encoding="utf-8", errors="ignore")
        for s in secrets_locaux:
            assert s not in texte, f"un secret local apparaît dans {p.relative_to(RACINE)}"
