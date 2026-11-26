"""Évaluation de la classification : `python -m app.eval.eval_ia --methode regle|llm --split DEV`.

`regle` : règle simple par mots-clés, hors ligne. `llm` : modèle réel (LLM_API_KEY requise),
appels réels et payants, jamais en CI. Le jeu TEST n'est utilisé qu'une seule fois, après gel du
modèle, de la consigne et des seuils : il exige `--confirmer-gel`.
"""
import argparse
import sys
import time
from pathlib import Path

from app.config import charger_reglages
from app.eval import ia
from app.ia.adaptateur import Adaptateur, nettoyer_texte
from app.ia.gemini import ClientGemini
from app.ia.validation import SortieInvalide, repli, valider

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _classer_un(ex: ia.Exemple, client: ClientGemini, cache: dict, essais: int,
                pause: float) -> tuple[str, dict]:
    """Un appel avec réessais espacés. Retourne (message_id, entrée du cache)."""
    entree = {"message_id": ex.id, "texte": nettoyer_texte(ex.texte), "canal": ex.canal,
              "date_reception": f"{ex.reception.isoformat()}T09:00:00+01:00",
              "jour_semaine": JOURS_FR[ex.reception.weekday()], "factures_ouvertes": []}
    derniere = ""
    for i in range(essais):
        debut = time.monotonic()
        try:
            brut = client.classer(entree)
            return ex.id, {"brut": brut, "latence": time.monotonic() - debut,
                           "tentatives": i + 1, "usage": client.dernier_usage}
        except Exception as e:  # noqa: BLE001 - 503, 429, délai : on réessaie
            derniere = f"{type(e).__name__} : {str(e)[:120]}"
            time.sleep(pause * (i + 1))
    return ex.id, {"erreur": derniere, "tentatives": essais}


def predire_llm(exemples: list[ia.Exemple], split: str, parallele: int = 4,
                essais: int = 6) -> list[ia.Prediction]:
    """Classe les exemples avec le modèle réel. Les réponses sont mises en cache (fichier JSON)
    et reprises à la relance : un appel réussi n'est jamais refait (quota et coût)."""
    import json
    from concurrent.futures import ThreadPoolExecutor
    r = charger_reglages()
    if not r.llm_configure:
        raise SystemExit("LLM_API_KEY est vide : renseigner .env pour évaluer le modèle réel.")
    chemin = Path(f".cache_eval_{r.llm_modele}_{split}.json")
    cache = json.loads(chemin.read_text()) if chemin.is_file() else {}
    # Délai long : l'API réelle peut être lente aux heures de forte demande
    client = ClientGemini(r.llm_api_key, r.llm_modele, timeout=90)
    restants = [e for e in exemples if "brut" not in cache.get(e.id, {})]
    print(f"{len(exemples) - len(restants)} réponses en cache, {len(restants)} à obtenir "
          f"({parallele} requêtes en parallèle)", flush=True)
    adaptateur = Adaptateur(None, modele=r.llm_modele)
    with ThreadPoolExecutor(parallele) as pool:
        futurs = [pool.submit(_classer_un, e, ClientGemini(r.llm_api_key, r.llm_modele, 90),
                              cache, essais, 8.0) for e in restants]
        for i, f in enumerate(futurs, 1):
            mid, entree = f.result()
            cache[mid] = entree
            chemin.write_text(json.dumps(cache, ensure_ascii=False))
            if i % 5 == 0 or i == len(futurs):
                ok = sum(1 for v in cache.values() if "brut" in v)
                print(f"  {i}/{len(futurs)} traités, {ok} réponses valides en cache", flush=True)
    _ = client, adaptateur
    sortie = []
    for ex in exemples:
        c = cache.get(ex.id, {})
        if "brut" not in c:
            sortie.append(ia.Prediction(repli("FORMAT_INVALIDE"), None, c.get("tentatives", 0)))
            continue
        entree = {"message_id": ex.id, "texte": ex.texte, "canal": ex.canal,
                  "date_reception": f"{ex.reception.isoformat()}T09:00:00+01:00",
                  "jour_semaine": JOURS_FR[ex.reception.weekday()],
                  "factures_ouvertes": []}
        try:
            res = valider(c["brut"], entree)
        except SortieInvalide as e:
            res = repli(e.motif)
        sortie.append(ia.Prediction(res, c.get("latence"), c.get("tentatives", 1)))
    return sortie


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.eval.eval_ia")
    ap.add_argument("--methode", choices=["regle", "llm"], default="regle")
    ap.add_argument("--split", choices=["DEV", "TEST"], default="DEV")
    ap.add_argument("--sortie", default="rapport_ia.md")
    ap.add_argument("--confirmer-gel", action="store_true",
                    help="requis pour TEST : modèle, consigne et seuils sont gelés")
    a = ap.parse_args(argv)
    if a.split == "TEST" and a.methode == "llm" and not a.confirmer_gel:
        print("Le jeu TEST ne s'utilise qu'une fois, après gel : relancer avec "
              "--confirmer-gel.", file=sys.stderr)
        return 2
    exemples = ia.charger(a.split)
    if a.methode == "regle":
        preds = [ia.Prediction(ia.regle_simple(e.texte, e.reception)) for e in exemples]
        titre = f"Règle simple par mots-clés – jeu {a.split}"
    else:
        preds = predire_llm(exemples, a.split)
        titre = f"LLM – jeu {a.split}"
    m = ia.evaluer(exemples, preds)
    calibration = ia.calibrer_seuils(exemples, preds) if a.split == "DEV" else None
    texte = ia.rapport_markdown(titre, m, calibration)
    if a.methode == "llm":
        texte += ("\n## Calibration (exactitude par tranche de confiance)\n\n" + "\n".join(
            f"- {t['tranche']} : {t['exactitude']} ({t['n']})"
            for t in ia.calibration_par_tranche(exemples, preds)) + "\n")
    Path(a.sortie).write_text(texte, encoding="utf-8")
    print(f"{titre} : exactitude {m['exactitude']:.1%}, F1 macro {m['f1_macro']}, "
          f"revue {m['taux_revue']:.1%}, critiques non rattrapées "
          f"{m['erreurs_critiques_non_rattrapees']} -> {a.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
