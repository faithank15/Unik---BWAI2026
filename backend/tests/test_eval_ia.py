"""Résolveur de dates (30 expressions standard), règle simple et métriques d'évaluation."""
from datetime import date

import pytest

from app.eval import ia
from app.eval.eval_ia import main as eval_main
from app.ia.dates import candidates, resoudre_date
from app.ia.validation import Resultat

MERCREDI = date(2026, 12, 2)     # mercredi


@pytest.mark.parametrize("texte,attendu", [
    ("Je paie aujourd'hui", date(2026, 12, 2)), ("je règle demain", date(2026, 12, 3)),
    ("Je paie vendredi", date(2026, 12, 4)), ("lundi", date(2026, 12, 7)),
    ("mardi svp", date(2026, 12, 8)), ("je paie mercredi", date(2026, 12, 9)),  # strictement après
    ("jeudi", date(2026, 12, 3)), ("samedi", date(2026, 12, 5)),
    ("dimanche", date(2026, 12, 6)),
    ("dans 3 jours", date(2026, 12, 5)), ("dans 2 jours", date(2026, 12, 4)),
    ("dans 7 jours", date(2026, 12, 9)), ("dans 1 jour", date(2026, 12, 3)),
    ("lundi prochain", date(2026, 12, 7)), ("début de semaine prochaine", date(2026, 12, 7)),
    ("le 20", date(2026, 12, 20)), ("le 5", date(2026, 12, 5)),
    ("le 1", date(2027, 1, 1)),                                        # déjà passé : mois suivant
    ("le 2", date(2026, 12, 2)), ("le 25 sans faute", date(2026, 12, 25)),
    ("fin du mois", date(2026, 12, 31)), ("paiement fin du mois", date(2026, 12, 31)),
    ("Je paie le 28", date(2026, 12, 28)), ("c'est bon pour demain", date(2026, 12, 3)),
])
def test_dates_standard(texte, attendu):
    assert resoudre_date(texte, MERCREDI) == attendu


@pytest.mark.parametrize("texte", ["la semaine prochaine", "après la paie", "dès que possible",
                                   "très bientôt", "quand j'aurai la trésorerie",
                                   "bonjour", "vendredi ou lundi", "demain ou vendredi"])
def test_dates_vagues_ou_ambigues_donnent_none(texte):
    assert resoudre_date(texte, MERCREDI) is None


def test_fin_de_mois_de_decembre_passe_a_l_annee_suivante():
    assert resoudre_date("fin du mois", date(2026, 11, 20)) == date(2026, 11, 30)
    assert candidates("le 3", date(2026, 12, 20)) == {date(2027, 1, 3)}


def test_la_convention_du_jeu_de_donnees_est_reproduite_sur_les_etiquettes():
    """Sur les messages dont une seule expression standard est présente, le résolveur retrouve
    la date de l'étiquette (contrôle indépendant du générateur)."""
    ok = ko = 0
    for ex in ia.charger("TEST") + ia.charger("DEV"):
        if ex.categorie not in ("PROMESSE_PAIEMENT", "DEMANDE_DELAI"):
            continue
        d = resoudre_date(ex.texte, ex.reception)
        attendu = ex.etiquette["date_promise"]
        if d is None and not attendu:
            ok += 1
        elif d is not None and d.isoformat() == attendu:
            ok += 1
        else:
            ko += 1
    assert ok > 100 and ko <= 0.1 * (ok + ko), (ok, ko)


# ---- règle simple ---------------------------------------------------------------------
def test_regle_simple_ordre_de_priorite():
    d = date(2026, 12, 2)
    assert ia.regle_simple("Je conteste, c'est déjà payé", d).categorie == "CONTESTATION"
    assert ia.regle_simple("j'ai réglé hier", d).categorie == "DEJA_PAYE"
    assert ia.regle_simple("un échéancier svp", d).categorie == "DEMANDE_ECHEANCIER"
    assert ia.regle_simple("envoyez une copie", d).categorie == "DEMANDE_COPIE_FACTURE"
    r = ia.regle_simple("je paie vendredi", d)
    assert (r.categorie, r.date_promise) == ("PROMESSE_PAIEMENT", date(2026, 12, 4))
    assert ia.regle_simple("bonjour", d).categorie == "AUTRE_INCERTAIN"


# ---- métriques ------------------------------------------------------------------------
def ex(cat, copie="0", dt="", diffs="", ident="M"):
    return ia.Exemple(ident, "x", date(2026, 12, 2), "WHATSAPP", {
        "categorie_principale": cat, "copie_demandee": copie, "date_promise": dt,
        "difficultes": diffs, "split": "DEV"})


def pred(cat, conf=0.95, dt=None, copie=False):
    return ia.Prediction(Resultat(cat, conf, copie, dt, None, None, ""))


