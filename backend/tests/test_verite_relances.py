"""Équivalence : en avançant du 2026-12-15 au 2027-01-05 avec planification, validation
automatique des gros montants (hypothèse de simulation : un VALIDATEUR agit) et envoi, les
décisions du moteur égalent verite_terrain/relances_attendues.csv, jour par jour."""
from collections import defaultdict
from datetime import date, timedelta

import pytest

from tests.verite import lire_csv

pytestmark = pytest.mark.equivalence

TYPES_REVUE = ("CONSENTEMENT_ABSENT", "CANAL_INVALIDE", "ESCALADE")


def tout(api, url, h):
    r = api.get(url + ("&" if "?" in url else "?") + "limite=200", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["elements"]


def jour(api, db, gest, valid, d: date):
    """Exécute une journée et retourne les décisions observées."""
    obs = []
    suspendues = tout(api, "/api/relances/suspensions", gest)
    par_groupe = defaultdict(list)
    for s in suspendues:
        par_groupe[(s["client_id"], s["canal"] or "", s["motif"])].append(s["echeance_id"])
    plan = api.post("/api/relances/planifier", headers=gest)
    assert plan.status_code == 200
    if not plan.json()["jour_ouvre"]:
        # dimanche ou jour férié : rien n'est décidé, ni créé, ni envoyé
        assert plan.json()["creees"] == 0
        assert api.post("/api/relances/envoyer", headers=gest).json()["nb_total"] == 0
        return obs
    for (client, canal, motif), echs in par_groupe.items():
        obs.append((d.isoformat(), client, canal, "", ";".join(sorted(echs)), "SUSPENDUE",
                    motif))
    assert api.post("/api/relances/envoyer", headers=gest).status_code == 200
    gros = {r["id"] for r in tout(api, f"/api/relances?date={d.isoformat()}"
                                  "&statut=EN_ATTENTE_VALIDATION", gest)}
    for rid in sorted(gros):
        assert api.post(f"/api/relances/{rid}/valider", headers=valid).status_code == 200
    for r in tout(api, f"/api/relances?date={d.isoformat()}", gest):
        det = api.get(f"/api/relances/{r['id']}", headers=gest).json()
        lignes = det["lignes"]
        if det["statut"] == "SAUTEE":
            obs.append((d.isoformat(), det["client_id"], det["canal"], "P",
                        f"{lignes[0]['echeance_id']}:P", "SAUTEE", det["motif"] or ""))
            continue
        if det["statut"] != "ENVOYEE_SIM":
            obs.append((d.isoformat(), det["client_id"], det["canal"], det["etape"],
                        "?", f"INATTENDU_{det['statut']}", det["motif"] or ""))
            continue
        echs = sorted(f"{x['echeance_id']}:{x['etape_echeance']}" for x in lignes)
        obs.append((d.isoformat(), det["client_id"], det["canal"], det["etape"],
                    ";".join(echs), "EN_ATTENTE_VALIDATION" if r["id"] in gros else "PREPAREE",
                    det["motif"] or ""))
        for x in lignes:
            if x["decision"] == "ABSORBEE":
                obs.append((d.isoformat(), det["client_id"], det["canal"],
                            x["etape_echeance"], f"{x['echeance_id']}:{x['etape_echeance']}",
                            "ABSORBEE", "REGROUPE"))
    for r in db.execute("SELECT f.type, f.objet_id, f.client_id FROM file_revue f WHERE "
                        "f.date_reference_creation = ? AND f.type IN (?,?,?)",
                        (d.isoformat(), *TYPES_REVUE)):
        obs.append((d.isoformat(), r["client_id"], "", "",
                    r["objet_id"] if r["type"] == "ESCALADE" else "", "REVUE", r["type"]))
    return obs


def normaliser_attendu(rows):
    sortie = []
    for r in rows:
        if r["decision"] == "REVUE":
            sortie.append((r["date_simulee"], r["client_id"], "", "",
                           r["echeances"] if r["motif"] == "ESCALADE" else "", "REVUE",
                           r["motif"]))
        else:
            sortie.append((r["date_simulee"], r["client_id"], r["canal"], r["etape"],
                           r["echeances"], r["decision"], r["motif"]))
    return sortie


def test_relances_jour_par_jour_du_15_decembre_au_5_janvier(api, gest, valid, db_chargee):
    attendu = normaliser_attendu(lire_csv("verite_terrain/relances_attendues.csv"))
    obtenu = []
    d = date(2026, 12, 15)
    while d <= date(2027, 1, 5):
        if d != date(2026, 12, 15):
            r = api.post("/api/admin/date-reference", headers=valid, json={"date": d.isoformat()})
            assert r.status_code == 200
        obtenu += jour(api, db_chargee, gest, valid, d)
        d += timedelta(days=1)
    manquantes = sorted(set(attendu) - set(obtenu))
    en_trop = sorted(set(obtenu) - set(attendu))
    ecarts = [f"MANQUE {x}" for x in manquantes] + [f"EN TROP {x}" for x in en_trop]
    assert len(attendu) == len(set(attendu)), "lignes attendues en double"
    assert not ecarts, (f"{len(ecarts)} écart(s) sur {len(attendu)} décisions\n"
                        + "\n".join(ecarts[:40]))
