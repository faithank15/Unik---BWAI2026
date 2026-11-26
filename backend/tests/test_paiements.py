"""Paiements simulés, avoirs, affectation manuelle : règles, idempotence, concurrence."""
import threading

import pytest

from app.db import connecter
from app.journal import SYSTEME
from app.services import calculs
from app.services import paiements as svc
from tests.aides import compter


def payer(api, h, **kw):
    corps = {"client_id": "CLI-0001", "date_paiement": "2026-12-15", "montant": 1000,
             "mode": "MOBILE_MONEY", "reference_externe": "MM-SIM-2026-T00001",
             "references_indiquees": []}
    corps.update(kw)
    return api.post("/api/paiements", json=corps, headers=h)


def facture_de(conn, numero_client, n):
    return conn.execute("SELECT id, numero, montant_ttc FROM factures WHERE id = ?",
                        (f"FAC-2026-{n:04d}",)).fetchone()


def test_Y01_paiement_valide_affecte_et_journalise(api, gest, db_chargee):
    f = facture_de(db_chargee, "CLI-0001", 61)
    r = payer(api, gest, montant=f["montant_ttc"], references_indiquees=[f["numero"]])
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["id"] == "PAY-0085" and p["statut"] == "RECU" and p["deja_enregistre"] is False
    assert p["reste_non_affecte"] == 0
    assert [a["mode"] for a in p["affectations"]] == ["INDIQUEE"]
    assert calculs.factures_calculees(db_chargee)[f["id"]]["statut"] == "SOLDEE"
    ev = db_chargee.execute("SELECT acteur_type, acteur_id, correlation_id FROM journal "
                            "WHERE type_evenement = 'PAIEMENT_ENREGISTRE' AND objet_id = "
                            "'PAY-0085'").fetchall()
    assert len(ev) == 1 and ev[0]["acteur_type"] == "UTILISATEUR" and ev[0]["correlation_id"]


def test_Y02_rejeu_meme_corps_200_sans_ecriture(api, gest, db_chargee):
    f = facture_de(db_chargee, "CLI-0001", 61)
    corps = dict(montant=f["montant_ttc"], references_indiquees=[f["numero"]])
    a = payer(api, gest, **corps)
    avant = (compter(db_chargee, "paiements"), compter(db_chargee, "affectations"))
    b = payer(api, gest, **corps)
    assert b.status_code == 200 and b.json()["deja_enregistre"] is True
    assert b.json()["id"] == a.json()["id"]
    assert (compter(db_chargee, "paiements"), compter(db_chargee, "affectations")) == avant
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'PAIEMENT_REJOUE'").fetchone()[0] == 1


def test_rejeu_avec_valeurs_differentes_409(api, gest):
    payer(api, gest, montant=1000)
    r = payer(api, gest, montant=2000)
    assert r.status_code == 409 and r.json()["erreur"]["code"] == "CONFLIT"


def test_meme_reference_autre_mode_est_un_autre_paiement(api, gest):
    assert payer(api, gest).status_code == 201
    assert payer(api, gest, mode="VIREMENT").status_code == 201


def test_Y04_facture_annulee_refusee(api, gest, db_chargee):
    f = db_chargee.execute("SELECT f.numero, f.client_id FROM factures f WHERE f.id = "
                           "'FAC-2026-0118'").fetchone()
    r = payer(api, gest, client_id=f["client_id"], references_indiquees=[f["numero"]])
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == "FACTURE_ANNULEE"
    assert compter(db_chargee, "paiements") == 84


def test_Y05_date_posterieure_a_la_date_de_reference(api, gest):
    r = payer(api, gest, date_paiement="2026-12-16")
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == "DATE_FUTURE"


@pytest.mark.parametrize("champ,valeur", [("montant", 0), ("montant", -5),
                                          ("mode", "BITCOIN"), ("date_paiement", "2026-02-30"),
                                          ("date_paiement", "15/12/2026")])
def test_A07_entrees_invalides(api, gest, champ, valeur):
    r = payer(api, gest, **{champ: valeur})
    assert r.status_code in (400, 422), r.text
    assert r.json()["erreur"]["code"] in ("VALIDATION", "REGLE_METIER")


def test_client_inconnu(api, gest):
    r = payer(api, gest, client_id="CLI-9999")
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == "CLIENT_INCONNU"


