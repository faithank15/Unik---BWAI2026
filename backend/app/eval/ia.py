"""Évaluation de la classification (document IA, sections 6 et 9). Hors CI.

Métriques : exactitude, F1 macro, précision/rappel/F1 par catégorie, matrice de confusion 7 × 7,
copie_demandee, date promise (exactitude et dates inventées), taux de revue, précision
automatique, résultats par difficulté, erreurs critiques C1 à C4 (total et part non rattrapée).
La règle simple par mots-clés sert de base de comparaison : l'apport de l'IA est la différence.
"""
import csv
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ia.dates import resoudre_date
from app.ia.decision import ParametresDecision, decider
from app.ia.validation import CATEGORIES, Resultat

DATASET = Path(__file__).resolve().parent.parent.parent / "dataset"
SENSIBLES = ("CONTESTATION", "DEJA_PAYE")


@dataclass
class Exemple:
    id: str
    texte: str
    reception: date
    canal: str
    etiquette: dict[str, str]

    @property
    def categorie(self) -> str:
        return self.etiquette["categorie_principale"]

    @property
    def difficultes(self) -> list[str]:
        return [d for d in self.etiquette["difficultes"].split(";") if d]


@dataclass
class Prediction:
    resultat: Resultat
    latence: float | None = None
    tentatives: int = 1


@dataclass
class Evaluation:
    n: int = 0
    metriques: dict = field(default_factory=dict)


def charger(split: str) -> list[Exemple]:
    def lire(rel: str) -> list[dict[str, str]]:
        with (DATASET / rel).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    etiq = {e["message_id"]: e for e in lire("messages/etiquettes.csv")}
    return [Exemple(m["id"], m["contenu"], date.fromisoformat(m["date_reception"][:10]),
                    m["canal"], etiq[m["id"]]) for m in lire("messages/messages_clients.csv")
            if etiq[m["id"]]["split"] == split]


# ---- règle simple par mots-clés (document IA, section 9) -----------------------------
REGLES = (("CONTESTATION", ("conteste", "erreur", "pas livré")),
          ("DEJA_PAYE", ("déjà payé", "j'ai réglé")),
          ("DEMANDE_ECHEANCIER", ("échéancier", "en plusieurs fois")),
          ("DEMANDE_COPIE_FACTURE", ("copie", "renvoyer la facture")))
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def regle_simple(texte: str, reception: date) -> Resultat:
    """Écrite avant de voir le jeu TEST ; appliquée dans l'ordre de priorité des catégories."""
    t = texte.lower()
    for cat, mots in REGLES:
        if any(m in t for m in mots):
            return Resultat(cat, 1.0, "copie" in t or "facture" in t and "renvoy" in t, None,
                            None, None, "mots-clés")
    if any(j in t for j in JOURS) or "demain" in t or "je paierai" in t:
        return Resultat("PROMESSE_PAIEMENT", 1.0, False, resoudre_date(t, reception), None,
                        None, "mots-clés")
    return Resultat("AUTRE_INCERTAIN", 0.0, False, None, None, None, "aucun mot-clé")


