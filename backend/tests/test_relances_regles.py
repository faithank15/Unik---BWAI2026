"""Moteur de relances : planification (T-R), suspensions (T-S), envoi et revérification (T-E),
escalade (T-X), rôles et journal."""
import pytest

from app.db import transaction
from tests.aides import compter, corps_paiement, evenement
from tests.aides_relances import (
    D0,
    changer_date,
    ech_de,
    envoyer,
    planifier,
    relance_du_client,
    relances,
)


def payer(api, h, client, numero, montant, ref="MM-SIM-2026-TEST01", date_="2026-12-15"):
    return api.post("/api/paiements", headers=h, json={
        "client_id": client, "date_paiement": date_, "montant": montant, "mode": "MOBILE_MONEY",
        "reference_externe": ref, "references_indiquees": [numero]})


def montant(conn, facture_id):
    return conn.execute("SELECT montant_ttc FROM factures WHERE id = ?", (facture_id,)
                        ).fetchone()[0]


# ---- planification ---------------------------------------------------------------------
def test_R01_resume_de_planification(api, gest):
    r = planifier(api, gest)
    assert r["traitement_id"] == "TRT-0001" and r["date_reference"] == D0 and r["jour_ouvre"]
    assert r["creees"] == 18 and r["sautees"] == 16 and r["escalades"] == 2
    assert {s["motif"] for s in r["suspendues"]} == {
        "SUSPENDU_CONTESTATION", "SUSPENDU_PROMESSE", "SUSPENDU_ECHEANCIER"}


def test_R03_planifier_deux_fois_le_meme_jour_ne_cree_rien(api, gest, db_chargee):
    planifier(api, gest)
    avant = (compter(db_chargee, "relances"), compter(db_chargee, "relance_lignes"))
    r2 = planifier(api, gest)
    assert (compter(db_chargee, "relances"), compter(db_chargee, "relance_lignes")) == avant
    assert r2["creees"] == 0 and r2["sautees"] == 0 and r2["escalades"] == 0


def test_R04_R05_un_seul_message_groupe_au_ton_le_plus_grave(api, gest):
    planifier(api, gest)
    p = relance_du_client(api, gest, "CLI-0024", date=D0)
    assert p["etape"] == "GROUPE" and p["ton"] == "P" and len(p["lignes"]) == 2
    assert p["motif"] == "REGROUPE" and p["statut"] == "PLANIFIEE"
    g = relance_du_client(api, gest, "CLI-0007", date=D0, etape="GROUPE")
    assert g["ton"] == "R3"
    decisions = {x["etape_echeance"]: x["decision"] for x in g["lignes"]}
    assert decisions == {"R1": "ABSORBEE", "R3": "PREPAREE"}


def test_R08_rappel_p_saute_avec_motif(api, gest):
    planifier(api, gest)
    saute = relances(api, gest, client_id="CLI-0023", statut="SAUTEE", date=D0)
    assert [(x["etape"], x["motif"]) for x in saute] == [("P", "P_TROP_PROCHE")]
    apres = relances(api, gest, client_id="CLI-0001", statut="SAUTEE", date=D0)
    assert [x["motif"] for x in apres] == ["P_APRES_ECHEANCE"]


def test_R09_aucun_rappel_p_pour_un_accord_accepte(api, gest, db_chargee):
    planifier(api, gest)
    ech = ech_de(db_chargee, "FAC-2026-0104")
    n = db_chargee.execute(
        f"SELECT COUNT(*) FROM relance_lignes WHERE echeance_id IN ({','.join('?' * len(ech))})",
        ech).fetchone()[0]
    assert n == 0


def test_R10_pas_de_relance_pour_facture_soldee_ou_annulee(api, gest, db_chargee):
    planifier(api, gest)
    soldees = [r[0] for r in db_chargee.execute(
        "SELECT e.id FROM echeances e JOIN factures f ON f.id = e.facture_id WHERE "
        "f.id IN (SELECT id FROM factures WHERE id <= 'FAC-2026-0038' OR id >= 'FAC-2026-0118')"
    )]
    q = ",".join("?" * len(soldees))
    assert db_chargee.execute(
        f"SELECT COUNT(*) FROM relance_lignes l JOIN relances r ON r.id = l.relance_id "
        f"WHERE l.echeance_id IN ({q}) AND r.date_prevue = ?", soldees + [D0]).fetchone()[0] == 0


