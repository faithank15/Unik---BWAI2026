"""Scénarios S07 à S09, S11 à S16, S19, S21 et S22, comparés à verite_terrain/scenarios/Sxx.json.
S10, S17, S18 et S23 (messages, IA, dossiers) arrivent avec le jalon M3."""
from datetime import date, timedelta

from tests.aides import corps_paiement, evenement
from tests.aides_relances import (
    D0,
    changer_date,
    ech_de,
    envoyer,
    planifier,
    relance_du_client,
    relances,
)
from tests.test_verite_relances import jour
from tests.verite import lire_scenario


def ligne(r):
    if r["decision"] == "REVUE":   # les revues se comparent sans canal (voir le relevé du test)
        return (r["date"], r["client"], "", "", r["echeances"] if r["motif"] == "ESCALADE"
                else "", "REVUE", r["motif"])
    return (r["date"], r["client"], r["canal"], r["etape"], r["echeances"], r["decision"],
            r["motif"])


def simuler(api, db, gest, valid, debut, fin):
    obs, d = [], debut
    while d <= fin:
        if d != date(2026, 12, 15):
            changer_date(api, valid, d.isoformat())
        obs += jour(api, db, gest, valid, d)
        d += timedelta(days=1)
    return obs


def test_S07_relance_annulee_apres_paiement(api, gest):
    a = lire_scenario("S07")["attendu"]
    planifier(api, gest)
    avant = relance_du_client(api, gest, "CLI-0001", date=D0, etape=a["etape"])
    assert avant["statut"] == "PLANIFIEE"
    assert avant["lignes"][0]["echeance_id"] == a["echeance_id"]
    p = api.post("/api/paiements", headers=gest, json=corps_paiement(
        evenement("paiement_entre_preparation_et_envoi")))
    assert p.status_code == 201
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0001", date=D0, etape=a["etape"])
    assert (r["statut"], r["motif"]) == (a["statut_final"], a["motif"])
    boite = api.get("/api/canaux/envois?client_id=CLI-0001&limite=200", headers=gest).json()
    assert [e for e in boite["elements"] if e["date_envoi"] == D0] == []
    assert a["envois_pour_ce_client"] == 0


def test_S08_traitements_concurrents_une_seule_action(api, gest, db_chargee):
    a = lire_scenario("S08")["attendu"]
    planifier(api, gest)
    envoyer(api, gest)
    envoyer(api, gest)       # le second traitement trouve tout déjà traité
    for g in a["relances_verifiees"]:
        r = relance_du_client(api, gest, g["client"], date=D0, statut="ENVOYEE_SIM")
        assert r["canal"] == g["canal"] and r["etape"] == g["etape"]
        assert db_chargee.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                                  (r["id"],)).fetchone()[0] == a["par_relance"]["envois_simules"]
        assert db_chargee.execute(
            "SELECT COUNT(*) FROM journal WHERE type_evenement = 'RELANCE_ENVOYEE_SIM' AND "
            "objet_id = ?", (r["id"],)).fetchone()[0] == a["par_relance"]["evenements_envoi"]
    assert len(relances(api, gest, statut="ENVOYEE_SIM", date=D0)) == \
        a["total_envoyees_ce_jour"]


def test_S09_gros_montants_validation_avant_envoi(api, gest, valid):
    a = lire_scenario("S09")["attendu"]
    planifier(api, gest)
    envoyer(api, gest)
    attente = relances(api, gest, statut="EN_ATTENTE_VALIDATION", date=D0)
    assert len(attente) == a["nb"] == 3     # CLI-0019 est différé par l'espacement (x2)
    obtenu = sorted((x["client_id"], x["canal"], x["etape"]) for x in attente)
    voulu = sorted((g["client"], g["canal"], g["etape"]) for g in a["en_attente_validation"])
    assert obtenu == voulu
    assert sum(1 for g in a["en_attente_validation"] if len(g["lignes"]) > 1) == \
        a["dont_regroupes"] == 0
    for x in attente:
        d = relance_du_client(api, gest, x["client_id"], date=D0, statut="EN_ATTENTE_VALIDATION")
        assert d["total_solde"] > 500_000 and d["revue_id"] and d["date_envoi"] is None
    assert not [e for e in api.get("/api/canaux/envois?limite=200", headers=gest
                                   ).json()["elements"] if e["date_envoi"] == D0
                and e["client_id"] in {x["client_id"] for x in attente}]
    for x in attente:
        assert api.post(f"/api/relances/{x['id']}/valider", headers=valid).status_code == 200
    assert not relances(api, gest, statut="EN_ATTENTE_VALIDATION")


