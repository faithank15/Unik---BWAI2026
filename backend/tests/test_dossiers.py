"""Contestations, promesses, accords d'échéancier, file de revue et journal (S10, S12)."""
import pytest

from tests.aides import compter
from tests.aides_relances import D0, changer_date, envoyer, planifier, relance_du_client
from tests.verite import lire_scenario


def facture(api, h, fid):
    return api.get(f"/api/factures/{fid}", headers=h).json()


# ---- contestations ---------------------------------------------------------------------
def test_ouvrir_une_contestation_suspend_et_annule_les_relances(api, gest):
    planifier(api, gest)
    r = api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-2026-0061", "motif": "montant non conforme"})
    assert r.status_code == 201 and r.json()["statut"] == "OUVERTE"
    assert r.json()["date_ouverture"] == D0
    f = facture(api, gest, "FAC-2026-0061")
    assert f["statut"] == "CONTESTEE" and f["suspension"] == "SUSPENDU_CONTESTATION"
    rel = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert (rel["statut"], rel["motif"]) == ("ANNULEE", "CONTESTATION_OUVERTE")


def test_une_seule_contestation_ouverte_par_facture_et_echeance(api, gest, db_chargee):
    corps = {"facture_id": "FAC-2026-0061", "motif": "a"}
    a = api.post("/api/contestations", headers=gest, json=corps)
    b = api.post("/api/contestations", headers=gest, json={**corps, "motif": "b"})
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    assert compter(db_chargee, "contestations") == 7


def test_contestation_sur_une_echeance_seulement(api, gest, db_chargee):
    ech = db_chargee.execute("SELECT id FROM echeances WHERE facture_id = 'FAC-2026-0102' "
                             "AND etat = 'ACTIVE' ORDER BY rang LIMIT 1").fetchone()[0]
    r = api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-2026-0102", "echeance_id": ech, "motif": "tranche"})
    assert r.status_code == 201
    assert api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-2026-0061", "echeance_id": ech, "motif": "x"}).status_code == 422


def test_contestation_validations(api, gest):
    assert api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-9999", "motif": "x"}).status_code == 404
    assert api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-2026-0061", "motif": ""}).status_code == 400


def test_cloture_reservee_au_validateur(api, gest, valid):
    corps = {"resolution": "REJETEE", "commentaire": "client débouté"}
    assert api.post("/api/contestations/CTE-0001/cloturer", headers=gest, json=corps
                    ).status_code == 403
    r = api.post("/api/contestations/CTE-0001/cloturer", headers=valid, json=corps)
    assert r.status_code == 200
    assert (r.json()["statut"], r.json()["resolution"], r.json()["date_cloture"]) == (
        "CLOTUREE", "REJETEE", D0)
    assert facture(api, gest, "FAC-2026-0095")["statut"] == "ECHUE"


def test_cloture_validations(api, valid):
    assert api.post("/api/contestations/CTE-0001/cloturer", headers=valid, json={
        "resolution": "PEUT-ETRE", "commentaire": "x"}).status_code == 400
    assert api.post("/api/contestations/CTE-0001/cloturer", headers=valid, json={
        "resolution": "ACCEPTEE", "commentaire": ""}).status_code == 400
    assert api.post("/api/contestations/CTE-9999/cloturer", headers=valid, json={
        "resolution": "ACCEPTEE", "commentaire": "x"}).status_code == 404
    assert api.post("/api/contestations/CTE-0005/cloturer", headers=valid, json={
        "resolution": "ACCEPTEE", "commentaire": "x"}).status_code == 422   # déjà clôturée


def test_cloture_resout_la_revue_litige_du_message(api, gest, valid, faux_llm):
    from app.ia.faux import sortie
    mid = api.post("/api/messages", headers=gest, json={
        "client_id": "CLI-0028", "canal": "EMAIL", "contenu": "Facture fausse"}).json()["id"]
    faux_llm.programmer(mid, sortie("CONTESTATION", 0.9))
    m = api.post(f"/api/messages/{mid}/classer?synchrone=true", headers=gest).json()
    api.post(f"/api/contestations/{m['contestation_id']}/cloturer", headers=valid, json={
        "resolution": "ACCEPTEE", "commentaire": "avoir à émettre"})
    revues = api.get("/api/revue?type=LITIGE&client_id=CLI-0028", headers=gest
                     ).json()["elements"]
    assert [r["statut"] for r in revues] == ["RESOLUE"]


