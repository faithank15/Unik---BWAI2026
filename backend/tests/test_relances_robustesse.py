"""Idempotence, concurrence et reprise du moteur de relances (S08, S19, CO01, CO03, CO04)."""
import threading

import pytest

from app.db import connecter
from app.journal import SYSTEME, utilisateur
from app.services import paiements as svc_paiements
from app.services import relances as svc
from tests.aides import compter
from tests.aides_relances import D0, envoyer, planifier, relance_du_client, relances


def lancer(n, cible):
    erreurs = []

    def tache():
        try:
            cible()
        except Exception as e:  # noqa: BLE001
            erreurs.append(e)
    threads = [threading.Thread(target=tache) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not erreurs, erreurs


def test_S08_CO01_deux_a_huit_traitements_paralleles_une_seule_action(
        api, gest, reglages_charge):
    planifier(api, gest)
    a_envoyer = len(relances(api, gest, statut="PLANIFIEE", date=D0))
    assert a_envoyer == 16          # 13 à envoyer, 3 gros montants à valider (CLI-0019 différé)
    deja = compter(connecter(reglages_charge.database_path), "envois_simules")

    def cible():
        c = connecter(reglages_charge.database_path)
        svc.envoyer_lot(c, SYSTEME)
        c.close()
    lancer(8, cible)
    c = connecter(reglages_charge.database_path)
    assert compter(c, "envois_simules") == deja + 13
    dupl = c.execute("SELECT relance_id, COUNT(*) FROM envois_simules GROUP BY relance_id "
                     "HAVING COUNT(*) > 1").fetchall()
    assert dupl == []
    evts = c.execute("SELECT objet_id, COUNT(*) FROM journal WHERE type_evenement = "
                     "'RELANCE_ENVOYEE_SIM' GROUP BY objet_id HAVING COUNT(*) > 1").fetchall()
    assert evts == []
    assert c.execute("SELECT COUNT(*) FROM relances WHERE statut = 'PLANIFIEE'"
                     ).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM relances WHERE statut = 'EN_ATTENTE_VALIDATION'"
                     ).fetchone()[0] == 3


def test_CO01_meme_relance_envoyee_par_plusieurs_threads_sans_erreur(api, gest, reglages_charge):
    planifier(api, gest)
    rid = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")["id"]
    resultats = []

    def cible():
        c = connecter(reglages_charge.database_path)
        resultats.append(svc.envoyer_relance(c, rid, SYSTEME)["resultat"])
        c.close()
    lancer(6, cible)
    assert sorted(resultats).count("ENVOYEE_SIM") == 1
    assert sorted(resultats).count("DEJA_TRAITEE") == 5


def test_CO03_paiement_et_envoi_simultanes_jamais_d_envoi_apres_le_paiement(
        api, gest, reglages_charge):
    planifier(api, gest)
    rid = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")["id"]
    f = connecter(reglages_charge.database_path).execute(
        "SELECT numero, montant_ttc FROM factures WHERE id = 'FAC-2026-0061'").fetchone()
    barriere = threading.Barrier(2)

    def envoi():
        c = connecter(reglages_charge.database_path)
        barriere.wait()
        svc.envoyer_relance(c, rid, SYSTEME)

    def paiement():
        c = connecter(reglages_charge.database_path)
        barriere.wait()
        svc_paiements.enregistrer_paiement(
            c, client_id="CLI-0001", date_paiement=D0, montant=f["montant_ttc"],
            mode="MOBILE_MONEY", reference_externe="MM-SIM-2026-CO03",
            references_indiquees=[f["numero"]], acteur=SYSTEME)
    t1, t2 = threading.Thread(target=envoi), threading.Thread(target=paiement)
    t1.start(); t2.start(); t1.join(); t2.join()  # noqa: E702
    c = connecter(reglages_charge.database_path)
    statut = c.execute("SELECT statut FROM relances WHERE id = ?", (rid,)).fetchone()[0]
    assert statut in ("ENVOYEE_SIM", "ANNULEE")
    envoi_id = c.execute("SELECT MIN(id) FROM journal WHERE type_evenement = "
                         "'RELANCE_ENVOYEE_SIM' AND objet_id = ?", (rid,)).fetchone()[0]
    pay_id = c.execute("SELECT MIN(id) FROM journal WHERE type_evenement = "
                       "'PAIEMENT_ENREGISTRE' AND details LIKE '%CO03%'").fetchone()[0]
    if statut == "ENVOYEE_SIM":
        assert envoi_id < pay_id        # envoyée avant le paiement, jamais après
    else:
        assert envoi_id is None and c.execute(
            "SELECT motif FROM relances WHERE id = ?", (rid,)).fetchone()[0] == "SOLDE_NUL"


def test_CO04_deux_validations_de_la_meme_relance_une_seule_transition(
        api, gest, reglages_charge):
    planifier(api, gest)
    envoyer(api, gest)
    rid = relance_du_client(api, gest, "CLI-0016", date=D0, etape="R1")["id"]
    resultats = []

    def cible():
        c = connecter(reglages_charge.database_path)
        resultats.append(svc.valider_relance(c, rid, utilisateur("USR-0002"))["resultat"])
        c.close()
    lancer(5, cible)
    assert resultats.count("ENVOYEE_SIM") == 1 and resultats.count("SANS_EFFET") == 4
    c = connecter(reglages_charge.database_path)
    assert c.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = 'RELANCE_VALIDEE' "
                     "AND objet_id = ?", (rid,)).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                     (rid,)).fetchone()[0] == 1