# ---- métriques ----------------------------------------------------------------------
def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "rappel": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def evaluer(exemples: list[Exemple], predictions: list[Prediction],
            params: ParametresDecision | None = None) -> dict:
    params = params or ParametresDecision()
    n = len(exemples)
    conf = {a: {b: 0 for b in CATEGORIES} for a in CATEGORIES}
    bonnes = 0
    copie = {"tp": 0, "fp": 0, "fn": 0}
    dates = {"avec_date": 0, "dates_exactes": 0, "sans_date": 0, "dates_inventees": 0}
    revue = auto = auto_bonnes = 0
    critiques = {c: {"total": 0, "non_rattrapees": 0} for c in ("C1", "C2", "C3", "C4")}
    par_diff: dict[str, list[int]] = {}
    for ex, pr in zip(exemples, predictions, strict=True):
        r = pr.resultat
        vrai = ex.categorie
        conf[vrai][r.categorie] += 1
        juste = r.categorie == vrai
        bonnes += juste
        voulue = ex.etiquette["copie_demandee"] == "1"
        copie["tp"] += voulue and r.copie_demandee
        copie["fp"] += (not voulue) and r.copie_demandee
        copie["fn"] += voulue and not r.copie_demandee
        date_vraie = ex.etiquette["date_promise"]
        if date_vraie:
            dates["avec_date"] += 1
            dates["dates_exactes"] += bool(r.date_promise and r.date_promise.isoformat()
                                           == date_vraie)
        else:
            dates["sans_date"] += 1
            dates["dates_inventees"] += r.date_promise is not None
        d = decider(r, params, True, ex.reception)
        rattrape = d.statut_message != "CLASSE"       # une personne reprend la main
        revue += rattrape
        if not rattrape:
            auto += 1
            auto_bonnes += juste and (not date_vraie or bool(
                r.date_promise and r.date_promise.isoformat() == date_vraie))
        pred_promesse = r.categorie in ("PROMESSE_PAIEMENT", "DEMANDE_DELAI")
        faux_promesse = pred_promesse and (r.date_promise is None or not (
            date_vraie and r.date_promise.isoformat() == date_vraie))
        evts = []
        if vrai == "CONTESTATION" and not juste:
            evts.append("C1")
        if vrai == "DEJA_PAYE" and not juste:
            evts.append("C2")
        if faux_promesse and vrai not in ("PROMESSE_PAIEMENT", "DEMANDE_DELAI") or (
                pred_promesse and date_vraie == "" and r.date_promise is not None):
            evts.append("C3")
        if "INJECTION" in ex.difficultes and not juste and r.categorie in (
                "DEJA_PAYE", "PROMESSE_PAIEMENT", "DEMANDE_DELAI"):
            evts.append("C4")
        for c in evts:
            critiques[c]["total"] += 1
            critiques[c]["non_rattrapees"] += not rattrape
        for diff in ex.difficultes or ["AUCUNE"]:
            par_diff.setdefault(diff, []).append(int(juste))
    par_cat = {}
    for c in CATEGORIES:
        tp = conf[c][c]
        fp = sum(conf[o][c] for o in CATEGORIES if o != c)
        fn = sum(conf[c][o] for o in CATEGORIES if o != c)
        par_cat[c] = {**prf(tp, fp, fn), "support": sum(conf[c].values())}
    latences = [p.latence for p in predictions if p.latence is not None]
    return {
        "n": n, "exactitude": round(bonnes / n, 4),
        "f1_macro": round(statistics.mean(v["f1"] for v in par_cat.values()), 4),
        "par_categorie": par_cat, "confusion": conf,
        "copie_demandee": prf(copie["tp"], copie["fp"], copie["fn"]),
        "dates": {**dates, "exactitude_dates": round(dates["dates_exactes"]
                                                     / dates["avec_date"], 4)
                  if dates["avec_date"] else None,
                  "taux_dates_inventees": round(dates["dates_inventees"] / dates["sans_date"], 4)
                  if dates["sans_date"] else None},
        "taux_revue": round(revue / n, 4), "nb_traites_sans_revue": auto,
        "precision_automatique": round(auto_bonnes / auto, 4) if auto else None,
        "erreurs_critiques": critiques,
        "erreurs_critiques_non_rattrapees": sum(c["non_rattrapees"] for c in critiques.values()),
        "par_difficulte": {k: {"n": len(v), "exactitude": round(sum(v) / len(v), 4)}
                           for k, v in sorted(par_diff.items())},
        "repli_ou_reessais": sum(1 for p in predictions if p.tentatives > 1
                                 or p.resultat.motif_repli),
        "latence_mediane_s": round(statistics.median(latences), 3) if latences else None,
        "latence_p95_s": round(sorted(latences)[int(0.95 * (len(latences) - 1))], 3)
        if latences else None,
    }


def calibrer_seuils(exemples: list[Exemple], predictions: list[Prediction],
                    cibles: dict | None = None) -> dict:
    """Pour chaque seuil de 0,50 à 0,95 (pas de 0,05) : taux de revue, précision automatique et
    erreurs critiques non rattrapées. Retient le plus petit seuil qui respecte les cibles
    (zéro erreur critique non rattrapée, précision ≥ 95 %, revue ≤ 40 %)."""
    cibles = cibles or {"critiques": 0, "precision_min": 0.95, "revue_max": 0.40}
    lignes, retenu = [], None
    for k in range(10):
        seuil = Decimal("0.50") + Decimal("0.05") * k
        m = evaluer(exemples, predictions, ParametresDecision(seuil, seuil, 30))
        ok = (m["erreurs_critiques_non_rattrapees"] <= cibles["critiques"]
              and (m["precision_automatique"] or 1.0) >= cibles["precision_min"]
              and m["taux_revue"] <= cibles["revue_max"])
        lignes.append({"seuil": float(seuil), "taux_revue": m["taux_revue"],
                       "precision_automatique": m["precision_automatique"],
                       "critiques_non_rattrapees": m["erreurs_critiques_non_rattrapees"],
                       "respecte_les_cibles": ok})
        if ok and retenu is None:
            retenu = float(seuil)
    return {"seuil_retenu": retenu, "cibles": cibles, "courbe": lignes}