def test_R11_R12_seuil_strict_de_validation_humaine(api, gest, valid, db_chargee):
    m = montant(db_chargee, "FAC-2026-0061")
    api.put("/api/parametres/seuil_gros_montant", headers=valid, json={"valeur": str(m)})
    planifier(api, gest)
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ENVOYEE_SIM" and r["total_solde"] == m  # égal au seuil : pas de revue


def test_R11_au_dessus_du_seuil_en_attente_de_validation(api, gest, valid, db_chargee):
    m = montant(db_chargee, "FAC-2026-0061")
    api.put("/api/parametres/seuil_gros_montant", headers=valid, json={"valeur": str(m - 1)})
    planifier(api, gest)
    r0 = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r0["motif"] == "GROS_MONTANT"
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "EN_ATTENTE_VALIDATION" and r["revue_id"]
    assert compter(db_chargee, "envois_simules") == 72 + len([
        x for x in relances(api, gest, statut="ENVOYEE_SIM", date=D0)])


def test_R06_espacement_minimal_deux_jours(api, gest, valid):
    planifier(api, gest)
    envoyer(api, gest)
    # CLI-0008 a reçu un message le 15 : le 16, rien de nouveau pour lui
    changer_date(api, valid, "2026-12-16")
    r = planifier(api, gest)
    assert all(x["client_id"] != "CLI-0001"
               for x in relances(api, gest, statut="PLANIFIEE", date="2026-12-16"))
    assert r["reportees_espacement"] >= 0


def test_R07_rattrapage_une_seule_etape_espacee_de_cinq_jours(api, gest, valid):
    """Facture en retard de 45 jours : R1 le 15, puis R2 et R3 espacés d'au moins 5 jours."""
    dates = {}
    for jour in ("2026-12-15", "2026-12-16", "2026-12-17", "2026-12-18", "2026-12-19",
                 "2026-12-21", "2026-12-26"):
        changer_date(api, valid, jour)
        planifier(api, gest)
        envoyer(api, gest)
        for x in relances(api, gest, client_id="CLI-0005", statut="ENVOYEE_SIM", date=jour):
            dates.setdefault(x["etape"], jour)
    assert dates == {"R1": "2026-12-15", "R2": "2026-12-21", "R3": "2026-12-26"}


# ---- suspensions -----------------------------------------------------------------------
def test_S01_contestation_ouverte_suspend(api, gest):
    s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
    contestees = {x["facture_id"] for x in s if x["motif"] == "SUSPENDU_CONTESTATION"}
    assert contestees == {"FAC-2026-0095", "FAC-2026-0096", "FAC-2026-0097", "FAC-2026-0098"}
    planifier(api, gest)
    assert relance_du_client(api, gest, "CLI-0013", date=D0) is None


def test_S02_promesse_suspend_jusqu_a_la_date_plus_deux_jours(api, gest, valid, db_chargee):
    def motifs():
        s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
        return {x["facture_id"]: x["motif"] for x in s}
    assert motifs()["FAC-2026-0110"] == "SUSPENDU_PROMESSE"      # 13/12 + 2 = 15/12 inclus
    changer_date(api, valid, "2026-12-16")
    assert "FAC-2026-0110" not in motifs()
    planifier(api, gest)
    assert db_chargee.execute("SELECT statut FROM promesses_paiement WHERE id='PRO-0004'"
                              ).fetchone()[0] == "NON_TENUE"
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'PROMESSE_NON_TENUE'").fetchone()[0] == 1


def test_S03_echeancier_accepte_suspend_sauf_tranche_manquee(api, gest):
    s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
    echeancier = {x["facture_id"] for x in s if x["motif"] == "SUSPENDU_ECHEANCIER"}
    assert {"FAC-2026-0101", "FAC-2026-0104", "FAC-2026-0105"} <= echeancier
    assert "FAC-2026-0102" not in echeancier and "FAC-2026-0103" not in echeancier