def test_planifications_paralleles_ne_creent_aucun_doublon(api, gest, reglages_charge):
    def cible():
        c = connecter(reglages_charge.database_path)
        svc.planifier(c, SYSTEME)
        c.close()
    lancer(4, cible)
    c = connecter(reglages_charge.database_path)
    assert c.execute("SELECT COUNT(*) FROM relances WHERE date_prevue = ? AND statut = "
                     "'PLANIFIEE'", (D0,)).fetchone()[0] == 13 + 3
    assert c.execute("SELECT cle_idempotence, COUNT(*) FROM relances GROUP BY "
                     "cle_idempotence HAVING COUNT(*) > 1").fetchall() == []
    assert c.execute("SELECT COUNT(*) FROM file_revue WHERE type = 'ESCALADE'"
                     ).fetchone()[0] == 2


def test_CO06_base_occupee_reessai_borne_jamais_d_echec_silencieux(reglages_charge):
    """Une transaction d'écriture longue bloque les autres ; elles attendent puis réussissent."""
    c1 = connecter(reglages_charge.database_path)
    c1.execute("BEGIN IMMEDIATE")
    fin = {}

    def cible():
        c = connecter(reglages_charge.database_path)
        fin["r"] = svc.planifier(c, SYSTEME)["creees"]
        c.close()
    t = threading.Thread(target=cible)
    t.start()
    t.join(timeout=0.5)
    assert t.is_alive()          # elle attend le verrou
    c1.execute("ROLLBACK")
    t.join(timeout=10)
    assert fin["r"] == 16


# ---- reprise après interruption ---------------------------------------------------------
def test_S19_RP01_lot_interrompu_apres_5_puis_repris_sans_doublon(api, gest, valid,
                                                                  db_chargee):
    planifier(api, gest)
    assert api.put("/api/parametres/simulation_interruption_apres", headers=valid,
                   json={"valeur": "5"}).status_code == 200
    r1 = envoyer(api, gest)
    assert r1["statut"] == "INTERROMPU" and r1["nb_traites"] == 5 and r1["envoyees"] == 5
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE statut = 'ENVOYEE_SIM' "
                              "AND date_envoi = ?", (D0,)).fetchone()[0] == 5
    lot = db_chargee.execute("SELECT statut, nb_total, nb_traites FROM traitements_lot "
                             "WHERE id = ?", (r1["traitement_id"],)).fetchone()
    assert tuple(lot) == ("INTERROMPU", 16, 5)
    # la simulation est consommée : la reprise va jusqu'au bout
    r2 = envoyer(api, gest)
    assert r2["statut"] == "TERMINE" and r2["nb_total"] == 11 and r2["envoyees"] == 8
    assert r2["en_attente_validation"] == 3
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE statut = 'ENVOYEE_SIM' "
                              "AND date_envoi = ?", (D0,)).fetchone()[0] == 13
    assert db_chargee.execute("SELECT relance_id FROM envois_simules GROUP BY relance_id "
                              "HAVING COUNT(*) > 1").fetchall() == []


def test_reprise_apres_replanification_aucun_doublon(api, gest, valid, db_chargee):
    planifier(api, gest)
    api.put("/api/parametres/simulation_interruption_apres", headers=valid,
            json={"valeur": "3"})
    envoyer(api, gest)
    planifier(api, gest)           # replanifier au milieu d'un lot ne recrée rien
    envoyer(api, gest)
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE date_prevue = ? AND "
                              "statut = 'ENVOYEE_SIM'", (D0,)).fetchone()[0] == 13
    assert db_chargee.execute("SELECT COUNT(*) FROM relances WHERE date_prevue = ?",
                              (D0,)).fetchone()[0] == 13 + 3 + 16


def test_RP03_atomicite_une_erreur_pendant_l_envoi_annule_tout(api, gest, reglages_charge,
                                                               monkeypatch):
    planifier(api, gest)
    rid = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")["id"]
    c = connecter(reglages_charge.database_path)
    original = svc.journaliser

    def piege(conn, type_evenement, *a, **k):
        if type_evenement == "RELANCE_ENVOYEE_SIM":
            raise RuntimeError("panne entre l'envoi simulé et le statut")
        return original(conn, type_evenement, *a, **k)
    monkeypatch.setattr(svc, "journaliser", piege)
    with pytest.raises(RuntimeError):
        svc.envoyer_relance(c, rid, SYSTEME)
    assert c.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                     (rid,)).fetchone()[0] == 0
    assert c.execute("SELECT statut, date_envoi FROM relances WHERE id = ?", (rid,)
                     ).fetchone()[:] == ("PLANIFIEE", None)
    monkeypatch.setattr(svc, "journaliser", original)
    assert svc.envoyer_relance(c, rid, SYSTEME)["resultat"] == "ENVOYEE_SIM"


def test_ID03_envoi_de_la_meme_relance_un_seul_envoi_un_seul_evenement(api, gest, db_chargee):
    planifier(api, gest)
    rid = relance_du_client(api, gest, "CLI-0001", date=D0, etape="R1")["id"]
    for _ in range(3):
        envoyer(api, gest)
    assert db_chargee.execute("SELECT COUNT(*) FROM envois_simules WHERE relance_id = ?",
                              (rid,)).fetchone()[0] == 1
    assert db_chargee.execute("SELECT COUNT(*) FROM journal WHERE type_evenement = "
                              "'RELANCE_ENVOYEE_SIM' AND objet_id = ?", (rid,)
                              ).fetchone()[0] == 1