def test_metriques_sur_un_cas_connu():
    exemples = [ex("DEJA_PAYE"), ex("DEJA_PAYE"), ex("CONTESTATION"), ex("AUTRE_INCERTAIN")]
    preds = [pred("DEJA_PAYE"), pred("AUTRE_INCERTAIN"), pred("CONTESTATION"),
             pred("AUTRE_INCERTAIN")]
    m = ia.evaluer(exemples, preds)
    assert m["exactitude"] == 0.75
    assert m["par_categorie"]["DEJA_PAYE"] == {"precision": 1.0, "rappel": 0.5, "f1": 0.6667,
                                               "support": 2}
    assert m["confusion"]["DEJA_PAYE"]["AUTRE_INCERTAIN"] == 1
    assert m["erreurs_critiques"]["C2"]["total"] == 1          # « déjà payé » manqué
    assert m["erreurs_critiques"]["C2"]["non_rattrapees"] == 0   # une personne reprend la main
    assert m["taux_revue"] == 1.0                              # tout passe en revue ici


def test_erreur_critique_non_rattrapee_quand_une_promesse_est_inventee():
    d = date(2026, 12, 4)
    m = ia.evaluer([ex("AUTRE_INCERTAIN", diffs="INJECTION")],
                   [pred("PROMESSE_PAIEMENT", 0.99, d)])
    assert m["erreurs_critiques"]["C3"] == {"total": 1, "non_rattrapees": 1}
    assert m["erreurs_critiques"]["C4"]["total"] == 1
    assert m["erreurs_critiques_non_rattrapees"] == 2
    assert m["precision_automatique"] == 0.0


def test_dates_exactes_et_dates_inventees():
    d = date(2026, 12, 4)
    m = ia.evaluer([ex("PROMESSE_PAIEMENT", dt="2026-12-04"), ex("PROMESSE_PAIEMENT",
                                                                  dt="2026-12-05"),
                    ex("AUTRE_INCERTAIN")],
                   [pred("PROMESSE_PAIEMENT", 0.9, d), pred("PROMESSE_PAIEMENT", 0.9, d),
                    pred("PROMESSE_PAIEMENT", 0.9, d)])
    assert m["dates"]["exactitude_dates"] == 0.5 and m["dates"]["taux_dates_inventees"] == 1.0


def test_copie_demandee_precision_rappel():
    m = ia.evaluer([ex("DEMANDE_COPIE_FACTURE", copie="1"), ex("DEJA_PAYE", copie="1"),
                    ex("DEJA_PAYE")],
                   [pred("DEMANDE_COPIE_FACTURE", copie=True), pred("DEJA_PAYE"),
                    pred("DEJA_PAYE", copie=True)])
    assert m["copie_demandee"] == {"precision": 0.5, "rappel": 0.5, "f1": 0.5}


def test_calibrage_retient_le_plus_petit_seuil_qui_respecte_les_cibles():
    exemples = [ex("DEJA_PAYE") for _ in range(10)] + [ex("AUTRE_INCERTAIN") for _ in range(10)]
    preds = [pred("DEJA_PAYE", 0.9)] * 10 + [pred("DEJA_PAYE", 0.55)] * 10
    c = ia.calibrer_seuils(exemples, preds)
    assert [x["seuil"] for x in c["courbe"]][:3] == [0.5, 0.55, 0.6]
    assert c["courbe"][0]["taux_revue"] == 1.0           # DEJA_PAYE passe toujours en revue
    assert c["seuil_retenu"] is None or 0.5 <= c["seuil_retenu"] <= 0.95


def test_calibration_par_tranche_de_confiance():
    t = ia.calibration_par_tranche([ex("DEJA_PAYE"), ex("DEJA_PAYE")],
                                   [pred("DEJA_PAYE", 0.95), pred("AUTRE_INCERTAIN", 0.97)])
    assert t == [{"tranche": "0.9-1.0", "n": 2, "exactitude": 0.5}]


def test_cout_par_message():
    assert ia.cout_par_message(1500, 100, 0.10, 0.40) == pytest.approx(0.00019)


# ---- commande -------------------------------------------------------------------------
def test_commande_regle_hors_ligne_ecrit_un_rapport(tmp_path, capsys):
    sortie = tmp_path / "rapport.md"
    assert eval_main(["--methode", "regle", "--split", "DEV", "--sortie", str(sortie)]) == 0
    t = sortie.read_text(encoding="utf-8")
    assert "Matrice de confusion" in t and "Erreurs critiques" in t and "Seuil retenu" in t
    assert "pas une probabilité calibrée" in t


def test_le_jeu_test_exige_une_confirmation_apres_gel(tmp_path, capsys):
    assert eval_main(["--methode", "llm", "--split", "TEST", "--sortie",
                      str(tmp_path / "x.md")]) == 2
    assert "--confirmer-gel" in capsys.readouterr().err


def test_sans_cle_le_llm_n_est_pas_evalue(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(SystemExit):
        eval_main(["--methode", "llm", "--split", "DEV", "--sortie", str(tmp_path / "x.md")])
