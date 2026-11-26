#!/usr/bin/env python3
"""Génère rapport_tests.md : tests par famille, échecs, tests ignorés avec motif, couverture et
traçabilité règle → test (d'après les identifiants T-xxx, Sxx et Rxx présents dans les noms).

Usage : make rapport   (lance pytest avec JUnit et couverture, puis ce script)
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FAMILLES = {
    "test_verite_": "Équivalence avec la vérité terrain", "test_scenarios": "Scénarios S01 à S23",
    "test_idempotence": "Idempotence", "test_relances_robustesse": "Concurrence et reprise",
    "test_securite": "Sécurité", "test_contrat": "Contrat d'API", "test_ia": "IA (faux LLM)",
    "test_eval_ia": "Évaluation IA", "test_canevas": "Canevas", "test_calendrier": "Calendrier",
    "test_db": "Base, transactions et journal", "test_reset": "Reproductibilité",
    "test_import": "Import", "test_paiements": "Paiements et avoirs",
    "test_relances": "Moteur de relances", "test_messages": "Messages", "test_dossiers":
    "Dossiers, revue, journal", "test_tableau": "Tableau de bord et journal",
    "test_api": "API", "test_domaine": "Règles pures", "test_reseau": "Réseau bloqué",
    "test_secrets": "Secrets",
}
ID = re.compile(r"(?:test_)?((?:[TS]-?[A-Z]?\d{1,2})|(?:[A-Z]{1,2}\d{2})|S\d{2})", re.I)


def famille(fichier: str) -> str:
    nom = Path(fichier).stem
    for prefixe, libelle in FAMILLES.items():
        if nom.startswith(prefixe):
            return libelle
    return "Autres"


def main() -> int:
    junit = RACINE / "junit.xml"
    if not junit.is_file():
        print("junit.xml absent : lancer `make rapport`.", file=sys.stderr)
        return 1
    cas = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        statut, detail = "ok", ""
        for enfant in tc:
            if enfant.tag in ("failure", "error"):
                statut, detail = "échec", (enfant.get("message") or "")[:200]
            elif enfant.tag == "skipped":
                statut, detail = "ignoré", enfant.get("message") or "(sans motif)"
        cas.append({"fichier": (tc.get("classname") or "").replace(".", "/") + ".py",
                    "nom": tc.get("name", ""), "statut": statut, "detail": detail,
                    "duree": float(tc.get("time", 0))})
    par_famille: dict[str, Counter] = defaultdict(Counter)
    for c in cas:
        par_famille[famille(c["fichier"])][c["statut"]] += 1
    lignes = ["# Rapport de tests", "", f"Total : **{len(cas)}** tests, "
              f"{sum(c['statut'] == 'ok' for c in cas)} réussis, "
              f"{sum(c['statut'] == 'échec' for c in cas)} en échec, "
              f"{sum(c['statut'] == 'ignoré' for c in cas)} ignorés. "
              f"Durée cumulée : {sum(c['duree'] for c in cas):.0f} s.", "",
              "## Par famille", "", "| Famille | Réussis | Échecs | Ignorés |",
              "| --- | --- | --- | --- |"]
    for f, cnt in sorted(par_famille.items()):
        lignes.append(f"| {f} | {cnt['ok']} | {cnt['échec']} | {cnt['ignoré']} |")
    echecs = [c for c in cas if c["statut"] == "échec"]
    lignes += ["", "## Échecs", ""] + ([f"- `{c['fichier']}::{c['nom']}` : {c['detail']}"
                                        for c in echecs] or ["Aucun."])
    ignores = [c for c in cas if c["statut"] == "ignoré"]
    lignes += ["", "## Tests ignorés (motif écrit obligatoire)", ""] + (
        [f"- `{c['fichier']}::{c['nom']}` : {c['detail']}" for c in ignores] or ["Aucun."])
    couv = RACINE / "coverage.json"
    if couv.is_file():
        data = json.loads(couv.read_text())
        lignes += ["", "## Couverture (`app/domain`, `app/services`, `app/ia`)", "",
                   "| Module | Couverture |", "| --- | --- |"]
        for chemin, v in sorted(data["files"].items()):
            lignes.append(f"| `{chemin}` | {v['summary']['percent_covered']:.0f} % |")
        lignes.append(f"| **Total** | **{data['totals']['percent_covered']:.1f} %** |")
    trace: dict[str, list[str]] = defaultdict(list)
    for c in cas:
        for m in ID.findall(c["nom"]):
            trace[m.upper()].append(c["nom"])
    lignes += ["", "## Traçabilité règle → test", "", "| Identifiant | Tests |", "| --- | --- |"]
    for k in sorted(trace):
        lignes.append(f"| {k} | {', '.join(sorted(set(trace[k]))[:3])} |")
    (RACINE / "rapport_tests.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"rapport_tests.md écrit ({len(cas)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