def test_S10_suspension_puis_reprise_apres_cloture(api, gest, valid):
    a = lire_scenario("S10")["attendu"]
    planifier(api, gest)
    s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
    assert {x["facture_id"] for x in s if x["motif"] == "SUSPENDU_CONTESTATION"} == set(
        a["contestations_ouvertes"])
    assert relance_du_client(api, gest, "CLI-0014", date=D0, statut="PLANIFIEE") is None
    api.post("/api/contestations/CTE-0002/cloturer", headers=valid, json={
        "resolution": "REJETEE", "commentaire": "rejetée"})
    planifier(api, gest)                      # même jour : reprise à l'étape non traitée
    voulu = a["apres_cloture_CTE_0002"][0]
    r = relance_du_client(api, gest, "CLI-0014", date=D0, statut="PLANIFIEE")
    assert r["etape"] == voulu["etape"] == "R2"
    assert [x["echeance_id"] for x in r["lignes"]] == [voulu["echeances"].split(":")[0]]
    envoyer(api, gest)
    assert relance_du_client(api, gest, "CLI-0014", date=D0, statut="ENVOYEE_SIM")


# ---- promesses --------------------------------------------------------------------------
def test_promesse_manuelle_suspend_les_relances(api, gest):
    r = api.post("/api/promesses", headers=gest, json={
        "facture_id": "FAC-2026-0061", "date_promise": "2026-12-18", "montant_promis": 5000})
    assert r.status_code == 201
    assert (r.json()["statut"], r.json()["origine"], r.json()["id"]) == (
        "EN_COURS", "MANUELLE", "PRO-0007")
    assert facture(api, gest, "FAC-2026-0061")["suspension"] == "SUSPENDU_PROMESSE"


def test_une_nouvelle_promesse_annule_l_ancienne(api, gest, db_chargee):
    api.post("/api/promesses", headers=gest, json={
        "facture_id": "FAC-2026-0061", "date_promise": "2026-12-18"})
    api.post("/api/promesses", headers=gest, json={
        "facture_id": "FAC-2026-0061", "date_promise": "2026-12-20"})
    statuts = [r[0] for r in db_chargee.execute(
        "SELECT statut FROM promesses_paiement WHERE facture_id = 'FAC-2026-0061' ORDER BY id")]
    assert statuts == ["ANNULEE", "EN_COURS"]
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'PROMESSE_ANNULEE'").fetchone()[0] == 1


@pytest.mark.parametrize("corps,code", [
    ({"facture_id": "FAC-2026-0061", "date_promise": "2026-12-14"}, 422),    # passée
    ({"facture_id": "FAC-2026-0061", "date_promise": "nimporte"}, 400),
    ({"facture_id": "FAC-2026-0001", "date_promise": "2026-12-18"}, 422),    # soldée
    ({"facture_id": "FAC-2026-0118", "date_promise": "2026-12-18"}, 422),    # annulée
    ({"facture_id": "FAC-9999", "date_promise": "2026-12-18"}, 404),
    ({"facture_id": "FAC-2026-0061", "date_promise": "2026-12-18", "montant_promis": 0}, 400)])
def test_promesse_refus(api, gest, corps, code):
    assert api.post("/api/promesses", headers=gest, json=corps).status_code == code


def test_promesse_au_dela_du_plafond_reservee_au_validateur(api, gest, valid):
    corps = {"facture_id": "FAC-2026-0061", "date_promise": "2027-03-01"}
    r = api.post("/api/promesses", headers=gest, json=corps)
    assert r.status_code == 403 and r.json()["erreur"]["details"]["role_requis"] == "VALIDATEUR"
    assert api.post("/api/promesses", headers=valid, json=corps).status_code == 201