def test_S04_message_en_attente_suspend_sauf_demande_de_copie(api, gest, db_chargee):
    def ajouter(msg_id, statut, categorie, facture=None):
        with transaction(db_chargee):
            db_chargee.execute(
                "INSERT INTO messages_entrants(id, client_id, canal, date_reception, contenu, "
                "facture_citee_id, statut_traitement, categorie_ia) VALUES (?,?,?,?,?,?,?,?)",
                (msg_id, "CLI-0001", "WHATSAPP", "2026-12-15T10:00:00+01:00", "x", facture,
                 statut, categorie))
    ajouter("MSG-9001", "EN_REVUE", "DEMANDE_COPIE_FACTURE")
    s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
    assert not [x for x in s if x["client_id"] == "CLI-0001"]       # copie : pas de suspension
    ajouter("MSG-9002", "A_CLASSER", None, "FAC-2026-0061")
    s = api.get("/api/relances/suspensions?limite=200", headers=gest).json()["elements"]
    mot = [x for x in s if x["client_id"] == "CLI-0001"]
    assert [x["facture_id"] for x in mot] == ["FAC-2026-0061"]       # facture citée seulement
    assert mot[0]["motif"] == "SUSPENDU_MESSAGE_EN_ATTENTE"
    assert api.get("/api/factures/FAC-2026-0061", headers=gest).json()["suspension"] == \
        "SUSPENDU_MESSAGE_EN_ATTENTE"
    assert api.get("/api/factures?suspendue=true&limite=200", headers=gest).json()["total"] >= 10
    assert api.get("/api/factures/FAC-2026-0062", headers=gest).json()["suspension"] is None


def test_priorisation_indique_la_suspension(api, gest):
    p = api.get("/api/priorisation?limite=200", headers=gest).json()["elements"]
    par = {x["facture_id"]: x["suspension"] for x in p}
    assert par["FAC-2026-0107"] == "SUSPENDU_PROMESSE"      # ECHUE suspendue : reste listée
    assert par["FAC-2026-0102"] is None                      # tranche manquée : relançable
    assert par["FAC-2026-0061"] is None and len(p) == 47


def test_S20_client_sans_consentement_ni_canal_valide_en_revue(api, gest, db_chargee):
    planifier(api, gest)
    assert relance_du_client(api, gest, "CLI-0027", date=D0) is None
    assert relance_du_client(api, gest, "CLI-0028", date=D0) is None
    revues = dict(db_chargee.execute("SELECT objet_id, type FROM file_revue WHERE type IN "
                                     "('CONSENTEMENT_ABSENT','CANAL_INVALIDE')").fetchall())
    assert revues == {"CLI-0027": "CONSENTEMENT_ABSENT", "CLI-0028": "CANAL_INVALIDE"}
    planifier(api, gest)  # rejouer ne recrée rien
    assert compter(db_chargee, "file_revue") == 2 + 2 + 2   # ambigus, escalades, contacts


# ---- envoi et revérification -----------------------------------------------------------
def test_E01_envoi_normal_ecrit_envoi_simule_et_evenement(api, gest, db_chargee):
    planifier(api, gest)
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ENVOYEE_SIM" and r["date_envoi"] == D0
    assert r["lignes"][0]["solde"] == montant(db_chargee, "FAC-2026-0061")
    boite = api.get("/api/canaux/envois?client_id=CLI-0001&limite=200", headers=gest).json()
    envoi = [e for e in boite["elements"] if e["relance_id"] == r["id"]]
    assert len(envoi) == 1
    assert envoi[0]["destinataire"] == "+2290100000001" and envoi[0]["objet"] is None
    assert "(simulation : aucun paiement réel)" in envoi[0]["contenu"]
    assert "MM-SIM-2026-" + r["id"][4:].zfill(6) in envoi[0]["contenu"]
    ev = db_chargee.execute("SELECT acteur_type, acteur_id FROM journal WHERE type_evenement = "
                            "'RELANCE_ENVOYEE_SIM' AND objet_id = ?", (r["id"],)).fetchall()
    assert [tuple(x) for x in ev] == [("UTILISATEUR", "USR-0001")]


def test_envoi_par_courriel_separe_objet_et_corps(api, gest):
    planifier(api, gest)
    envoyer(api, gest)
    boite = api.get("/api/canaux/envois?canal=EMAIL&client_id=CLI-0002&limite=200",
                    headers=gest).json()["elements"]
    nouveaux = [e for e in boite if e["date_envoi"] == D0]
    assert nouveaux and nouveaux[0]["objet"].startswith("Rappel : règlement en attente")
    assert not nouveaux[0]["contenu"].startswith("Objet")
    assert nouveaux[0]["destinataire"] == "contact@client-0002.example"


