"""Sécurité de toutes les routes, parcourues depuis l'OpenAPI et la matrice des rôles :
401 sans jeton ou avec un jeton invalide, 403 avec le mauvais rôle, secrets, performance."""
import re

import pytest

from app.security import neutraliser_formule
from tests.matrice_roles import AUTH, MATRICE, PUBLIC, SELON, VALIDATEUR

ROUTES = sorted(MATRICE)


def url(chemin: str) -> str:
    return re.sub(r"\{\}", "X-1", chemin)


def appeler(api, methode: str, chemin: str, **kw):
    corps = {} if methode in ("POST", "PUT") and "files" not in kw else None
    if corps is not None:
        kw.setdefault("json", corps)
    return api.request(methode, url(chemin), **kw)


def test_la_matrice_couvre_exactement_les_routes_exposees():
    from tests.test_contrat import contrat, routes_exposees
    assert routes_exposees(contrat()) == set(MATRICE)


@pytest.mark.parametrize("methode,chemin", [r for r in ROUTES if MATRICE[r] != PUBLIC])
def test_U01_chaque_route_protegee_refuse_l_absence_de_jeton(api, methode, chemin):
    r = appeler(api, methode, chemin)
    assert r.status_code == 401, (methode, chemin, r.text)
    assert r.json()["erreur"]["code"] == "NON_AUTHENTIFIE"


@pytest.mark.parametrize("methode,chemin", [r for r in ROUTES if MATRICE[r] != PUBLIC])
@pytest.mark.parametrize("entete", [
    {"Authorization": "Bearer jeton-invalide"}, {"Authorization": "Basic YWJjOmRlZg=="},
    {"Authorization": "Bearer "}])
def test_U02_jeton_invalide_donne_401(api, methode, chemin, entete):
    assert appeler(api, methode, chemin, headers=entete).status_code == 401


@pytest.mark.parametrize("methode,chemin", [r for r in ROUTES if MATRICE[r] == VALIDATEUR])
def test_U03_route_reservee_au_validateur_appelee_par_un_gestionnaire_donne_403(
        api, gest, db_chargee, methode, chemin):
    avant = db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                               "'ACCES_REFUSE'").fetchone()[0]
    r = appeler(api, methode, chemin, headers=gest)
    assert r.status_code == 403, (methode, chemin, r.text)
    assert r.json()["erreur"]["code"] == "ACCES_REFUSE"
    apres = db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                               "'ACCES_REFUSE'").fetchone()[0]
    assert apres == avant + 1                       # événement ACCES_REFUSE, un par refus


@pytest.mark.parametrize("methode,chemin", [r for r in ROUTES if MATRICE[r] == AUTH
                                            and r[0] == "GET" and "{}" not in r[1]])
def test_les_routes_authentifiees_acceptent_les_deux_roles(api, gest, valid, methode, chemin):
    assert api.get(chemin, headers=gest).status_code == 200
    assert api.get(chemin, headers=valid).status_code == 200


def test_routes_publiques_seulement_sante_et_login():
    assert {r for r in MATRICE if MATRICE[r] == PUBLIC} == {("GET", "/api/sante"),
                                                            ("POST", "/api/auth/login")}


def test_routes_selon_le_role_ont_des_tests_dedies():
    # promesse au-delà du plafond, validation d'une catégorie hors plafond, revue réservée :
    # couverts dans test_dossiers.py et test_messages.py
    assert {r for r in MATRICE if MATRICE[r] == SELON} == {
        ("POST", "/api/messages/{}/valider-categorie"), ("POST", "/api/promesses"),
        ("POST", "/api/revue/{}/resoudre")}


def test_jeton_d_une_session_revoquee_ou_d_un_utilisateur_desactive(api, gest, db_chargee):
    assert api.get("/api/auth/moi", headers=gest).status_code == 200
    db_chargee.execute("UPDATE utilisateurs SET actif = 0 WHERE id = 'USR-0001'")
    assert api.get("/api/auth/moi", headers=gest).status_code == 401


def test_aucun_secret_dans_les_reponses_d_api(api, gest, valid):
    texte = ""
    for url_ in ("/api/sante", "/api/parametres", "/api/contexte", "/api/auth/moi",
                 "/api/journal?limite=200"):
        texte += api.get(url_, headers=valid).text
    assert "mot_de_passe" not in texte and "scrypt$" not in texte
    assert "llm_api_key" not in texte.lower() and "token_hash" not in texte


def test_les_reponses_d_erreur_ne_contiennent_aucune_trace(api, gest):
    for r in (api.post("/api/paiements", headers=gest, content=b"{", ),
              api.get("/api/factures/FAC-9999", headers=gest)):
        assert "Traceback" not in r.text and "File \"" not in r.text


# ---- export CSV : injection de formules ---------------------------------------------------
@pytest.mark.parametrize("valeur", ["=1+1", "+33", "-2+3", "@SUM(A1)", "\t=x", "\r=x"])
def test_I07_valeurs_dangereuses_prefixees_d_une_apostrophe(valeur):
    assert neutraliser_formule(valeur) == "'" + valeur


@pytest.mark.parametrize("valeur", ["Cotonou", "FA-2026-0412", "1 000", 12345, -5, None, ""])
def test_valeurs_normales_inchangees(valeur):
    assert neutraliser_formule(valeur) == valeur


# ---- performance : garde-fous (T-PF) ------------------------------------------------------
def duree(fn):
    import time
    d = time.monotonic()
    fn()
    return time.monotonic() - d


def test_PF01_liste_priorisee_en_moins_de_300_ms(api, gest):
    assert duree(lambda: api.get("/api/priorisation?limite=200", headers=gest)) < 0.3


def test_PF02_planification_d_une_journee_complete_en_moins_de_2_s(api, gest):
    assert duree(lambda: api.post("/api/relances/planifier", headers=gest)) < 2


def test_PF03_tableau_de_bord_en_moins_de_500_ms(api, gest):
    assert duree(lambda: api.get("/api/tableau-de-bord", headers=gest)) < 0.5


def test_PF_liste_des_factures_et_explication_restent_rapides(api, gest):
    assert duree(lambda: api.get("/api/factures?limite=200", headers=gest)) < 0.5
    assert duree(lambda: api.get("/api/factures/FAC-2026-0073/explication",
                                 headers=gest)) < 0.5