def test_A04_reference_d_un_autre_client_ignoree(api, gest, db_chargee):
    autre = db_chargee.execute("SELECT numero FROM factures WHERE client_id = 'CLI-0002' "
                               "AND id = 'FAC-2026-0062'").fetchone()
    r = payer(api, gest, client_id="CLI-0001", montant=1000,
              references_indiquees=[autre["numero"]])
    assert r.status_code == 201
    assert all(a["mode"] == "AUTO_ANCIENNETE" for a in r.json()["affectations"])
    # aucune affectation sur une échéance d'un autre client
    for a in r.json()["affectations"]:
        c = db_chargee.execute("SELECT f.client_id FROM echeances e JOIN factures f ON "
                               "f.id = e.facture_id WHERE e.id = ?", (a["echeance_id"],)
                               ).fetchone()[0]
        assert c == "CLI-0001"
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'REFERENCE_INTROUVABLE'").fetchone()[0] == 1


def test_A02_sans_indication_la_plus_ancienne_d_abord(api, gest, db_chargee):
    r = payer(api, gest, client_id="CLI-0007", montant=1000)
    ech = r.json()["affectations"][0]["echeance_id"]
    plus_ancienne = db_chargee.execute(
        "SELECT c.echeance_id FROM v_echeances_calc c JOIN factures f ON f.id = c.facture_id "
        "WHERE f.client_id = 'CLI-0007' AND c.etat='ACTIVE' AND c.solde > 0 "
        "ORDER BY c.date_echeance, c.echeance_id LIMIT 1").fetchone()[0]
    assert ech == plus_ancienne and r.json()["affectations"][0]["mode"] == "AUTO_ANCIENNETE"


def test_A05_surpaiement_reste_non_affecte_jamais_de_solde_negatif(api, gest, db_chargee):
    total = db_chargee.execute(
        "SELECT SUM(c.solde) FROM v_echeances_calc c JOIN factures f ON f.id = c.facture_id "
        "WHERE f.client_id = 'CLI-0001' AND c.etat='ACTIVE'").fetchone()[0]
    r = payer(api, gest, client_id="CLI-0001", montant=total + 7000)
    p = r.json()
    assert p["reste_non_affecte"] == 7000
    assert db_chargee.execute("SELECT COUNT(*) FROM v_echeances_calc WHERE solde < 0"
                              ).fetchone()[0] == 0
    revue = db_chargee.execute("SELECT type, statut FROM file_revue WHERE objet_id = ?",
                               (p["id"],)).fetchone()
    assert (revue["type"], revue["statut"]) == ("PAIEMENT_AMBIGU", "OUVERTE")


def test_paiement_sans_client_en_revue(api, gest, db_chargee):
    r = payer(api, gest, client_id=None, reference_externe="MM-SIM-2026-ORPH01")
    assert r.status_code == 201 and r.json()["affectations"] == []
    assert r.json()["reste_non_affecte"] == 1000


def test_affectation_manuelle_resout_la_revue_et_fixe_le_client(api, gest, db_chargee):
    pid = payer(api, gest, client_id=None, montant=5000,
                reference_externe="MM-SIM-2026-ORPH02").json()["id"]
    ech = db_chargee.execute(
        "SELECT c.echeance_id, c.solde FROM v_echeances_calc c JOIN factures f ON f.id = "
        "c.facture_id WHERE f.client_id = 'CLI-0001' AND c.etat='ACTIVE' AND c.solde >= 5000 "
        "LIMIT 1").fetchone()
    r = api.post(f"/api/paiements/{pid}/affecter", headers=gest, json={
        "affectations": [{"echeance_id": ech["echeance_id"], "montant": 5000}]})
    assert r.status_code == 200, r.text
    assert r.json()["client_id"] == "CLI-0001" and r.json()["reste_non_affecte"] == 0
    assert r.json()["affectations"][0]["mode"] == "INDIQUEE"
    assert db_chargee.execute("SELECT statut FROM file_revue WHERE objet_id = ?", (pid,)
                              ).fetchone()[0] == "RESOLUE"