def test_E02_paiement_complet_annule_la_relance_aucun_envoi(api, gest, db_chargee):
    planifier(api, gest)
    f = db_chargee.execute("SELECT numero, montant_ttc FROM factures WHERE id='FAC-2026-0061'"
                           ).fetchone()
    p = payer(api, gest, "CLI-0001", f["numero"], f["montant_ttc"]).json()
    assert [x["motif"] for x in p["relances_annulees"]] == ["SOLDE_NUL"]
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ANNULEE" and r["motif"] == "SOLDE_NUL" and r["date_envoi"] is None
    assert db_chargee.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                              (r["id"],)).fetchone()[0] == 0


def test_E03_paiement_partiel_envoi_avec_le_nouveau_solde(api, gest, db_chargee):
    planifier(api, gest)
    f = db_chargee.execute("SELECT numero, montant_ttc FROM factures WHERE id='FAC-2026-0061'"
                           ).fetchone()
    p = payer(api, gest, "CLI-0001", f["numero"], 1000).json()
    assert p["relances_annulees"] == []
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ENVOYEE_SIM" and r["lignes"][0]["solde"] == f["montant_ttc"] - 1000
    boite = api.get("/api/canaux/envois?client_id=CLI-0001&limite=200", headers=gest).json()
    contenu = [e["contenu"] for e in boite["elements"] if e["relance_id"] == r["id"]][0]
    assert f"solde {(f['montant_ttc'] - 1000):,}".replace(",", " ") in contenu


@pytest.mark.parametrize("motif,sql,args", [
    ("CONTESTATION_OUVERTE",
     "INSERT INTO contestations(id, facture_id, motif, date_ouverture, statut) "
     "VALUES ('CTE-9001','FAC-2026-0061','test','2026-12-15','OUVERTE')", ()),
    ("PROMESSE_EN_COURS",
     "INSERT INTO promesses_paiement(id, client_id, facture_id, date_promise, statut) "
     "VALUES ('PRO-9001','CLI-0001','FAC-2026-0061','2026-12-20','EN_COURS')", ()),
    ("MESSAGE_EN_ATTENTE",
     "INSERT INTO messages_entrants(id, client_id, canal, date_reception, contenu, "
     "statut_traitement) VALUES ('MSG-9001','CLI-0001','WHATSAPP','2026-12-15T10:00:00+01:00',"
     "'x','A_CLASSER')", ()),
])
def test_E04_E05_E06_evenement_entre_planification_et_envoi_annule(
        api, gest, db_chargee, motif, sql, args):
    planifier(api, gest)
    with transaction(db_chargee):
        db_chargee.execute(sql, args)
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ANNULEE" and r["motif"] == motif


def test_E07_jour_non_ouvre_la_relance_reste_planifiee_puis_part_le_lundi(api, gest, valid):
    planifier(api, gest)
    changer_date(api, valid, "2026-12-20")
    r = envoyer(api, gest)
    assert r["envoyees"] == 0
    assert relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")["statut"] == "PLANIFIEE"
    p = planifier(api, gest)
    assert p["jour_ouvre"] is False and p["creees"] == 0
    changer_date(api, valid, "2026-12-21")
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")
    assert r["statut"] == "ENVOYEE_SIM" and r["date_envoi"] == "2026-12-21"


def test_E08_gros_montant_non_valide_n_est_jamais_envoye(api, gest, valid):
    planifier(api, gest)
    envoyer(api, gest)
    for jour in ("2026-12-16", "2026-12-17", "2026-12-19"):
        changer_date(api, valid, jour)
        planifier(api, gest)
        envoyer(api, gest)
    attente = relances(api, gest, statut="EN_ATTENTE_VALIDATION")
    assert {x["client_id"] for x in attente} >= {"CLI-0016", "CLI-0017", "CLI-0018", "CLI-0019"}


def test_E09_validation_par_un_validateur_puis_envoi_et_trace(api, gest, valid, db_chargee):
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0016", date=D0, etape="R1")["id"]
    r = api.post(f"/api/relances/{rid}/valider", headers=valid)
    assert r.status_code == 200 and r.json()["relance"]["statut"] == "ENVOYEE_SIM"
    assert r.json()["relance"]["valide_par"] == "USR-0002"
    types = [h["type_evenement"] for h in r.json()["relance"]["historique"]]
    assert types == ["RELANCE_PLANIFIEE", "RELANCE_EN_ATTENTE_VALIDATION", "RELANCE_VALIDEE",
                     "RELANCE_ENVOYEE_SIM"]
    assert db_chargee.execute("SELECT statut FROM file_revue WHERE objet_id = ?", (rid,)
                              ).fetchone()[0] == "RESOLUE"


