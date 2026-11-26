"""Contrat d'API (T-N01 à T-N05) : routes exposées = section 13 de la spécification, openapi.json
identique à l'application, format d'erreur homogène, exemples de la spécification."""
import json
import re
import sys
from pathlib import Path

import pytest

from tests.aides_relances import D0, planifier
from tests.matrice_roles import MATRICE

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from scripts.export_openapi import contrat, serialiser  # noqa: E402


def routes_exposees(spec: dict) -> set[tuple[str, str]]:
    sortie = set()
    for chemin, ops in spec["paths"].items():
        for methode in ops:
            sortie.add((methode.upper(), re.sub(r"\{[^}]+\}", "{}", chemin)))
    return sortie


def test_N01_les_routes_exposees_sont_exactement_celles_de_la_section_13():
    exposees = routes_exposees(contrat())
    attendues = set(MATRICE)
    assert exposees - attendues == set(), f"routes en trop : {sorted(exposees - attendues)}"
    assert attendues - exposees == set(), f"routes manquantes : {sorted(attendues - exposees)}"
    assert len(exposees) == 62      # 59 de la section 13 + relance manuelle et 2 de rédactions


def test_N05_openapi_json_exporte_identique_a_l_application():
    fichier = RACINE / "openapi.json"
    assert fichier.is_file(), "lancer `make openapi`"
    assert fichier.read_text(encoding="utf-8") == serialiser(contrat()), \
        "openapi.json est périmé : lancer `make openapi`"


def test_toutes_les_operations_sont_documentees_en_francais():
    spec = contrat()
    for chemin, ops in spec["paths"].items():
        for methode, op in ops.items():
            assert op.get("summary"), f"{methode.upper()} {chemin} sans résumé"


def test_routes_en_prefixe_api_sans_numero_de_version():
    assert all(p.startswith("/api/") for p in contrat()["paths"])
    assert not any(re.match(r"/api/v\d", p) for p in contrat()["paths"])


def test_aucune_route_de_suppression():
    assert not [m for m, _ in routes_exposees(contrat()) if m == "DELETE"]


@pytest.mark.parametrize("methode,url,corps,code,erreur", [
    ("get", "/api/introuvable", None, 404, "INTROUVABLE"),
    ("get", "/api/factures/FAC-9999", None, 404, "INTROUVABLE"),
    ("get", "/api/factures?limite=0", None, 400, "VALIDATION"),
    ("post", "/api/paiements", {"montant": "x"}, 400, "VALIDATION"),
    ("post", "/api/avoirs", {"facture_id": "FAC-2026-0062", "date": D0, "montant": 10 ** 9,
                             "motif": "x"}, 422, "REGLE_METIER"),
    ("post", "/api/paiements", {"client_id": "CLI-0001", "date_paiement": D0, "montant": 1,
                                "mode": "ESPECES", "reference_externe": "E-C"}, 201, None),
])
def test_N03_format_d_erreur_homogene(api, gest, methode, url, corps, code, erreur):
    kw = {"headers": gest, **({"json": corps} if corps is not None else {})}
    r = getattr(api, methode)(url, **kw)
    assert r.status_code == code
    if erreur:
        e = r.json()["erreur"]
        assert e["code"] == erreur and e["message"] and "details" in e
        assert e["correlation_id"] == r.headers["X-Correlation-Id"]
        assert set(r.json()) == {"erreur"}


def test_N03_les_erreurs_d_authentification_ont_le_meme_format(api):
    r = api.get("/api/factures")
    assert r.status_code == 401 and set(r.json()["erreur"]) >= {"code", "message", "details"}


# ---- exemples de la spécification (T-N02) -------------------------------------------------
def test_N02_exemple_login(api):
    r = api.post("/api/auth/login", json={"nom_utilisateur": "gestionnaire",
                                          "mot_de_passe": "mdp-test-gestionnaire"}).json()
    assert set(r) == {"jeton", "expire_le", "utilisateur"}
    assert set(r["utilisateur"]) >= {"id", "nom_affiche", "role"}


def test_N02_exemple_detail_de_facture(api, gest):
    f = api.get("/api/factures/FAC-2026-0067", headers=gest).json()
    assert set(f) >= {"id", "numero", "client", "date_emission", "montant_ttc",
                      "conditions_paiement", "taux_penalite_retard", "statut",
                      "partiellement_payee", "solde", "affecte", "retard_jours", "suspension",
                      "echeances", "priorite"}
    assert set(f["client"]) == {"id", "raison_sociale"}
    assert set(f["echeances"][0]) >= {"id", "rang", "date_echeance", "montant_du", "affecte",
                                      "solde", "retard_jours", "etat"}
    assert set(f["priorite"]) == {"rang", "score", "points_anciennete", "points_solde",
                                  "points_historique"}
    assert isinstance(f["priorite"]["score"], str)            # décimal sérialisé en texte