def test_affectation_manuelle_refus_clients_differents_et_sur_affectation(api, gest, db_chargee):
    pid = payer(api, gest, client_id=None, montant=5000,
                reference_externe="MM-SIM-2026-ORPH03").json()["id"]
    e1 = db_chargee.execute("SELECT c.echeance_id FROM v_echeances_calc c JOIN factures f ON "
                            "f.id = c.facture_id WHERE f.client_id='CLI-0001' AND c.solde>0 "
                            "AND c.etat='ACTIVE' LIMIT 1").fetchone()[0]
    e2 = db_chargee.execute("SELECT c.echeance_id FROM v_echeances_calc c JOIN factures f ON "
                            "f.id = c.facture_id WHERE f.client_id='CLI-0002' AND c.solde>0 "
                            "AND c.etat='ACTIVE' LIMIT 1").fetchone()[0]
    r = api.post(f"/api/paiements/{pid}/affecter", headers=gest, json={"affectations": [
        {"echeance_id": e1, "montant": 100}, {"echeance_id": e2, "montant": 100}]})
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == "CLIENTS_DIFFERENTS"
    r = api.post(f"/api/paiements/{pid}/affecter", headers=gest, json={"affectations": [
        {"echeance_id": e1, "montant": 5001}]})
    assert r.status_code == 422 and r.json()["erreur"]["details"]["regle"] == "SUR_AFFECTATION"
    assert compter(db_chargee, "affectations") == 92  # rien n'a été écrit


def test_promesse_passe_a_tenue_quand_la_facture_est_soldee(api, gest, db_chargee):
    f = db_chargee.execute("SELECT id, numero, client_id, montant_ttc FROM factures "
                           "WHERE id = 'FAC-2026-0107'").fetchone()
    r = payer(api, gest, client_id=f["client_id"], montant=f["montant_ttc"],
              references_indiquees=[f["numero"]], reference_externe="MM-SIM-2026-PROM01")
    assert r.json()["promesses_tenues"] == ["PRO-0001"]
    assert db_chargee.execute("SELECT statut FROM promesses_paiement WHERE id='PRO-0001'"
                              ).fetchone()[0] == "TENUE"
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'PROMESSE_TENUE'").fetchone()[0] == 1


def test_RP03_atomicite_une_erreur_annule_paiement_et_journal(reglages_charge, monkeypatch):
    c = connecter(reglages_charge.database_path)

    def boum(*a, **k):
        raise RuntimeError("panne entre le paiement et ses affectations")
    monkeypatch.setattr(svc, "_ecrire_affectations", boum)
    f = c.execute("SELECT numero, montant_ttc FROM factures WHERE id = 'FAC-2026-0061'"
                  ).fetchone()
    with pytest.raises(RuntimeError):
        svc.enregistrer_paiement(
            c, client_id="CLI-0001", date_paiement="2026-12-15", montant=f["montant_ttc"],
            mode="MOBILE_MONEY", reference_externe="MM-SIM-2026-ATOM01",
            references_indiquees=[f["numero"]], acteur=SYSTEME)
    assert compter(c, "paiements") == 84
    assert c.execute("SELECT COUNT(*) FROM journal WHERE objet_type = 'PAIEMENT' AND "
                     "details LIKE '%ATOM01%'").fetchone()[0] == 0
    assert c.execute("SELECT valeur FROM sequences WHERE nom = 'PAY'").fetchone()[0] == 84


def test_CO02_meme_paiement_enregistre_par_plusieurs_threads(reglages_charge):
    resultats, erreurs = [], []
    f = connecter(reglages_charge.database_path).execute(
        "SELECT numero, montant_ttc FROM factures WHERE id = 'FAC-2026-0062'").fetchone()

    def tache():
        try:
            c = connecter(reglages_charge.database_path)
            resultats.append(svc.enregistrer_paiement(
                c, client_id="CLI-0002", date_paiement="2026-12-15",
                montant=f["montant_ttc"], mode="VIREMENT",
                reference_externe="VIR-SIM-2026-CONC01", references_indiquees=[f["numero"]],
                acteur=SYSTEME))
            c.close()
        except Exception as e:  # noqa: BLE001
            erreurs.append(e)

    threads = [threading.Thread(target=tache) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not erreurs, erreurs
    assert sum(1 for r in resultats if not r["deja_enregistre"]) == 1
    assert len({r["id"] for r in resultats}) == 1
    c = connecter(reglages_charge.database_path)
    assert compter(c, "paiements") == 85 and compter(c, "affectations") == 93
    assert c.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                     "'PAIEMENT_ENREGISTRE' AND objet_id = ?", (resultats[0]["id"],)
                     ).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                     "'PAIEMENT_REJOUE'").fetchone()[0] == 7


