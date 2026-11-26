"""Tableau de bord, balance âgée, explication d'une facture, comparaison à la référence, et
catalogue complet du journal (M4)."""
import pytest

from app.journal import CATALOGUE
from tests.aides import compter
from tests.aides_relances import D0, changer_date, envoyer, planifier, relances
from tests.verite import lire_csv


def tdb(api, h):
    r = api.get("/api/tableau-de-bord", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def attendu_depuis_la_verite():
    """Chiffres du tableau de bord recalculés à partir des fichiers de vérité terrain."""
    ech = {e["id"]: e for e in lire_csv("lot_nominal/echeances.csv")}
    fac = {f["id"]: f for f in lire_csv("lot_nominal/factures.csv")}
    statuts = {s["facture_id"]: s for s in lire_csv("verite_terrain/statuts_factures.csv")}
    lignes = []
    for s in lire_csv("verite_terrain/soldes_echeances.csv"):
        e = ech[s["echeance_id"]]
        if e["etat"] == "ACTIVE" and fac[e["facture_id"]]["statut_document"] == "VALIDEE" \
                and int(s["solde"]) > 0:
            lignes.append((int(s["solde"]), int(s["retard_jours"])))
    return statuts, lignes


# ---- tableau de bord ---------------------------------------------------------------------
def test_chiffres_du_tableau_de_bord_egaux_a_la_verite_terrain(api, gest):
    t = tdb(api, gest)
    statuts, lignes = attendu_depuis_la_verite()
    total = sum(s for s, _ in lignes)
    echu = sum(s for s, r in lignes if r > 0)
    assert t["date_reference"] == D0
    assert t["encours"] == {"total": total, "echu": echu, "non_echu": total - echu,
                            "nb_factures_ouvertes": len({k for k, v in statuts.items()
                                                         if int(v["solde_facture"]) > 0
                                                         and v["statut"] != "ANNULEE"})}
    assert t["factures_par_statut"] == {"ANNULEE": 3, "SOLDEE": 38, "CONTESTEE": 4,
                                        "COUVERTE_PAR_ECHEANCIER": 3, "ECHUE": 47,
                                        "NON_ECHUE": 25}
    retards = [r for _, r in lignes if r > 0]
    assert t["retards"]["nb_echeances_en_retard"] == len(retards)
    assert t["retards"]["retard_max_jours"] == max(retards)
    assert t["retards"]["retard_moyen_jours"] == round(sum(retards) / len(retards), 1)


def test_reglements_revue_messages_et_promesses_a_l_etat_initial(api, gest):
    t = tdb(api, gest)
    assert t["reglements_simules"]["non_affectes"] == {"nb": 2, "montant": 205000}
    assert sum(t["reglements_simules"]["par_mode"].values()) == t["reglements_simules"]["total"]
    assert t["reglements_simules"]["total"] == sum(
        int(p["montant"]) for p in lire_csv("lot_nominal/paiements.csv"))
    assert t["revue"] == {"total_ouvertes": 2, "par_type": {"PAIEMENT_AMBIGU": 2}}
    assert t["messages"] == {"par_statut": {}, "par_categorie": {}}
    assert t["promesses"] == {"en_cours": 4, "tenues": 0, "non_tenues": 2, "taux_tenues": 0.0}
    assert t["actions_suspendues"]["SUSPENDU_CONTESTATION"] == 4
    assert t["actions_suspendues"]["SUSPENDU_PROMESSE"] == 4
    assert t["actions_suspendues"]["SUSPENDU_ECHEANCIER"] >= 3
    assert t["actions_suspendues"]["SUSPENDU_MESSAGE_EN_ATTENTE"] == 0
    assert t["relances"] == {"planifiees": 0, "en_attente_validation": 0, "envoyees_sim": 0,
                             "annulees": 0, "sautees": 0}


def test_les_relances_du_jour_suivent_la_planification_et_l_envoi(api, gest):
    planifier(api, gest)
    assert tdb(api, gest)["relances"] == {"planifiees": 18, "en_attente_validation": 0,
                                          "envoyees_sim": 0, "annulees": 0, "sautees": 16}
    envoyer(api, gest)
    assert tdb(api, gest)["relances"] == {"planifiees": 0, "en_attente_validation": 4,
                                          "envoyees_sim": 14, "annulees": 0, "sautees": 16}


def test_chaque_chiffre_renvoie_a_la_liste_qui_l_explique(api, gest):
    t = tdb(api, gest)
    liens = t["liens"]

    def liste(url, **sub):
        r = api.get(url.format(**sub) + ("&" if "?" in url else "?") + "limite=200", headers=gest)
        assert r.status_code == 200, url
        return r.json()

    fact = liste(liens["encours.total"])
    assert fact["total"] == t["encours"]["nb_factures_ouvertes"]
    assert sum(f["solde"] for f in fact["elements"]) == t["encours"]["total"]
    ech = liste(liens["encours.echu"])
    assert sum(e["solde"] for e in ech["elements"]) == t["encours"]["echu"]
    assert ech["total"] == t["retards"]["nb_echeances_en_retard"]
    for statut, n in t["factures_par_statut"].items():
        assert liste(liens["factures_par_statut"], statut=statut)["total"] == n
    assert liste(liens["reglements_simules.non_affectes"])["total"] == \
        t["reglements_simules"]["non_affectes"]["nb"]
    assert liste(liens["revue"])["total"] == t["revue"]["total_ouvertes"]
    assert liste(liens["promesses"])["total"] == 6
    assert liste(liens["actions_suspendues"])["total"] == sum(t["actions_suspendues"].values())


def test_taux_de_promesses_tenues(api, gest, valid):
    f = api.get("/api/factures/FAC-2026-0107", headers=gest).json()
    api.post("/api/paiements", headers=gest, json={
        "client_id": "CLI-0003", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "VIREMENT", "reference_externe": "VIR-TDB-1",
        "references_indiquees": ["FA-2026-0507"]})
    p = tdb(api, gest)["promesses"]
    assert p["tenues"] == 1 and p["non_tenues"] == 2 and p["taux_tenues"] == round(1 / 3, 4)


# ---- balance âgée -----------------------------------------------------------------------
def test_balance_agee_somme_egale_a_l_encours_et_liens_coherents(api, gest):
    b = api.get("/api/tableau-de-bord/balance-agee", headers=gest).json()
    t = tdb(api, gest)
    assert [x["tranche"] for x in b["tranches"]] == [
        "non_echu", "1_30_jours", "31_60_jours", "61_90_jours", "plus_de_90_jours"]
    assert b["total"] == t["encours"]["total"] == sum(x["solde"] for x in b["tranches"])
    _, lignes = attendu_depuis_la_verite()
    voulu = {"non_echu": [s for s, r in lignes if r == 0],
             "1_30_jours": [s for s, r in lignes if 1 <= r <= 30],
             "31_60_jours": [s for s, r in lignes if 31 <= r <= 60],
             "61_90_jours": [s for s, r in lignes if 61 <= r <= 90],
             "plus_de_90_jours": [s for s, r in lignes if r > 90]}
    for x in b["tranches"]:
        assert (x["nb_echeances"], x["solde"]) == (len(voulu[x["tranche"]]),
                                                   sum(voulu[x["tranche"]])), x["tranche"]
        liste = api.get(x["liste"] + ("&" if "?" in x["liste"] else "?") + "limite=200",
                        headers=gest).json()
        # la liste n'est filtrée que sur le retard : elle contient aussi les échéances soldées
        # ou remplacées ; on vérifie seulement qu'elle recouvre la tranche
        assert liste["total"] >= x["nb_echeances"]
        assert x["tranche"] in ("non_echu",) or all(
            e["retard_jours"] > 0 for e in liste["elements"])


def test_filtres_de_retard_sur_les_echeances(api, gest):
    r = api.get("/api/echeances?retard_min=31&retard_max=60&limite=200", headers=gest).json()
    assert r["total"] > 0 and all(31 <= e["retard_jours"] <= 60 for e in r["elements"])
    assert api.get("/api/echeances?retard_min=-1", headers=gest).status_code == 400


# ---- explication d'une facture ----------------------------------------------------------
def test_explication_d_une_facture_echue(api, gest):
    e = api.get("/api/factures/FAC-2026-0061/explication", headers=gest).json()
    assert e["facture"]["statut"] == "ECHUE" and e["facture"]["retard_jours"] == 1
    r = e["calcul"]["regle_statut"]
    assert r["appliquee"] == "ECHUE"
    assert r["ecartees"] == ["ANNULEE", "SOLDEE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER"]
    assert r["motif"] == "Une échéance est en retard de 1 jour"
    assert all(x["motif"] for x in r["motifs_exclusion"])
    assert e["calcul"]["echeances"][0]["solde"] == e["facture"]["solde"]
    assert e["affectations"] == [] and e["relances"] == [] and e["journal"] == []


def test_explication_apres_planification_envoi_et_paiement_les_pieces_se_retrouvent(api, gest):
    planifier(api, gest)
    envoyer(api, gest)
    f = api.get("/api/factures/FAC-2026-0061", headers=gest).json()
    p = api.post("/api/paiements", headers=gest, json={
        "client_id": "CLI-0001", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "MOBILE_MONEY", "reference_externe": "MM-EXPL-1",
        "references_indiquees": ["FA-2026-0461"]}).json()
    e = api.get("/api/factures/FAC-2026-0061/explication", headers=gest).json()
    assert e["facture"]["statut"] == "SOLDEE"
    assert e["calcul"]["regle_statut"]["ecartees"] == ["ANNULEE"]
    assert e["calcul"]["regle_statut"]["motif"] == "Le solde de la facture est nul"
    assert [a["paiement_id"] for a in e["affectations"]] == [p["id"]]
    assert {r["etape_echeance"] for r in e["relances"]} == {"P", "R1"}
    sautee = [r for r in e["relances"] if r["statut"] == "SAUTEE"][0]
    assert sautee["motif"] == "P_APRES_ECHEANCE" and sautee["anterieure_au_chargement"] is False
    types = [j["type_evenement"] for j in e["journal"]]
    for t in ("RELANCE_PLANIFIEE", "RELANCE_SAUTEE", "RELANCE_ENVOYEE_SIM",
              "PAIEMENT_ENREGISTRE", "PAIEMENT_AFFECTE"):
        assert t in types, t
    assert [j["id"] for j in e["journal"]] == sorted(j["id"] for j in e["journal"])


def test_relances_historiques_signalees_comme_anterieures_au_chargement(api, gest):
    e = api.get("/api/factures/FAC-2026-0073/explication", headers=gest).json()
    assert len(e["relances"]) >= 3
    assert all(r["anterieure_au_chargement"] and r["statut"] == "ENVOYEE_SIM"
               for r in e["relances"])


@pytest.mark.parametrize("fid,statut,motif", [
    ("FAC-2026-0095", "CONTESTEE", "Une contestation est ouverte"),
    ("FAC-2026-0101", "COUVERTE_PAR_ECHEANCIER", "accord d'échéancier est accepté"),
    ("FAC-2026-0118", "ANNULEE", "Le document est annulé"),
    ("FAC-2026-0050", "NON_ECHUE", "Aucune échéance en retard"),
    ("FAC-2026-0001", "SOLDEE", "Le solde de la facture est nul")])
def test_explication_pour_chaque_statut(api, gest, fid, statut, motif):
    e = api.get(f"/api/factures/{fid}/explication", headers=gest).json()
    r = e["calcul"]["regle_statut"]
    assert r["appliquee"] == statut and motif in r["motif"]
    ordre = ["ANNULEE", "SOLDEE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER", "ECHUE"]
    assert r["ecartees"] == ordre[:ordre.index(statut)] if statut in ordre else \
        r["ecartees"] == ordre


def test_explication_dossiers_et_avoirs(api, gest):
    e = api.get("/api/factures/FAC-2026-0095/explication", headers=gest).json()
    assert [c["id"] for c in e["contestations"]] == ["CTE-0001"]
    e = api.get("/api/factures/FAC-2026-0107/explication", headers=gest).json()
    assert [p["id"] for p in e["promesses"]] == ["PRO-0001"]
    e = api.get("/api/factures/FAC-2026-0101/explication", headers=gest).json()
    assert [a["id"] for a in e["accords"]] == ["ACC-0001"]
    assert sum(1 for x in e["calcul"]["echeances"] if x["etat"] == "REMPLACEE") == 1
    e = api.get("/api/factures/FAC-2026-0118/explication", headers=gest).json()
    assert len(e["avoirs"]) == 1 and e["avoirs"][0]["montant"] == e["facture"]["affecte"]


def test_explication_facture_inconnue(api, gest):
    assert api.get("/api/factures/FAC-9999/explication", headers=gest).status_code == 404


# ---- comparaison à la référence ---------------------------------------------------------
def test_comparaison_a_la_regle_naive(api, gest):
    planifier(api, gest)
    envoyer(api, gest)
    c = api.get("/api/evaluation/comparaison-reference", headers=gest).json()
    t = tdb(api, gest)
    ref, sys_, gain = c["reference"], c["systeme"], c["gain"]
    assert ref["nb_relances_naives"] == t["retards"]["nb_echeances_en_retard"]
    assert ref["nb_relances_injustifiees"] == sum(ref["injustifiees_par_motif"].values()) > 0
    assert set(ref["injustifiees_par_motif"]) == {
        "SUSPENDU_CONTESTATION", "SUSPENDU_PROMESSE", "SUSPENDU_ECHEANCIER",
        "SUSPENDU_MESSAGE_EN_ATTENTE"}
    assert sys_["messages_apres_regroupement"] == sys_["relances_preparees"] == 18
    assert sys_["envois"] == 14 and sys_["annulations"] == 0
    assert gain["relances_injustifiees_evitees"] == ref["nb_relances_injustifiees"]
    assert gain["messages_economises_par_le_regroupement"] == sys_["lignes_preparees"] - 18 >= 3
    assert sys_["lignes_preparees"] < ref["nb_relances_naives"] + 100


def test_routes_du_tableau_exigent_un_jeton(api):
    for url in ("/api/tableau-de-bord", "/api/tableau-de-bord/balance-agee",
                "/api/evaluation/comparaison-reference",
                "/api/factures/FAC-2026-0061/explication"):
        assert api.get(url).status_code == 401


def test_performance_garde_fou_du_tableau_de_bord(api, gest):
    import time
    debut = time.monotonic()
    tdb(api, gest)
    assert time.monotonic() - debut < 0.5                  # T-PF03


# ---- journal : catalogue complet, un événement par opération, refus sans succès -------
def test_J02_chaque_evenement_du_catalogue_est_emis(api, gest, valid, faux_llm, reglages_charge):
    """Variante lisible : on tient le journal de la base AVANT le reset final et on exige que
    tout le catalogue y figure."""
    import sqlite3

    from tests.aides import fichiers_nominal

    def conn():
        c = sqlite3.connect(reglages_charge.database_path)
        c.row_factory = sqlite3.Row
        return c
    G = gest
    api.post("/api/auth/login", json={"nom_utilisateur": "gestionnaire", "mot_de_passe": "x"})
    api.post("/api/relances/REL-0001/valider", headers=G)                    # ACCES_REFUSE
    api.post("/api/imports", headers=G, files=fichiers_nominal())            # IMPORT_DEJA_FAIT
    api.put("/api/parametres/seuil_gros_montant", headers=valid, json={"valeur": "500000"})
    corps = {"client_id": "CLI-0001", "date_paiement": D0, "montant": 3000, "mode": "ESPECES",
             "reference_externe": "ESP-CAT-1", "references_indiquees": ["FA-INCONNUE"]}
    api.post("/api/paiements", headers=G, json=corps)
    api.post("/api/paiements", headers=G, json=corps)
    api.post("/api/avoirs", headers=G, json={"facture_id": "FAC-2026-0062", "date": D0,
                                             "montant": 500, "motif": "geste"})
    planifier(api, G)
    # entre la planification et l'envoi : ligne retirée (0039), relance annulée (0061 soldée,
    # 0063 promesse), promesse remplacée puis tenue (0107)
    f = api.get("/api/factures/FAC-2026-0039", headers=G).json()
    api.post("/api/paiements", headers=G, json={
        "client_id": "CLI-0024", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "VIREMENT", "reference_externe": "VIR-CAT-1",
        "references_indiquees": [f["numero"]]})                              # LIGNE_RETIREE
    f = api.get("/api/factures/FAC-2026-0061", headers=G).json()
    api.post("/api/paiements", headers=G, json={
        "client_id": "CLI-0001", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "MOBILE_MONEY", "reference_externe": "MM-CAT-1",
        "references_indiquees": [f["numero"]]})                              # RELANCE_ANNULEE
    for d in ("2026-12-20", "2026-12-22"):
        api.post("/api/promesses", headers=G, json={"facture_id": "FAC-2026-0063",
                                                    "date_promise": d})      # CREEE, ANNULEE
    f = api.get("/api/factures/FAC-2026-0107", headers=G).json()
    api.post("/api/paiements", headers=G, json={
        "client_id": "CLI-0003", "date_paiement": D0, "montant": f["montant_ttc"],
        "mode": "VIREMENT", "reference_externe": "VIR-CAT-3",
        "references_indiquees": [f["numero"]]})                              # PROMESSE_TENUE
    envoyer(api, G)
    attente = relances(api, G, statut="EN_ATTENTE_VALIDATION")
    api.post(f"/api/relances/{attente[0]['id']}/valider", headers=valid)
    api.post(f"/api/relances/{attente[1]['id']}/rejeter", headers=valid)
    m1 = api.post("/api/messages", headers=G, json={
        "client_id": "CLI-0004", "canal": "EMAIL", "contenu": "x"}).json()["id"]
    faux_llm.programmer(m1, "pas du json")
    api.post(f"/api/messages/{m1}/classer?synchrone=true", headers=G)
    m2 = api.post("/api/messages", headers=G, json={
        "client_id": "CLI-0005", "canal": "EMAIL", "contenu": "y"}).json()["id"]
    api.post(f"/api/messages/{m2}/classer?synchrone=true", headers=G)
    api.post(f"/api/messages/{m2}/valider-categorie", headers=G,
             json={"categorie": "AUTRE_INCERTAIN"})
    c = api.post("/api/contestations", headers=G, json={
        "facture_id": "FAC-2026-0064", "motif": "x"}).json()
    api.post(f"/api/contestations/{c['id']}/cloturer", headers=valid, json={
        "resolution": "REJETEE", "commentaire": "ok"})
    for fid, ref in (("FAC-2026-0065", "refus"), ("FAC-2026-0066", "accept")):
        ttc = api.get(f"/api/factures/{fid}", headers=G).json()["montant_ttc"]
        a = api.post("/api/accords", headers=G, json={"facture_id": fid, "tranches": [
            {"date_echeance": "2027-01-15", "montant": 500},
            {"date_echeance": "2027-02-15", "montant": ttc - 500}]}).json()
        api.post(f"/api/accords/{a['id']}/{'refuser' if ref == 'refus' else 'accepter'}",
                 headers=valid)
    f66 = api.get("/api/factures/FAC-2026-0066", headers=G).json()
    api.post("/api/paiements", headers=G, json={
        "client_id": f66["client"]["id"], "date_paiement": D0, "montant": f66["montant_ttc"],
        "mode": "VIREMENT", "reference_externe": "VIR-CAT-2",
        "references_indiquees": [f66["numero"]]})
    api.put("/api/parametres/simulation_llm_indisponible", headers=valid,
            json={"valeur": "true"})
    m3 = api.post("/api/messages", headers=G, json={
        "client_id": "CLI-0006", "canal": "EMAIL", "contenu": "z"}).json()["id"]
    api.post(f"/api/messages/{m3}/classer?synchrone=true", headers=G)
    for jour in ("2026-12-16", "2026-12-17", "2026-12-20"):
        changer_date(api, valid, jour)
        planifier(api, G)
        envoyer(api, G)
    api.post("/api/auth/logout", headers=valid)                              # DECONNEXION
    api.post("/api/auth/login", json={"nom_utilisateur": "validateur",
                                      "mot_de_passe": "mdp-test-validateur"})
    c1 = conn()
    types = {r[0] for r in c1.execute("SELECT DISTINCT type_evenement FROM journal")}
    manquants = sorted(CATALOGUE - types)
    assert not manquants, f"événements du catalogue jamais émis : {manquants}"


def test_J02_J03_chaque_operation_sensible_ecrit_un_evenement_avec_acteur_et_correlation(
        api, gest, db_chargee):
    avant = compter(db_chargee, "journal")
    r = api.post("/api/avoirs", headers={**gest, "X-Correlation-Id": "corr-avoir"}, json={
        "facture_id": "FAC-2026-0062", "date": D0, "montant": 500, "motif": "geste"})
    assert r.status_code == 201
    ev = db_chargee.execute("SELECT type_evenement, acteur_type, acteur_id, correlation_id, "
                            "horodatage, date_reference FROM journal WHERE id > ? AND "
                            "type_evenement = 'AVOIR_ENREGISTRE'", (avant,)).fetchall()
    assert len(ev) == 1
    assert (ev[0]["acteur_type"], ev[0]["acteur_id"], ev[0]["correlation_id"]) == (
        "UTILISATEUR", "USR-0001", "corr-avoir")
    assert ev[0]["horodatage"] and ev[0]["date_reference"] == D0


def test_J04_une_operation_refusee_n_ecrit_aucun_evenement_de_succes(api, gest, db_chargee):
    avant = compter(db_chargee, "journal")
    assert api.post("/api/paiements", headers=gest, json={
        "client_id": "CLI-0001", "date_paiement": "2027-01-01", "montant": 10,
        "mode": "ESPECES", "reference_externe": "E1"}).status_code == 422
    assert api.post("/api/avoirs", headers=gest, json={
        "facture_id": "FAC-2026-0062", "date": D0, "montant": 10 ** 9, "motif": "x"}
    ).status_code == 422
    assert api.post("/api/promesses", headers=gest, json={
        "facture_id": "FAC-2026-0001", "date_promise": D0}).status_code == 422
    assert api.post("/api/contestations/CTE-0005/cloturer", headers=gest, json={
        "resolution": "REJETEE", "commentaire": "x"}).status_code == 403
    nouveaux = [r[0] for r in db_chargee.execute(
        "SELECT type_evenement FROM journal WHERE id > ?", (avant,))]
    assert nouveaux == ["ACCES_REFUSE"]