def test_annuler_une_promesse(api, gest):
    assert api.post("/api/promesses/PRO-0001/annuler", headers=gest).json()["statut"] == "ANNULEE"
    assert facture(api, gest, "FAC-2026-0107")["suspension"] is None
    assert api.post("/api/promesses/PRO-0001/annuler", headers=gest).status_code == 422
    assert api.post("/api/promesses/PRO-0005/annuler", headers=gest).status_code == 422
    assert api.post("/api/promesses/PRO-9999/annuler", headers=gest).status_code == 404


def test_liste_des_promesses_et_filtres(api, gest):
    r = api.get("/api/promesses?statut=EN_COURS&limite=200", headers=gest).json()
    assert r["total"] == 4
    assert api.get("/api/promesses?statut=NIMPORTE", headers=gest).status_code == 400


# ---- accords ----------------------------------------------------------------------------
TRANCHES = [{"date_echeance": "2026-12-30", "montant": None},
            {"date_echeance": "2027-01-30", "montant": None}]


def tranches_pour(api, h, fid, n=2):
    ttc = facture(api, h, fid)["montant_ttc"]
    part = (ttc // n) // 500 * 500
    t = [{"date_echeance": f"2027-0{i + 1}-15", "montant": part} for i in range(n)]
    t[-1]["montant"] = ttc - part * (n - 1)
    return t


def test_proposer_un_accord_sans_effet_sur_les_echeances(api, gest, db_chargee):
    t = tranches_pour(api, gest, "FAC-2026-0062")
    r = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0062",
                                                     "tranches": t})
    assert r.status_code == 201
    assert (r.json()["statut"], r.json()["nb_tranches"]) == ("PROPOSE", 2)
    assert len(facture(api, gest, "FAC-2026-0062")["echeances"]) == 1
    assert facture(api, gest, "FAC-2026-0062")["statut"] == "ECHUE"


@pytest.mark.parametrize("modif,regle", [
    (lambda t: t[:1], "TRANCHES_INSUFFISANTES"),
    (lambda t: [t[0], {**t[1], "montant": t[1]["montant"] + 500}], "SOMME_TRANCHES_DIFFERENTE"),
    (lambda t: [t[1], t[0]], "DATES_INVALIDES"),
    (lambda t: [{**t[0], "date_echeance": "2026-12-10"}, t[1]], "DATES_INVALIDES")])
def test_accord_refus_regles_metier(api, gest, modif, regle):
    t = modif(tranches_pour(api, gest, "FAC-2026-0062"))
    r = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0062",
                                                     "tranches": t})
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == regle


def test_accord_impossible_sur_une_facture_partiellement_payee(api, gest):
    t = tranches_pour(api, gest, "FAC-2026-0087")
    r = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0087",
                                                     "tranches": t})
    assert r.status_code == 422
    assert r.json()["erreur"]["details"]["regle"] == "ACCORD_IMPOSSIBLE_PAIEMENT_PARTIEL"


def test_accord_facture_soldee_ou_inconnue(api, gest):
    t = [{"date_echeance": "2027-01-15", "montant": 500}, {"date_echeance": "2027-02-15",
                                                           "montant": 500}]
    assert api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0001",
                                                        "tranches": t}).status_code == 422
    assert api.post("/api/accords", headers=gest, json={"facture_id": "FAC-9999",
                                                        "tranches": t}).status_code == 404