def test_E09_valider_deux_fois_est_sans_effet(api, gest, valid, db_chargee):
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0016", date=D0, etape="R1")["id"]
    api.post(f"/api/relances/{rid}/valider", headers=valid)
    r = api.post(f"/api/relances/{rid}/valider", headers=valid)
    assert r.status_code == 200 and r.json()["resultat"] == "SANS_EFFET"
    assert db_chargee.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                              (rid,)).fetchone()[0] == 1


def test_E10_rejet_annule_avec_le_motif_du_rejet(api, gest, valid, db_chargee):
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0017", date=D0, etape="R1")["id"]
    r = api.post(f"/api/relances/{rid}/rejeter", headers=valid)
    assert r.json()["relance"]["statut"] == "ANNULEE"
    assert r.json()["relance"]["motif"] == "REJETEE_PAR_VALIDATEUR"
    assert db_chargee.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                              (rid,)).fetchone()[0] == 0


def test_E11_un_gestionnaire_ne_peut_ni_valider_ni_rejeter(api, gest, db_chargee):
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0016", date=D0, etape="R1")["id"]
    for action in ("valider", "rejeter"):
        r = api.post(f"/api/relances/{rid}/{action}", headers=gest)
        assert r.status_code == 403 and r.json()["erreur"]["code"] == "ACCES_REFUSE"
    assert relance_du_client(api, gest, "CLI-0016", date=D0, etape="R1")["statut"] == (
        "EN_ATTENTE_VALIDATION")
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'ACCES_REFUSE'").fetchone()[0] == 2


def test_validation_revoit_tout_avant_envoi(api, gest, valid, db_chargee):
    """Un paiement entre la mise en attente et la validation annule la relance."""
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0018", date=D0, etape="R1")["id"]
    f = db_chargee.execute("SELECT numero, montant_ttc FROM factures WHERE id='FAC-2026-0115'"
                           ).fetchone()
    p = payer(api, gest, "CLI-0018", f["numero"], f["montant_ttc"], ref="MM-SIM-2026-GROS01")
    assert [x["id"] for x in p.json()["relances_annulees"]] == [rid]
    r = api.post(f"/api/relances/{rid}/valider", headers=valid)
    assert r.json()["resultat"] == "SANS_EFFET" and r.json()["relance"]["statut"] == "ANNULEE"
    assert db_chargee.execute("SELECT statut FROM file_revue WHERE objet_id = ?", (rid,)
                              ).fetchone()[0] == "RESOLUE"


def test_annulation_partielle_retire_la_ligne_et_garde_le_reste(api, gest, db_chargee):
    planifier(api, gest)
    f = db_chargee.execute("SELECT numero, montant_ttc FROM factures WHERE id='FAC-2026-0039'"
                           ).fetchone()
    payer(api, gest, "CLI-0024", f["numero"], f["montant_ttc"], ref="MM-SIM-2026-PART01")
    r = relance_du_client(api, gest, "CLI-0024", date=D0)
    assert r["statut"] == "PLANIFIEE" and len(r["lignes"]) == 1
    assert r["etape"] == "P"
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'LIGNE_RETIREE'").fetchone()[0] == 1


def test_E_avoir_couvrant_annule_la_relance(api, gest, valid, db_chargee):
    """S21 : l'avoir couvre le solde d'une facture dont une relance est planifiée."""
    from tests.aides import evenement as ev
    planifier(api, gest)
    envoyer(api, gest)
    changer_date(api, valid, "2026-12-16")
    planifier(api, gest)
    a = ev("avoir_couvrant")
    r = api.post("/api/avoirs", headers=gest, json={
        "facture_id": a["facture_id"], "date": a["date"], "montant": int(a["montant"]),
        "motif": a["motif"]})
    assert r.status_code == 201
    assert [x["motif"] for x in r.json()["relances_annulees"]] == ["SOLDE_NUL"]
    assert api.get(f"/api/factures/{a['facture_id']}", headers=gest).json()["statut"] == "SOLDEE"
    envoyer(api, gest)
    assert relance_du_client(api, gest, "CLI-0014", date="2026-12-16")["statut"] == "ANNULEE"