# ---- avoirs ----------------------------------------------------------------------------
def avoir(api, h, facture, montant, **kw):
    corps = {"facture_id": facture, "date": "2026-12-15", "montant": montant,
             "motif": "remise commerciale"}
    corps.update(kw)
    return api.post("/api/avoirs", json=corps, headers=h)


def test_V01_avoir_partiel_reduit_le_solde(api, gest, db_chargee):
    avant = calculs.factures_calculees(db_chargee)["FAC-2026-0062"]["solde"]
    r = avoir(api, gest, "FAC-2026-0062", 5000)
    assert r.status_code == 201 and r.json()["id"] == "AVO-0006"
    assert calculs.factures_calculees(db_chargee)["FAC-2026-0062"]["solde"] == avant - 5000


def test_V02_avoir_total_solde_la_facture(api, gest, db_chargee):
    solde = calculs.factures_calculees(db_chargee)["FAC-2026-0062"]["solde"]
    r = avoir(api, gest, "FAC-2026-0062", solde)
    assert r.status_code == 201
    assert calculs.factures_calculees(db_chargee)["FAC-2026-0062"]["statut"] == "SOLDEE"


def test_V03_avoir_superieur_au_solde_refuse(api, gest, db_chargee):
    solde = calculs.factures_calculees(db_chargee)["FAC-2026-0062"]["solde"]
    r = avoir(api, gest, "FAC-2026-0062", solde + 1)
    assert r.status_code == 422
    assert r.json()["erreur"]["details"]["regle"] == "AVOIR_SUPERIEUR_AU_SOLDE"


def test_V04_avoir_rejoue_un_seul_effet(api, gest, db_chargee):
    avoir(api, gest, "FAC-2026-0062", 5000)
    avant = compter(db_chargee, "affectations")
    r = avoir(api, gest, "FAC-2026-0062", 5000)
    assert r.status_code == 200 and r.json()["deja_enregistre"] is True
    assert compter(db_chargee, "avoirs") == 6 and compter(db_chargee, "affectations") == avant


def test_avoir_facture_inconnue_404(api, gest):
    assert avoir(api, gest, "FAC-2026-9999", 100).status_code == 404


def test_avoir_sur_plusieurs_echeances_par_anciennete(api, gest, db_chargee):
    # FAC-2026-0102 : tranche 1 payée, tranches 2 et 3 dues ; un avoir déborde sur la suivante
    t = [r["solde"] for r in db_chargee.execute(
        "SELECT solde FROM v_echeances_calc WHERE facture_id = 'FAC-2026-0102' AND "
        "etat='ACTIVE' AND solde > 0 ORDER BY date_echeance")]
    r = avoir(api, gest, "FAC-2026-0102", t[0] + 1000)
    aff = r.json()["affectations"]
    assert [a["montant_affecte"] for a in aff] == [t[0], 1000]
    assert all(a["mode"] == "AUTO_ANCIENNETE" for a in aff)


# ---- imports de fichiers de paiements -------------------------------------------------
def test_import_fichier_de_paiements_rapport_par_ligne(api, gest, db_chargee):
    csv = ("id,client_id,date_paiement,montant,mode,reference_externe,source,statut,"
           "references_indiquees\n"
           ",CLI-0001,2026-12-15,1000,MOBILE_MONEY,MM-SIM-2026-FIC001,SIMULE,RECU,\n"
           ",CLI-0001,2026-12-15,1000,MOBILE_MONEY,MM-SIM-2026-FIC001,SIMULE,RECU,\n"
           ",CLI-0001,2026-12-15,9999,MOBILE_MONEY,MM-SIM-2026-FIC001,SIMULE,RECU,\n"
           ",CLI-0001,2026-12-15,-3,MOBILE_MONEY,MM-SIM-2026-FIC002,SIMULE,RECU,\n")
    r = api.post("/api/paiements/import", headers=gest,
                 files={"fichier": ("paiements.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    rap = r.json()
    assert (rap["enregistres"], rap["rejoues"], rap["conflits"]) == (1, 1, 1)
    assert len(rap["rejets"]) == 2 and rap["rejets"][1]["ligne"] == 5
    assert compter(db_chargee, "paiements") == 85