def test_S11_promesses(api, gest, valid, db_chargee):
    a = lire_scenario("S11")["attendu"]
    obs = simuler(api, db_chargee, gest, valid, date(2026, 12, 15), date(2026, 12, 16))
    le15 = sorted(ligne(r) for r in a["le_15"])
    assert [x for x in sorted(obs) if x[0] == D0 and x in le15] == le15
    assert a["cas_limite_0110"]["suspendue_le_15"] is True
    assert db_chargee.execute("SELECT statut FROM promesses_paiement WHERE id = 'PRO-0004'"
                              ).fetchone()[0] == "NON_TENUE"
    assert not [x for x in obs if x[0] == "2026-12-16" and x[5] == "SUSPENDUE"
                and ech_de(db_chargee, "FAC-2026-0110")[0] in x[4]]


def test_S11_promesse_tenue_apres_paiement(api, gest, db_chargee):
    a = lire_scenario("S11")["attendu"]["promesse_tenue_apres_paiement"]
    p = api.post("/api/paiements", headers=gest,
                 json=corps_paiement(evenement("paiement_promesse_tenue")))
    assert p.json()["promesses_tenues"] == [a["promesse"]]
    planifier(api, gest)
    ech = ech_de(db_chargee, "FAC-2026-0107")
    assert db_chargee.execute(
        f"SELECT COUNT(*) FROM relance_lignes WHERE echeance_id IN ({','.join('?' * len(ech))}) "
        "AND relance_id IN (SELECT id FROM relances WHERE date_prevue = ?)",
        ech + [D0]).fetchone()[0] == 0 == len(a["relances"])


def test_S12_relance_sur_la_tranche_manquee_seulement(api, gest):
    """Seule la tranche manquée est relancée. Sa relance du 15/12 n'existe que si l'espacement
    le permet : CLI-0030 (dernier envoi récent, total entre 100 001 et 500 000 FCFA) est différé."""
    a = lire_scenario("S12")["attendu"]
    planifier(api, gest)
    le15 = {r["echeances"].split(":")[0] for r in a["relances"]}
    assert le15 == {"ECH-0119"}
    for t in a["tranches_manquees"]:
        facture = api.get(f"/api/factures/{t['facture_id']}", headers=gest).json()
        r = relance_du_client(api, gest, facture["client"]["id"], date=D0, etape="R1")
        if t["echeance_id"] in le15:
            assert [x["echeance_id"] for x in r["lignes"]] == [t["echeance_id"]]
            assert r["total_solde"] == t["solde"] == r["lignes"][0]["solde"]
        else:
            assert r is None


def test_S12_tranche_differee_relancee_dans_un_message_groupe(api, gest, valid, db_chargee):
    a = lire_scenario("S12")["attendu"]
    obs = simuler(api, db_chargee, gest, valid, date(2026, 12, 15), date(2026, 12, 18))
    manquee = next(t["echeance_id"] for t in a["tranches_manquees"]
                   if t["echeance_id"] not in {r["echeances"].split(":")[0] for r in a["relances"]})
    premieres = [x for x in obs if x[5] == "PREPAREE" and f"{manquee}:R1" in x[4]]
    assert [x[0] for x in premieres] == ["2026-12-18"]
    assert premieres[0][3] == "GROUPE" and premieres[0][6] == "REGROUPE"


def test_S13_message_regroupe(api, gest, valid, db_chargee):
    a = lire_scenario("S13")["attendu"]
    obs = simuler(api, db_chargee, gest, valid, date(2026, 12, 15), date(2026, 12, 16))
    for cle in ("le_15", "le_16"):
        voulu = sorted(ligne(r) for r in a[cle])
        assert [x for x in sorted(obs) if x in voulu] == voulu, cle


def test_S14_escalade_progressive(api, gest, valid, db_chargee):
    a = lire_scenario("S14")["attendu"]
    obs = simuler(api, db_chargee, gest, valid, date(2026, 12, 15), date(2027, 1, 5))
    voulu = sorted(ligne(r) for r in a["decisions"])
    assert [x for x in sorted(obs) if x in voulu] == voulu
    etapes = [x[3] for x in sorted(obs) if x[5] == "PREPAREE" and x[1] == "CLI-0005"
              and "ECH-0079" in x[4]]
    assert etapes == ["R1", "R2", "R3"]          # jamais R3 directement