def test_accepter_un_accord_remplace_les_echeances_et_annule_les_relances(
        api, gest, valid, db_chargee):
    planifier(api, gest)
    t = tranches_pour(api, gest, "FAC-2026-0062", 3)
    acc = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0062",
                                                       "tranches": t}).json()
    assert api.post(f"/api/accords/{acc['id']}/accepter", headers=gest).status_code == 403
    r = api.post(f"/api/accords/{acc['id']}/accepter", headers=valid)
    assert r.status_code == 200 and r.json()["statut"] == "ACCEPTE"
    assert r.json()["accepte_par"] == "USR-0002"
    f = facture(api, gest, "FAC-2026-0062")
    etats = [(e["rang"], e["etat"], e["montant_du"]) for e in f["echeances"]]
    assert etats[0][1] == "REMPLACEE" and len(etats) == 4          # l'historique reste intact
    assert [x[2] for x in etats[1:]] == [x["montant"] for x in t]
    assert f["statut"] == "COUVERTE_PAR_ECHEANCIER" and f["suspension"] == "SUSPENDU_ECHEANCIER"
    assert f["solde"] == f["montant_ttc"]
    rel = relance_du_client(api, gest, "CLI-0002", date=D0, etape="R1")
    assert (rel["statut"], rel["motif"]) == ("ANNULEE", "ECHEANCIER_ACCEPTE")
    assert api.post(f"/api/accords/{acc['id']}/accepter", headers=valid).status_code == 422
    assert all(r[0].startswith("ECH-") for r in db_chargee.execute(
        "SELECT id FROM echeances WHERE accord_id = ?", (acc["id"],)))


def test_refuser_un_accord(api, gest, valid):
    t = tranches_pour(api, gest, "FAC-2026-0062")
    acc = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0062",
                                                       "tranches": t}).json()
    assert api.post(f"/api/accords/{acc['id']}/refuser", headers=gest).status_code == 403
    r = api.post(f"/api/accords/{acc['id']}/refuser", headers=valid)
    assert r.json()["statut"] == "ROMPU"
    assert api.post(f"/api/accords/{acc['id']}/refuser", headers=valid).status_code == 422
    assert len(facture(api, gest, "FAC-2026-0062")["echeances"]) == 1


def test_accord_respecte_quand_toutes_les_tranches_sont_soldees(api, gest, valid):
    t = tranches_pour(api, gest, "FAC-2026-0062")
    acc = api.post("/api/accords", headers=gest, json={"facture_id": "FAC-2026-0062",
                                                       "tranches": t}).json()
    api.post(f"/api/accords/{acc['id']}/accepter", headers=valid)
    f = facture(api, gest, "FAC-2026-0062")
    api.post("/api/paiements", headers=gest, json={
        "client_id": "CLI-0002", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "VIREMENT", "reference_externe": "VIR-ACC-1",
        "references_indiquees": [f["numero"]]})
    assert api.get("/api/accords?statut=RESPECTE", headers=gest).json()["total"] == 1
    assert facture(api, gest, "FAC-2026-0062")["statut"] == "SOLDEE"


def test_S12_apres_acceptation_relance_sur_la_tranche_manquee_seulement(api, gest):
    a = lire_scenario("S12")["attendu"]
    planifier(api, gest)
    for tr in a["tranches_manquees"]:
        f = facture(api, gest, tr["facture_id"])
        r = relance_du_client(api, gest, f["client"]["id"], date=D0, etape="R1")
        assert r["lignes"][0]["echeance_id"] == tr["echeance_id"]


def test_liste_des_accords(api, gest):
    r = api.get("/api/accords?limite=200", headers=gest).json()
    assert r["total"] == 6
    assert api.get("/api/accords?statut=PROPOSE", headers=gest).json()["total"] == 1


# ---- revue ------------------------------------------------------------------------------
def test_file_de_revue_triee_par_priorite_puis_creation(api, gest):
    planifier(api, gest)
    r = api.get("/api/revue?limite=200", headers=gest).json()
    prios = [x["priorite"] for x in r["elements"]]
    assert prios == sorted(prios, reverse=True) and prios[0] == 90
    assert {x["type"] for x in r["elements"]} >= {"ESCALADE", "CANAL_INVALIDE",
                                                  "CONSENTEMENT_ABSENT", "PAIEMENT_AMBIGU"}
    assert api.get("/api/revue?type=ESCALADE", headers=gest).json()["total"] == 2
    assert api.get("/api/revue?client_id=CLI-0027", headers=gest).json()["total"] == 1
    assert api.get("/api/revue?statut=NIMPORTE", headers=gest).status_code == 400