def calibration_par_tranche(exemples: list[Exemple], predictions: list[Prediction]) -> list:
    """Exactitude par tranche de confiance : la confiance auto-déclarée n'est pas calibrée."""
    tranches: dict[float, list[int]] = {}
    for ex, p in zip(exemples, predictions, strict=True):
        t = min(int(p.resultat.confiance * 10) / 10, 0.9)
        tranches.setdefault(t, []).append(int(p.resultat.categorie == ex.categorie))
    return [{"tranche": f"{t:.1f}-{t + 0.1:.1f}", "n": len(v), "exactitude": round(
        sum(v) / len(v), 4)} for t, v in sorted(tranches.items())]


def cout_par_message(jetons_entree: float, jetons_sortie: float, prix_entree: float,
                     prix_sortie: float) -> float:
    """Coût d'un message : (T_entrée × p_entrée + T_sortie × p_sortie) / 1 000 000, avec des
    jetons mesurés et des prix par million de jetons relevés à la date des tests."""
    return (jetons_entree * prix_entree + jetons_sortie * prix_sortie) / 1_000_000


def rapport_markdown(titre: str, m: dict, calibration: dict | None = None) -> str:
    lignes = [f"# {titre}", "", f"Messages évalués : {m['n']}", "",
              "| Mesure | Valeur |", "| --- | --- |",
              f"| Exactitude globale | {m['exactitude']:.1%} |", f"| F1 macro | {m['f1_macro']} |",
              f"| Taux de revue | {m['taux_revue']:.1%} |",
              f"| Précision automatique | {m['precision_automatique']} |",
              f"| Exactitude des dates promises | {m['dates']['exactitude_dates']} |",
              f"| Dates inventées | {m['dates']['taux_dates_inventees']} |",
              f"| Erreurs critiques non rattrapées (C1 à C4) | "
              f"{m['erreurs_critiques_non_rattrapees']} |",
              f"| copie_demandee F1 | {m['copie_demandee']['f1']} |",
              f"| Latence médiane / p95 (s) | {m['latence_mediane_s']} / {m['latence_p95_s']} |",
              "", "## Par catégorie", "", "| Catégorie | Précision | Rappel | F1 | Support |",
              "| --- | --- | --- | --- | --- |"]
    for c, v in m["par_categorie"].items():
        lignes.append(f"| {c} | {v['precision']} | {v['rappel']} | {v['f1']} | {v['support']} |")
    lignes += ["", "## Erreurs critiques", "", "| Code | Total | Non rattrapées |",
               "| --- | --- | --- |"]
    lignes += [f"| {c} | {v['total']} | {v['non_rattrapees']} |"
               for c, v in m["erreurs_critiques"].items()]
    lignes += ["", "## Par difficulté", "", "| Difficulté | n | Exactitude |",
               "| --- | --- | --- |"]
    lignes += [f"| {k} | {v['n']} | {v['exactitude']} |" for k, v in m["par_difficulte"].items()]
    lignes += ["", "## Matrice de confusion (lignes : étiquette, colonnes : prédiction)", ""]
    entete = "| |" + "|".join(c[:9] for c in CATEGORIES) + "|"
    lignes += [entete, "|" + " --- |" * (len(CATEGORIES) + 1)]
    for a in CATEGORIES:
        lignes.append(f"| {a[:12]} |" + "|".join(str(m["confusion"][a][b]) for b in CATEGORIES)
                      + "|")
    if calibration:
        lignes += ["", f"## Seuils (cibles : {calibration['cibles']})", "",
                   f"Seuil retenu : {calibration['seuil_retenu']}", "",
                   "| Seuil | Revue | Précision auto | Critiques non rattrapées |",
                   "| --- | --- | --- | --- |"]
        lignes += [f"| {c['seuil']} | {c['taux_revue']} | {c['precision_automatique']} | "
                   f"{c['critiques_non_rattrapees']} |" for c in calibration["courbe"]]
    lignes += ["", "*La confiance donnée par un modèle n'est pas une probabilité calibrée ; "
               "les résultats métier (soldes, statuts, relances) sont présentés à part.*"]
    return "\n".join(lignes) + "\n"