# ---- escalade --------------------------------------------------------------------------
def test_X01_X03_escalade_apres_r3_sans_suite_une_seule_fois(api, gest, db_chargee):
    planifier(api, gest)
    planifier(api, gest)
    escalades = db_chargee.execute("SELECT objet_id, priorite FROM file_revue WHERE type = "
                                   "'ESCALADE' ORDER BY objet_id").fetchall()
    assert [tuple(x) for x in escalades] == [(ech_de(db_chargee, "FAC-2026-0085")[0], 90),
                                             (ech_de(db_chargee, "FAC-2026-0086")[0], 90)]
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'ESCALADE_CREEE'").fetchone()[0] == 2
    for e in escalades:
        assert db_chargee.execute("SELECT COUNT(*) FROM relance_lignes l JOIN relances r ON "
                                  "r.id = l.relance_id WHERE l.echeance_id = ? AND "
                                  "r.date_prevue >= ?", (e["objet_id"], D0)).fetchone()[0] == 0


def test_X02_paiement_avant_cinq_jours_aucune_escalade(api, gest, valid, db_chargee):
    """R3 envoyée le 14/12 pour les trois factures 0079-0081 : escalade attendue le 19/12."""
    ech = ech_de(db_chargee, "FAC-2026-0079")[0]
    for jour in ("2026-12-15", "2026-12-16", "2026-12-17", "2026-12-18"):
        changer_date(api, valid, jour)
        planifier(api, gest)
    assert db_chargee.execute("SELECT COUNT(*) FROM file_revue WHERE type='ESCALADE' AND "
                              "objet_id = ?", (ech,)).fetchone()[0] == 0
    for n in (79, 80, 81):
        f = db_chargee.execute("SELECT id, numero, montant_ttc, client_id FROM factures "
                               "WHERE id = ?", (f"FAC-2026-{n:04d}",)).fetchone()
        payer(api, gest, f["client_id"], f["numero"], f["montant_ttc"], ref=f"MM-SIM-2026-X{n}",
              date_="2026-12-18")
    changer_date(api, valid, "2026-12-19")
    planifier(api, gest)
    assert db_chargee.execute("SELECT COUNT(*) FROM file_revue WHERE type='ESCALADE' AND "
                              "objet_id = ?", (ech,)).fetchone()[0] == 0


# ---- contrôle d'accès et lectures ------------------------------------------------------
@pytest.mark.parametrize("methode,url", [
    ("post", "/api/relances/planifier"), ("post", "/api/relances/envoyer"),
    ("get", "/api/relances"), ("get", "/api/relances/suspensions"),
    ("get", "/api/relances/REL-0001"), ("get", "/api/canaux/envois"),
    ("post", "/api/relances/REL-0001/valider"), ("post", "/api/relances/REL-0001/rejeter"),
    ("post", "/api/admin/avancer")])
def test_U01_routes_du_moteur_exigent_un_jeton(api, methode, url):
    assert getattr(api, methode)(url).status_code == 401


def test_relance_inconnue_404_et_filtres_invalides(api, gest):
    assert api.get("/api/relances/REL-9999", headers=gest).status_code == 404
    assert api.get("/api/relances?statut=NIMPORTE", headers=gest).status_code == 400
    assert api.get("/api/relances?date=pas-une-date", headers=gest).status_code == 400


def test_avancer_avec_execution_planifie_et_envoie(api, valid, gest, db_chargee):
    r = api.post("/api/admin/avancer", headers=valid, json={"jours": 2, "executer": True})
    assert r.status_code == 200
    corps = r.json()
    assert corps["date_reference"] == "2026-12-17" and len(corps["resultats"]) == 2
    assert corps["resultats"][0]["planification"]["creees"] > 0
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE statut='ENVOYEE_SIM' AND "
                              "date_envoi = '2026-12-16'").fetchone()[0] > 0
    assert api.post("/api/admin/avancer", headers=gest, json={"jours": 1}).status_code == 403
    assert api.post("/api/admin/avancer", headers=valid, json={"jours": 0}).status_code == 400


def test_paiement_event_fichier_s07_style(api, gest):
    """Le paiement du fichier d'événement solde la facture visée par la relance du jour."""
    planifier(api, gest)
    p = api.post("/api/paiements", headers=gest,
                 json=corps_paiement(evenement("paiement_entre_preparation_et_envoi")))
    assert p.status_code == 201 and [x["motif"] for x in p.json()["relances_annulees"]] == [
        "SOLDE_NUL"]