def test_detail_d_une_entree_de_revue_avec_l_objet(api, gest, db_chargee):
    pid = db_chargee.execute("SELECT objet_id FROM file_revue WHERE type = 'PAIEMENT_AMBIGU' "
                             "LIMIT 1").fetchone()[0]
    rid = db_chargee.execute("SELECT id FROM file_revue WHERE objet_id = ?", (pid,)
                             ).fetchone()[0]
    d = api.get(f"/api/revue/{rid}", headers=gest).json()
    assert d["type"] == "PAIEMENT_AMBIGU" and d["objet"]["id"] == pid
    assert api.get("/api/revue/REV-9999", headers=gest).status_code == 404


def test_resoudre_une_revue_selon_le_role(api, gest, valid, db_chargee):
    planifier(api, gest)
    esc = db_chargee.execute("SELECT id FROM file_revue WHERE type = 'ESCALADE' LIMIT 1"
                             ).fetchone()[0]
    corps = {"decision": "APPEL_TELEPHONIQUE", "commentaire": "client joint"}
    assert api.post(f"/api/revue/{esc}/resoudre", headers=gest, json=corps).status_code == 403
    r = api.post(f"/api/revue/{esc}/resoudre", headers=valid, json=corps)
    assert r.status_code == 200
    assert (r.json()["statut"], r.json()["decideur"]) == ("RESOLUE", "USR-0002")
    assert api.post(f"/api/revue/{esc}/resoudre", headers=valid, json=corps).status_code == 422
    amb = db_chargee.execute("SELECT id FROM file_revue WHERE type = 'PAIEMENT_AMBIGU' LIMIT 1"
                             ).fetchone()[0]
    assert api.post(f"/api/revue/{amb}/resoudre", headers=gest, json={
        "decision": "SANS_SUITE"}).status_code == 200
    # une entrée résolue n'est jamais recréée : replanifier ne rouvre pas l'escalade
    planifier(api, gest)
    assert db_chargee.execute("SELECT COUNT(*) FROM file_revue WHERE id = ? AND statut = "
                              "'RESOLUE'", (esc,)).fetchone()[0] == 1
    assert compter(db_chargee, "file_revue") == len(
        db_chargee.execute("SELECT DISTINCT type, objet_type, objet_id FROM file_revue"
                           ).fetchall())


# ---- journal ----------------------------------------------------------------------------
def test_journal_filtres(api, gest, valid):
    api.post("/api/contestations", headers=gest, json={
        "facture_id": "FAC-2026-0061", "motif": "x"},)
    j = api.get("/api/journal?type_evenement=CONTESTATION_OUVERTE&limite=200",
                headers=gest).json()
    assert j["total"] == 1 and j["elements"][0]["objet_type"] == "CONTESTATION"
    cid = j["elements"][0]["correlation_id"]
    assert cid and api.get(f"/api/journal?correlation_id={cid}", headers=gest
                           ).json()["total"] >= 1
    assert api.get("/api/journal?objet_type=PAIEMENT&limite=200", headers=gest
                   ).json()["total"] >= 84
    assert api.get("/api/journal?du=2026-12-16", headers=gest).json()["total"] == 0
    assert api.get("/api/journal?du=pas-une-date", headers=gest).status_code == 400
    changer_date(api, valid, "2026-12-16")
    assert api.get("/api/journal?du=2026-12-16", headers=gest).json()["total"] >= 1


def test_journal_en_lecture_seule_aucune_route_d_ecriture(api, gest):
    for methode in ("post", "put", "delete", "patch"):
        assert getattr(api, methode)("/api/journal", headers=gest).status_code in (404, 405)


def test_aucune_route_de_suppression(api, gest):
    for url in ("/api/factures/FAC-2026-0061", "/api/paiements/PAY-0001",
                "/api/relances/REL-0001", "/api/messages/MSG-0001", "/api/clients/CLI-0001"):
        assert api.delete(url, headers=gest).status_code in (404, 405)