def test_N02_exemple_paiement_et_rejeu(api, gest):
    corps = {"client_id": "CLI-0001", "date_paiement": D0, "montant": 1000, "mode":
             "MOBILE_MONEY", "reference_externe": "MM-SIM-2026-000731",
             "references_indiquees": ["FA-2026-0461"]}
    r = api.post("/api/paiements", headers=gest, json=corps)
    assert r.status_code == 201
    assert set(r.json()) >= {"id", "statut", "montant", "affectations", "reste_non_affecte",
                             "relances_annulees", "promesses_tenues", "deja_enregistre"}
    assert set(r.json()["affectations"][0]) == {"echeance_id", "montant_affecte", "mode"}
    again = api.post("/api/paiements", headers=gest, json=corps)
    assert again.status_code == 200 and again.json()["deja_enregistre"] is True


def test_N02_exemples_planification_et_detail_de_relance(api, gest):
    r = planifier(api, gest)
    assert set(r) >= {"traitement_id", "date_reference", "creees", "sautees",
                      "reportees_espacement", "escalades", "suspendues"}
    assert set(r["suspendues"][0]) == {"echeance_id", "motif"}
    rel = api.get("/api/relances?statut=EN_ATTENTE_VALIDATION", headers=gest)
    assert rel.json()["total"] == 0
    liste = api.get("/api/relances?statut=PLANIFIEE&limite=1", headers=gest).json()["elements"]
    d = api.get(f"/api/relances/{liste[0]['id']}", headers=gest).json()
    assert set(d) >= {"id", "client_id", "canal", "etape", "ton", "date_prevue", "statut",
                      "motif", "lignes", "total_solde", "revue_id", "contenu_apercu"}
    assert set(d["lignes"][0]) == {"echeance_id", "facture_numero", "etape_echeance",
                                   "decision", "solde"}


def test_N02_exemple_message_et_classification(api, gest, faux_llm):
    from app.ia.faux import sortie
    r = api.post("/api/messages", headers=gest, json={
        "client_id": "CLI-0001", "canal": "WHATSAPP", "contenu": "Je paie vendredi svp",
        "facture_citee": "FA-2026-0461", "reference_externe": "WA-SIM-000812"})
    assert r.status_code == 201 and set(r.json()) == {"id", "statut_traitement",
                                                      "facture_citee_id"}
    faux_llm.programmer(r.json()["id"], sortie("PROMESSE_PAIEMENT", 0.93,
                                               date_promise="2026-12-18"))
    m = api.post(f"/api/messages/{r.json()['id']}/classer?synchrone=true", headers=gest).json()
    assert set(m) >= {"id", "statut_traitement", "categorie_ia", "confiance", "copie_demandee",
                      "date_promise_extraite", "decision_ia", "modele_version", "promesse_id"}


def test_N02_exemple_explication_et_tableau_de_bord(api, gest):
    e = api.get("/api/factures/FAC-2026-0067/explication", headers=gest).json()
    assert set(e) >= {"facture", "calcul", "affectations", "avoirs", "contestations",
                      "promesses", "accords", "relances", "messages", "journal"}
    assert set(e["calcul"]["regle_statut"]) >= {"appliquee", "ecartees", "motif"}
    t = api.get("/api/tableau-de-bord", headers=gest).json()
    assert set(t) >= {"date_reference", "encours", "factures_par_statut", "retards", "relances",
                      "actions_suspendues", "reglements_simules", "revue", "messages",
                      "promesses"}


def test_N04_pagination_tri_filtres_identiques_sur_toutes_les_listes(api, gest):
    for url in ("/api/clients", "/api/factures", "/api/echeances", "/api/priorisation",
                "/api/imports", "/api/paiements", "/api/avoirs", "/api/relances",
                "/api/relances/suspensions", "/api/canaux/envois", "/api/messages",
                "/api/contestations", "/api/promesses", "/api/accords", "/api/revue",
                "/api/journal"):
        r = api.get(f"{url}?limite=2&decalage=1", headers=gest).json()
        assert set(r) >= {"total", "elements"} and len(r["elements"]) <= 2, url
        assert api.get(f"{url}?limite=201", headers=gest).status_code == 400, url
        assert api.get(f"{url}?tri=champ_inexistant", headers=gest).status_code == 400, url
    assert json.dumps(api.get("/api/factures?limite=1", headers=gest).json())