def test_S15_dimanche_et_jour_ferie(api, gest, valid, db_chargee):
    a = lire_scenario("S15")["attendu"]
    obs = simuler(api, db_chargee, gest, valid, date(2026, 12, 15), date(2026, 12, 27))
    assert [x for x in obs if x[0] in a["jours_sans_decision"]] == []
    for r in a["reportees"]:
        assert ligne(r) in obs
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE date_envoi IN "
                              "('2026-12-20', '2026-12-25')").fetchone()[0] == 0


def test_S16_rappel_p_saute(api, gest):
    a = lire_scenario("S16")["attendu"]
    planifier(api, gest)
    sautees = relances(api, gest, statut="SAUTEE", date=D0)
    assert len([x for x in sautees if x["motif"] == "P_TROP_PROCHE"]) == a["nb_P_TROP_PROCHE"]
    assert len([x for x in sautees if x["motif"] == "P_APRES_ECHEANCE"]) == \
        a["nb_P_APRES_ECHEANCE"]
    assert len(sautees) == a["nb_P_TROP_PROCHE"] + a["nb_P_APRES_ECHEANCE"]
    assert all(x["etape"] == "P" and x["nb_lignes"] == 1 for x in sautees)


def test_S19_lot_interrompu_puis_repris(api, gest, valid, db_chargee):
    a = lire_scenario("S19")["attendu"]
    planifier(api, gest)
    assert a["relances_a_envoyer"] == 13
    api.put("/api/parametres/simulation_interruption_apres", headers=valid,
            json={"valeur": str(a["apres_interruption"])})
    r1 = envoyer(api, gest)
    assert (r1["statut"], r1["envoyees"]) == ("INTERROMPU", a["apres_interruption"])
    envoyer(api, gest)
    assert len(relances(api, gest, statut="ENVOYEE_SIM", date=D0)) == a["apres_reprise"]
    assert a["doublons"] == 0
    assert db_chargee.execute("SELECT relance_id FROM envois_simules GROUP BY relance_id "
                              "HAVING COUNT(*) > 1").fetchall() == []
    for g in a["relances"]:
        assert relance_du_client(api, gest, g["client"], date=D0, statut="ENVOYEE_SIM")


def test_S21_avoir_couvrant(api, gest, valid):
    a = lire_scenario("S21")["attendu"]
    planifier(api, gest)
    envoyer(api, gest)
    changer_date(api, valid, "2026-12-16")
    planifier(api, gest)
    avant = relance_du_client(api, gest, "CLI-0014", date="2026-12-16")
    assert avant["etape"] == a["etape"] and avant["statut"] == "PLANIFIEE"
    ev = evenement("avoir_couvrant")
    api.post("/api/avoirs", headers=gest, json={
        "facture_id": ev["facture_id"], "date": ev["date"], "montant": int(ev["montant"]),
        "motif": ev["motif"]})
    f = api.get(f"/api/factures/{a['facture_id']}", headers=gest).json()
    assert (f["solde"], f["statut"]) == (a["solde_apres_avoir"], a["statut_facture"])
    envoyer(api, gest)
    r = relance_du_client(api, gest, "CLI-0014", date="2026-12-16")
    assert (r["statut"], r["motif"]) == (a["relance_statut_final"], a["motif"])


def test_S22_escalade_apres_r3(api, gest, db_chargee):
    a = lire_scenario("S22")["attendu"]
    planifier(api, gest)
    envoyer(api, gest)
    esc = sorted(r[0] for r in db_chargee.execute(
        "SELECT objet_id FROM file_revue WHERE type = 'ESCALADE'"))
    voulu = sorted(r["echeances"] for r in a["escalades"])
    assert esc == voulu
    assert a["nouvelles_relances_pour_ces_echeances"] == 0
    for e in esc:
        assert db_chargee.execute("SELECT COUNT(*) FROM relance_lignes l JOIN relances r ON "
                                  "r.id = l.relance_id WHERE l.echeance_id = ? AND "
                                  "r.date_prevue >= ?", (e, D0)).fetchone()[0] == 0
