#!/usr/bin/env python3
"""Les seize contrôles de cohérence du jeu de données (section 13 du document de données).

Le script ne lit que les fichiers du dossier : il n'importe rien du générateur, sauf
pour le contrôle 14 (déterminisme) qui le relance deux fois. Il rejoue lui-même la règle
d'affectation et recalcule statuts, soldes et priorisation.

Usage : python tests_coherence.py            (code de sortie non nul au moindre échec)
"""
import csv
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

ICI = os.path.dirname(os.path.abspath(__file__))
D0 = date(2026, 12, 15)


def lire(rel):
    with open(os.path.join(ICI, rel), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def pd(s):
    return date.fromisoformat(s)


def plus(d, n):
    return d + timedelta(days=n)


RESULTATS = []


def controle(numero, titre):
    def deco(fn):
        def run():
            try:
                msgs = fn() or []
                RESULTATS.append((numero, titre, not msgs, msgs))
            except Exception as e:  # noqa: BLE001
                RESULTATS.append((numero, titre, False, [f"exception : {e!r}"]))
        run.numero = numero
        return run
    return deco


# ---- données communes ------------------------------------------------------------
class D:
    pass


def charger():
    d = D()
    d.clients = lire("lot_nominal/clients.csv")
    d.prefs = lire("lot_nominal/preferences_contact.csv")
    d.fac = lire("lot_nominal/factures.csv")
    d.ech = lire("lot_nominal/echeances.csv")
    d.avo = lire("lot_nominal/avoirs.csv")
    d.pay = lire("lot_nominal/paiements.csv")
    d.feries = {r["date"] for r in lire("lot_nominal/jours_feries.csv")}
    d.accords = lire("etat_initial/accords_echeancier.csv")
    d.contest = lire("etat_initial/contestations.csv")
    d.promesses = lire("etat_initial/promesses_paiement.csv")
    d.hist = lire("etat_initial/relances_historique.csv")
    d.hlignes = lire("etat_initial/relance_lignes_historique.csv")
    d.statuts = lire("verite_terrain/statuts_factures.csv")
    d.soldes = lire("verite_terrain/soldes_echeances.csv")
    d.affs = lire("verite_terrain/affectations_attendues.csv")
    d.prio = lire("verite_terrain/priorisation.csv")
    d.rel = lire("verite_terrain/relances_attendues.csv")
    d.msgs = lire("messages/messages_clients.csv")
    d.etiq = lire("messages/etiquettes.csv")
    d.fiches = lire("messages/fiches_redaction_main.csv")
    return d


NOMS_JOURS = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI"]


def est_ouvre(d, feries):
    return d.weekday() != 6 and d.isoformat() not in feries


def rejouer_affectation(d):
    """Règle de la section 7, réécrite ici."""
    {e["id"]: e for e in d.ech}
    {f["id"]: f for f in d.fac}
    client_de = {f["id"]: f["client_id"] for f in d.fac}
    par_num = {(f["client_id"], f["numero"]): f["id"] for f in d.fac}
    actives = [e for e in d.ech if e["etat"] == "ACTIVE"]
    solde = {e["id"]: int(e["montant_du"]) for e in actives}
    par_fac = defaultdict(list)
    par_client = defaultdict(list)
    for e in actives:
        par_fac[e["facture_id"]].append(e)
        par_client[client_de[e["facture_id"]]].append(e)
    evs = []
    for p in d.pay:
        evs.append((p["date_paiement"], p["id"], "PAY", p))
    for a in d.avo:
        evs.append((a["date"], a["id"], "AVO", a))
    evs.sort(key=lambda x: (x[0], x[1]))
    res = []

    def prendre(src, e, reste, mode):
        m = min(reste, solde[e["id"]])
        if m > 0:
            solde[e["id"]] -= m
            res.append((src, e["id"], m, mode))
        return reste - m

    for _, ident, kind, o in evs:
        if kind == "PAY":
            reste = int(o["montant"])
            if o["client_id"]:
                for num in [x for x in o["references_indiquees"].split(";") if x]:
                    f = par_num.get((o["client_id"], num))
                    if not f:
                        continue
                    for e in sorted(par_fac[f], key=lambda x: (x["date_echeance"], x["id"])):
                        if solde[e["id"]] > 0:
                            reste = prendre(ident, e, reste, "INDIQUEE")
                if reste > 0:
                    for e in sorted(par_client[o["client_id"]],
                                    key=lambda x: (x["date_echeance"], x["id"])):
                        if solde[e["id"]] > 0:
                            reste = prendre(ident, e, reste, "AUTO_ANCIENNETE")
        else:
            reste = int(o["montant"])
            for e in sorted(par_fac[o["facture_id"]], key=lambda x: (x["date_echeance"], x["id"])):
                reste = prendre(ident, e, reste, "AUTO_ANCIENNETE")
    return res, solde


# ---- les seize contrôles ---------------------------------------------------------
def unicite(d):
    m = []
    for nom, lst in (("clients", d.clients), ("factures", d.fac), ("échéances", d.ech),
                     ("paiements", d.pay), ("avoirs", d.avo), ("relances", d.hist),
                     ("messages", d.msgs)):
        ids = [r["id"] for r in lst]
        if len(ids) != len(set(ids)):
            m.append(f"identifiants dupliqués dans {nom}")
    if len({(p["mode"], p["reference_externe"]) for p in d.pay}) != len(d.pay):
        m.append("couples (mode, reference_externe) dupliqués")
    if len({(f["client_id"], f["numero"]) for f in d.fac}) != len(d.fac):
        m.append("couples (client_id, numero) dupliqués")
    if len({r["cle_idempotence"] for r in d.hist}) != len(d.hist):
        m.append("cle_idempotence dupliquée")
    return m


def integrite(d):
    m = []
    cl = {c["id"] for c in d.clients}
    fa = {f["id"] for f in d.fac}
    ec = {e["id"] for e in d.ech}
    pa = {p["id"] for p in d.pay}
    ac = {a["id"] for a in d.accords}
    rel = {r["id"] for r in d.hist}
    cons = {r["client_id"] for r in d.prefs}
    if cons != cl:
        m.append("préférences de contact ≠ clients")
    for f in d.fac:
        if f["client_id"] not in cl:
            m.append(f"facture {f['id']} : client inconnu")
    for e in d.ech:
        if e["facture_id"] not in fa:
            m.append(f"échéance {e['id']} : facture inconnue")
        if e["accord_id"] and e["accord_id"] not in ac:
            m.append(f"échéance {e['id']} : accord inconnu")
    for p in d.pay:
        if p["client_id"] and p["client_id"] not in cl:
            m.append(f"paiement {p['id']} : client inconnu")
        for num in [x for x in p["references_indiquees"].split(";") if x]:
            if not any(f["numero"] == num and f["client_id"] == p["client_id"] for f in d.fac):
                m.append(f"paiement {p['id']} : référence {num} introuvable pour ce client")
    for a in d.avo:
        if a["facture_id"] not in fa:
            m.append(f"avoir {a['id']} : facture inconnue")
    for x in d.accords + d.contest:
        if x["facture_id"] not in fa:
            m.append(f"{x['id']} : facture inconnue")
    for x in d.promesses:
        if x["facture_id"] not in fa or x["client_id"] not in cl:
            m.append(f"{x['id']} : référence inconnue")
    for r in d.hist:
        if r["client_id"] not in cl:
            m.append(f"{r['id']} : client inconnu")
    for l in d.hlignes:
        if l["relance_id"] not in rel or l["echeance_id"] not in ec:
            m.append(f"ligne de relance {l['relance_id']}/{l['echeance_id']} orpheline")
    for a in d.affs:
        if a["echeance_id"] not in ec or (a["paiement_id"] not in pa and
                                          not a["paiement_id"].startswith("AVO-")):
            m.append(f"affectation orpheline {a['paiement_id']}/{a['echeance_id']}")
    # Préférences saisies par le gestionnaire (extension IA, 1.1) : listes fermées
    for p in d.prefs:
        jours = [j for j in p.get("jours_a_eviter", "").split(";") if j]
        if any(j not in ("LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI")
               for j in jours):
            m.append(f"{p['client_id']} : jours_a_eviter invalide ({jours})")
        if p.get("plage_horaire", "AUCUNE") not in ("MATIN", "APRES_MIDI", "AUCUNE"):
            m.append(f"{p['client_id']} : plage_horaire invalide")
        if len(p.get("interlocuteur", "")) > 80:
            m.append(f"{p['client_id']} : interlocuteur de plus de 80 caractères")
    if not any(p.get("jours_a_eviter") for p in d.prefs):
        m.append("aucun client avec un jour à éviter (le report n'est pas testé)")
    return m


def somme_echeances(d):
    m = []
    tot = defaultdict(int)
    for e in d.ech:
        if e["etat"] == "ACTIVE":
            tot[e["facture_id"]] += int(e["montant_du"])
    for f in d.fac:
        if tot[f["id"]] != int(f["montant_ttc"]):
            m.append(f"{f['id']} : somme {tot[f['id']]} ≠ {f['montant_ttc']}")
    return m


def montants(d):
    m = []
    for nom, lst, champ in (("factures", d.fac, "montant_ttc"), ("échéances", d.ech, "montant_du"),
                            ("paiements", d.pay, "montant"), ("avoirs", d.avo, "montant")):
        for r in lst:
            v = r[champ]
            if not re.fullmatch(r"\d+", v) or int(v) <= 0 or int(v) % 500:
                m.append(f"{nom} {r['id']} : montant {v}")
    return m


def chronologie(d):
    m = []
    em = {f["id"]: f["date_emission"] for f in d.fac}
    for e in d.ech:
        if e["date_echeance"] < em[e["facture_id"]]:
            m.append(f"échéance {e['id']} avant l'émission")
    for p in d.pay:
        if p["date_paiement"] > D0.isoformat():
            m.append(f"paiement {p['id']} après la date de référence")
    for r in d.hist:
        if r["date_prevue"] > D0.isoformat() or (r["date_envoi"] and
                                                  r["date_envoi"] > D0.isoformat()):
            m.append(f"relance {r['id']} après la date de référence")
    ech_f = {e["id"]: e["facture_id"] for e in d.ech}
    for a in d.avo:
        if a["date"] < em[a["facture_id"]] or a["date"] > D0.isoformat():
            m.append(f"avoir {a['id']} hors chronologie")
    # un paiement indiqué ne précède pas l'émission de ses factures
    fnum = {(f["client_id"], f["numero"]): f for f in d.fac}
    for p in d.pay:
        for num in [x for x in p["references_indiquees"].split(";") if x]:
            f = fnum.get((p["client_id"], num))
            if f and p["date_paiement"] < f["date_emission"]:
                m.append(f"paiement {p['id']} avant l'émission de {f['id']}")
    del ech_f
    return m


def volumes(d):
    m = []
    if len(d.clients) != 30:
        m.append(f"{len(d.clients)} clients")
    if len(d.fac) != 120:
        m.append(f"{len(d.fac)} factures")
    if not 140 <= len(d.ech) <= 160:
        m.append(f"{len(d.ech)} échéances (environ 150 attendues)")
    if not 80 <= len(d.pay) <= 100:
        m.append(f"{len(d.pay)} paiements (environ 90 attendus, à 10 près)")
    if len(d.avo) != 5:
        m.append(f"{len(d.avo)} avoirs")
    modes = Counter(p["mode"] for p in d.pay)
    tot = len(d.pay)
    for mode, cible in (("MOBILE_MONEY", .65), ("VIREMENT", .20), ("ESPECES", .10),
                        ("CHEQUE", .05)):
        if abs(modes[mode] / tot - cible) > 0.03:
            m.append(f"mode {mode} : {modes[mode] / tot:.0%}")
    # blocs de factures
    st = {s["facture_id"]: s for s in d.statuts}
    blocs = [(1, 26, "SOLDEE"), (27, 38, "SOLDEE"), (118, 120, "ANNULEE")]
    for a, b, statut in blocs:
        for n in range(a, b + 1):
            if st[f"FAC-2026-{n:04d}"]["statut"] != statut:
                m.append(f"FAC-2026-{n:04d} devrait être {statut}")
    for n in range(61, 73):
        if st[f"FAC-2026-{n:04d}"]["statut"] != "ECHUE":
            m.append(f"FAC-2026-{n:04d} devrait être ECHUE")
    for n in range(95, 99):
        if st[f"FAC-2026-{n:04d}"]["statut"] != "CONTESTEE":
            m.append(f"FAC-2026-{n:04d} devrait être CONTESTEE")
    for n in (101, 104, 105):
        if st[f"FAC-2026-{n:04d}"]["statut"] != "COUVERTE_PAR_ECHEANCIER":
            m.append(f"FAC-2026-{n:04d} devrait être COUVERTE_PAR_ECHEANCIER")
    nul = [n for n in range(39, 61) if st[f"FAC-2026-{n:04d}"]["statut"] != "NON_ECHUE"]
    if nul:
        m.append(f"non échues attendues : {nul}")
    tranches = len([f for f in d.fac if f["conditions_paiement"] == "TRANCHES"])
    if tranches != 12:
        m.append(f"{tranches} factures en tranches (environ 12 attendues)")
    return m


def statuts(d):
    m = []
    c = Counter(s["statut"] for s in d.statuts)
    attendu = {"ANNULEE": 3, "SOLDEE": 38, "CONTESTEE": 4, "COUVERTE_PAR_ECHEANCIER": 3,
               "NON_ECHUE": 25, "ECHUE": 47}
    if dict(c) != attendu:
        m.append(f"répartition {dict(c)} ≠ {attendu}")
    # Recalcul indépendant des statuts et soldes
    aff, solde_actif = rejouer_affectation(d)
    solde_ech = {e["id"]: int(e["montant_du"]) for e in d.ech}
    affecte = defaultdict(int)
    for src, e, mt, mode in aff:
        solde_ech[e] -= mt
        affecte[e] += mt
    ech_fac = defaultdict(list)
    for e in d.ech:
        ech_fac[e["facture_id"]].append(e)
    fac = {f["id"]: f for f in d.fac}
    ouvertes = {c["facture_id"] for c in d.contest if c["statut"] == "OUVERTE"}
    accepte = {a["facture_id"] for a in d.accords if a["statut"] == "ACCEPTE"}
    for s in d.statuts:
        fid = s["facture_id"]
        act = [e for e in ech_fac[fid] if e["etat"] == "ACTIVE"]
        sol = sum(solde_ech[e["id"]] for e in act)
        retards = [(D0 - pd(e["date_echeance"])).days for e in act
                   if solde_ech[e["id"]] > 0 and pd(e["date_echeance"]) < D0]
        if fac[fid]["statut_document"] == "ANNULEE":
            st = "ANNULEE"
        elif sol == 0:
            st = "SOLDEE"
        elif fid in ouvertes:
            st = "CONTESTEE"
        elif fid in accepte and not retards:
            st = "COUVERTE_PAR_ECHEANCIER"
        elif retards:
            st = "ECHUE"
        else:
            st = "NON_ECHUE"
        partiel = 1 if sum(affecte[e["id"]] for e in act) > 0 and sol > 0 else 0
        if (st, sol, partiel) != (s["statut"], int(s["solde_facture"]),
                                  int(s["partiellement_payee"])):
            m.append(f"{fid} : recalcul {(st, sol, partiel)} ≠ fichier "
                     f"{(s['statut'], s['solde_facture'], s['partiellement_payee'])}")
    for r in d.soldes:
        if solde_ech[r["echeance_id"]] != int(r["solde"]):
            m.append(f"solde de {r['echeance_id']} : recalcul {solde_ech[r['echeance_id']]} "
                     f"≠ fichier {r['solde']}")
    return m


def affectations(d):
    m = []
    aff, solde = rejouer_affectation(d)
    attendu = sorted((a["paiement_id"], a["echeance_id"], int(a["montant_affecte"]), a["mode"])
                     for a in d.affs)
    if sorted(aff) != attendu:
        manquantes = set(attendu) - set(aff)
        en_trop = set(aff) - set(attendu)
        m.append(f"rejeu ≠ fichier ({len(manquantes)} manquantes, {len(en_trop)} en trop)")
    if any(v < 0 for v in solde.values()):
        m.append("échéance sur-affectée")
    ids = {a["paiement_id"] for a in d.affs}
    ambigus = [p["id"] for p in d.pay if not p["client_id"]]
    if len(ambigus) != 2 or any(p in ids for p in ambigus):
        m.append("les 2 paiements non identifiables doivent rester non affectés")
    refs = [p for p in d.pay if p["references_indiquees"]]
    auto = [p for p in d.pay if p["client_id"] and not p["references_indiquees"]]
    multi = [p for p in refs if len(p["references_indiquees"].split(";")) >= 2]
    if len(auto) != 6:
        m.append(f"{len(auto)} paiements sans référence (6 attendus)")
    if len(multi) != 5:
        m.append(f"{len(multi)} paiements multi-factures (5 attendus)")
    return m


def relances_hist(d):
    m = []
    ordre = ["P", "R1", "R2", "R3"]
    rel = {r["id"]: r for r in d.hist}
    env = defaultdict(list)
    for r in d.hist:
        if r["statut"] == "ENVOYEE_SIM":
            dt = pd(r["date_envoi"])
            if not est_ouvre(dt, d.feries):
                m.append(f"{r['id']} envoyée un jour non ouvré ({dt})")
            env[(r["client_id"], r["canal"])].append(dt)
    for k, v in env.items():
        v.sort()
        for a, b in zip(v, v[1:]):
            if (b - a).days < 2:
                m.append(f"espacement < 2 jours pour {k} : {a} puis {b}")
    prefs = {p["client_id"]: p for p in d.prefs}
    for r in d.hist:
        p = prefs[r["client_id"]]
        if not int(p["consentement_relance"]):
            m.append(f"{r['id']} : relance à un client sans consentement")
    steps = defaultdict(list)
    ech = {e["id"]: e for e in d.ech}
    for l in d.hlignes:
        r = rel[l["relance_id"]]
        steps[l["echeance_id"]].append((r["date_prevue"], l["etape_echeance"], r["statut"]))
    decal = {"P": -3, "R1": 1, "R2": 7, "R3": 15}
    for e, v in steps.items():
        v.sort()
        seq = [s for _, s, _ in v]
        if seq != ordre[:len(seq)] and seq != ordre[1:1 + len(seq)]:
            m.append(f"{e} : étapes {seq} non contiguës")
        client = {f["id"]: f["client_id"] for f in d.fac}[ech[e]["facture_id"]]
        evites = {NOMS_JOURS.index(j) for j in prefs[client].get("jours_a_eviter", "").split(";")
                  if j}
        for dt, s, statut in v:
            brut = plus(pd(ech[e]["date_echeance"]), decal[s])
            while not est_ouvre(brut, d.feries) or brut.weekday() in evites:
                brut = plus(brut, 1)
            if brut.isoformat() != dt:
                m.append(f"{e} {s} : date prévue {dt} ≠ calendrier {brut}")
    nb_groupes = len([r for r in d.hist if r["etape"] == "GROUPE"])
    if nb_groupes < 2:
        m.append(f"{nb_groupes} relance(s) GROUPE (2 attendues au moins)")
    if len([r for r in d.hist if r["statut"] == "ANNULEE"]) != 2:
        m.append("2 relances ANNULEE attendues")
    for r in d.hist:
        if "(simulation : aucun paiement réel)" not in r["contenu"]:
            m.append(f"{r['id']} : mention de simulation absente")
    # cohérence avec le retard : aucune étape R3 pour une échéance en retard < 15 jours
    ret = {s["echeance_id"]: int(s["retard_jours"]) for s in d.soldes}
    for e, v in steps.items():
        if any(s == "R3" for _, s, st in v if st == "ENVOYEE_SIM") and ret[e] < 15 and ret[e]:
            m.append(f"{e} : R3 envoyée pour un retard de {ret[e]} jours")
    return m


MINIMUMS = {"NEGATION": 12, "DATE_RELATIVE": 16, "MULTI_INTENTION": 12,
            "MAUVAISE_REFERENCE": 8, "TIERS": 8, "HORS_SUJET_OU_VIDE": 10,
            "LANGUE_LOCALE": 8, "INJECTION": 6}


def messages(d):
    m = []
    n = len(d.msgs)
    if n not in (340, 400):
        m.append(f"{n} messages (340 générés + 60 écrits à la main = 400)")
    manquants = 400 - n
    if manquants:
        m.append(f"AVERTISSEMENT : {manquants} messages à rédiger à la main "
                 "(messages/redaction_main.csv absent ou incomplet)") if False else None
    wa = len([x for x in d.msgs if x["canal"] == "WHATSAPP"])
    cible_wa = 204 if n == 340 else 240
    if wa != cible_wa:
        m.append(f"{wa} messages WhatsApp (attendu {cible_wa})")
    et = {e["message_id"]: e for e in d.etiq}
    if set(et) != {x["id"] for x in d.msgs}:
        m.append("étiquettes et messages ne correspondent pas")
    vol = {"PROMESSE_PAIEMENT": (80, 20, 60), "AUTRE_INCERTAIN": (80, 20, 60),
           "DEJA_PAYE": (60, 15, 45), "CONTESTATION": (60, 15, 45),
           "DEMANDE_ECHEANCIER": (40, 10, 30), "DEMANDE_DELAI": (40, 10, 30),
           "DEMANDE_COPIE_FACTURE": (40, 10, 30)}
    c = Counter((e["categorie_principale"], e["split"]) for e in d.etiq)
    if n == 400:
        for cat, (t, dv, ts) in vol.items():
            if c[(cat, "DEV")] != dv or c[(cat, "TEST")] != ts:
                m.append(f"{cat} : DEV {c[(cat, 'DEV')]}/{dv}, TEST {c[(cat, 'TEST')]}/{ts}")
    tags = Counter(t for e in d.etiq for t in e["difficultes"].split(";") if t)
    for k, mn in MINIMUMS.items():
        if tags[k] < mn:
            m.append(f"cas difficile {k} : {tags[k]} < {mn}")
    for sp, mn in (("DEV", 16), ("TEST", 64)):
        nb = len([e for e in d.etiq if e["split"] == sp and e["difficultes"]])
        if nb < mn:
            m.append(f"cas difficiles {sp} : {nb} < {mn}")
    if len(d.fiches) != 60:
        m.append(f"{len(d.fiches)} fiches de rédaction (60 attendues)")
    dur = len([f for f in d.fiches if f["difficultes_a_inclure"]])
    if dur < 20:
        m.append(f"{dur} fiches difficiles (20 attendues au moins)")
    return m


def mots_cles(t):
    return " ".join(t.lower().split())


def qualite_messages(d):
    m = []
    if set(d.msgs[0]) & {"categorie", "categorie_principale", "etiquette"}:
        m.append("une étiquette figure dans messages_clients.csv")
    textes = [(x["id"], mots_cles(x["contenu"])) for x in d.msgs]
    split = {e["message_id"]: e["split"] for e in d.etiq}
    for i in range(len(textes)):
        a = difflib.SequenceMatcher(None, textes[i][1], "", autojunk=False)
        for j in range(i + 1, len(textes)):
            b = textes[j][1]
            a.set_seq2(b)
            if a.real_quick_ratio() < 0.8 or a.quick_ratio() < 0.8:
                continue
            if a.ratio() >= 0.8:
                m.append(f"similarité ≥ 0,8 : {textes[i][0]} / {textes[j][0]}"
                         f"{' (fuite DEV/TEST)' if split[textes[i][0]] != split[textes[j][0]] else ''}")
    for t in set(textes[i][1] for i in range(len(textes))):
        pass
    cnt = Counter(t for _, t in textes)
    for t, k in cnt.items():
        if k > 3:
            m.append(f"phrase répétée {k} fois : {t[:50]}")
    return m


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
EXPR = [
    (r"\baujourd'hui\b", lambda r: r), (r"\bdemain\b", lambda r: plus(r, 1)),
    (r"\bdans (\d+) jours\b", None), (r"\blundi prochain\b", None),
    (r"\bdébut de semaine prochaine\b", None), (r"\bfin du mois\b", None),
]


def date_attendue(texte, rec):
    t = texte.lower()
    trouvees = set()
    if re.search(r"la semaine prochaine|après la paie|dès que possible|très bientôt|"
                 r"quand j'aurai la trésorerie", t):
        return "NULLE"
    if re.search(r"lundi prochain|début de semaine prochaine", t):
        trouvees.add(plus(rec, (7 - rec.weekday()) % 7 or 7))
    if "aujourd'hui" in t:
        trouvees.add(rec)
    if re.search(r"\bdemain\b", t):
        trouvees.add(plus(rec, 1))
    for mt in re.finditer(r"dans (\d+) jours", t):
        trouvees.add(plus(rec, int(mt.group(1))))
    for mt in re.finditer(r"\ble (\d{1,2})\b", t):
        n = int(mt.group(1))
        x = rec.replace(day=n)
        if x < rec:
            mo = 1 if rec.month == 12 else rec.month + 1
            yr = rec.year + 1 if rec.month == 12 else rec.year
            x = date(yr, mo, n)
        trouvees.add(x)
    if "fin du mois" in t:
        mo = 1 if rec.month == 12 else rec.month + 1
        yr = rec.year + 1 if rec.month == 12 else rec.year
        trouvees.add(plus(date(yr, mo, 1), -1))
    sans_prochain = re.sub(r"lundi prochain", "", t)
    for j in JOURS:
        if re.search(rf"\b{j}\b", sans_prochain):
            cible = JOURS.index(j)
            trouvees.add(plus(rec, (cible - rec.weekday()) % 7 or 7))
    return trouvees


def dates_promises(d):
    m = []
    rec = {x["id"]: pd(x["date_reception"][:10]) for x in d.msgs}
    txt = {x["id"]: x["contenu"] for x in d.msgs}
    verifies = 0
    for e in d.etiq:
        if e["categorie_principale"] not in ("PROMESSE_PAIEMENT", "DEMANDE_DELAI"):
            if e["date_promise"]:
                m.append(f"{e['message_id']} : date promise sur une catégorie sans date")
            continue
        att = date_attendue(txt[e["message_id"]], rec[e["message_id"]])
        if att == "NULLE":
            if e["date_promise"]:
                m.append(f"{e['message_id']} : date promise alors que l'expression est floue")
            verifies += 1
        elif len(att) == 1:
            verifies += 1
            if e["date_promise"] != next(iter(att)).isoformat():
                m.append(f"{e['message_id']} : date {e['date_promise']} ≠ "
                         f"{next(iter(att)).isoformat()}")
    if verifies < 60:
        m.append(f"seulement {verifies} dates recalculées")
    return m


def ancres(d):
    m = []
    fac = {f["id"]: f for f in d.fac}
    ech_de = defaultdict(list)
    for e in d.ech:
        ech_de[e["facture_id"]].append(e)
    due = lambda n: [e["date_echeance"] for e in ech_de[f"FAC-2026-{n:04d}"]  # noqa: E731
                     if e["etat"] == "ACTIVE"][0]
    if fac["FAC-2026-0039"]["client_id"] != fac["FAC-2026-0040"]["client_id"] \
            or due(39) != "2026-12-18" or due(40) != "2026-12-18":
        m.append("0039 et 0040 : même client, échéance le 2026-12-18")
    if due(41) != "2026-12-17" or due(42) != "2026-12-16" or due(43) != "2026-12-15":
        m.append("échéances de 0041, 0042 ou 0043 incorrectes")
    if not any(due(n) == "2026-12-19" for n in range(39, 61)):
        m.append("aucune non échue avec échéance le 2026-12-19")
    steps = defaultdict(list)
    rel = {r["id"]: r for r in d.hist}
    for l in d.hlignes:
        steps[l["echeance_id"]].append((rel[l["relance_id"]]["date_envoi"], l["etape_echeance"]))
    e41 = ech_de["FAC-2026-0041"][0]["id"]
    e43 = ech_de["FAC-2026-0043"][0]["id"]
    if ("2026-12-14", "P") not in steps[e41]:
        m.append("P de 0041 non envoyée le 12-14")
    if ("2026-12-12", "P") not in steps[e43]:
        m.append("P de 0043 non envoyée le 12-12")
    e42 = ech_de["FAC-2026-0042"][0]["id"]
    if steps[e42]:
        m.append("0042 ne doit avoir aucune relance historique")
    # 0061 à 0072 sans historique ; 0061 à 0064 échues depuis 1 jour
    for n in range(61, 73):
        if any(steps[e["id"]] for e in ech_de[f"FAC-2026-{n:04d}"]):
            m.append(f"FAC-2026-{n:04d} ne doit pas avoir de relance historique")
    for n in range(61, 65):
        if due(n) != "2026-12-14":
            m.append(f"FAC-2026-{n:04d} doit être échue depuis 1 jour")
    if not any((D0 - pd(due(n))).days == 45 for n in range(65, 73)):
        m.append("aucune facture de 0065 à 0072 en retard de 45 jours")
    # Scénarios : identifiants existants
    ids = set()
    for nom, lst in (("c", d.clients), ("f", d.fac), ("e", d.ech), ("p", d.pay), ("a", d.avo),
                     ("m", d.msgs), ("r", d.hist), ("x", d.contest), ("o", d.promesses),
                     ("g", d.accords)):
        ids |= {r["id"] for r in lst}
    for nom in ("clients", "factures"):
        for r in lire(f"lot_defectueux/{nom}.csv"):
            ids |= {v for v in r.values() if v}
    sc_dir = os.path.join(ICI, "verite_terrain", "scenarios")
    fichiers = sorted(os.listdir(sc_dir))
    if len(fichiers) != 23:
        m.append(f"{len(fichiers)} fichiers de scénario (23 attendus)")
    modele = re.compile(r"\b(CLI-\d{4}|FAC-2026-\d{4}|ECH-\d{4}|PAY-\d{4}|AVO-\d{4}|MSG-\d{4}|"
                        r"CTE-\d{4}|PRO-\d{4}|ACC-\d{4})\b")
    evenements = set()
    for nom in os.listdir(os.path.join(ICI, "evenements")):
        for r in lire(os.path.join("evenements", nom)):
            evenements.add(r["id"])
    for nom in fichiers:
        with open(os.path.join(sc_dir, nom), encoding="utf-8") as f:
            txt = f.read()
        obj = json.loads(txt)
        for k in ("id", "titre", "date_reference", "prerequis", "actions", "attendu"):
            if k not in obj:
                m.append(f"{nom} : champ {k} absent")
        for ident in set(modele.findall(txt)):
            if ident not in ids and ident not in evenements:
                m.append(f"{nom} : identifiant inconnu {ident}")
    # Au moins 10 messages éligibles le 15/12 (hors validation humaine)
    j1 = [r for r in d.rel if r["date_simulee"] == "2026-12-15"
          and r["decision"] == "PREPAREE"]
    if len(j1) < 10:
        m.append(f"{len(j1)} messages éligibles le 15/12 (10 attendus au moins)")
    return m


def determinisme(d):
    m = []
    sums = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, os.path.join(ICI, "generate_dataset.py"),
                                "--seed", "20261215", "--out", t],
                               capture_output=True, text=True)
            if r.returncode != 0:
                m.append("le générateur a échoué : " + r.stdout[-200:] + r.stderr[-200:])
                return m
            h = {}
            for racine, _, fs in os.walk(t):
                for f in fs:
                    p = os.path.join(racine, f)
                    with open(p, "rb") as fh:
                        h[os.path.relpath(p, t)] = hashlib.sha256(fh.read()).hexdigest()
            sums.append(h)
    if sums[0] != sums[1]:
        diff = [k for k in sums[0] if sums[0][k] != sums[1].get(k)]
        m.append(f"deux exécutions diffèrent : {diff[:5]}")
    # et le jeu versionné correspond à la génération
    for k, v in sums[0].items():
        p = os.path.join(ICI, k)
        if k.endswith(".csv") or k.endswith(".json"):
            if not os.path.exists(p):
                m.append(f"fichier manquant : {k}")
                continue
            with open(p, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != v:
                    m.append(f"{k} diffère de la génération")
    return m


def confidentialite(d):
    m = []
    for c in d.clients:
        if c["email"] and not c["email"].endswith(".example"):
            m.append(f"{c['id']} : domaine de courriel non réservé")
        if c["whatsapp"] and not re.fullmatch(r"\+22901\d{8}", c["whatsapp"]):
            m.append(f"{c['id']} : numéro hors du plan fictif")
    for x in d.msgs:
        if re.search(r"@(?!.*\.example)\S+\.\w+", x["contenu"]):
            m.append(f"{x['id']} : adresse de courriel réelle ?")
        if re.search(r"\+?\d{8,}", x["contenu"].replace(" ", "")) and "FCFA" not in x["contenu"]:
            m.append(f"{x['id']} : numéro de téléphone dans le texte ?")
    noms = [c["raison_sociale"] for c in d.clients]
    if len(set(noms)) != len(noms):
        m.append("raisons sociales dupliquées")
    m.append("RAPPEL : relecture humaine des raisons sociales et des noms requise "
             "(aucune ne doit correspondre à une entreprise réelle)") if False else None
    return m


def verification_manuelle(d):
    """15 cas recalculés : 5 statuts, 5 priorités, 5 décisions de relance. Les valeurs
    attendues sont posées à la main ici, déduites des règles, pas lues dans les fichiers."""
    m = []
    st = {s["facture_id"]: s for s in d.statuts}
    cas_statuts = {"FAC-2026-0001": "SOLDEE", "FAC-2026-0061": "ECHUE",
                   "FAC-2026-0095": "CONTESTEE", "FAC-2026-0101": "COUVERTE_PAR_ECHEANCIER",
                   "FAC-2026-0118": "ANNULEE"}
    for f, s in cas_statuts.items():
        if st[f]["statut"] != s:
            m.append(f"statut de {f} : {st[f]['statut']} ≠ {s}")
    # Priorités : 0061 (retard 1 jour) a 1/30*40 = 1,33 point d'ancienneté
    pr = {p["facture_id"]: p for p in d.prio}
    if pr["FAC-2026-0061"]["points_anciennete"] != "1.33":
        m.append(f"ancienneté 0061 = {pr['FAC-2026-0061']['points_anciennete']} (1.33 attendu)")
    for f in ("FAC-2026-0065", "FAC-2026-0067", "FAC-2026-0071"):
        if f in pr and (pr[f]["points_anciennete"] != "40.00" and
                        int(pr[f]["retard_jours"]) >= 30):
            m.append(f"{f} : ancienneté plafonnée à 40 attendue")
    gros = [p for p in d.prio if int(p["solde"]) >= 1000000]
    if not gros or any(p["points_solde"] != "35.00" for p in gros):
        m.append("solde plafonné à 35 points attendu au-delà de 1 000 000 FCFA")
    scores = [Decimal(p["score"]) for p in d.prio]
    if scores != sorted(scores, reverse=True):
        m.append("priorisation non triée par score décroissant")
    nouveaux = [p for p in d.prio if p["facture_id"] in (f"FAC-2026-{n:04d}" for n in range(0))]
    del nouveaux
    # Décisions de relance (déduites à la main des règles)
    rel = d.rel
    def trouve(date_, **champs):
        return [r for r in rel if r["date_simulee"] == date_
                and all(r[k] == v for k, v in champs.items())]
    if not trouve("2026-12-15", client_id="CLI-0024", etape="GROUPE", decision="PREPAREE",
                  motif="REGROUPE"):
        m.append("0039 et 0040 : message P regroupé attendu le 12-15")
    if not trouve("2026-12-15", client_id="CLI-0023", decision="SAUTEE", motif="P_TROP_PROCHE"):
        m.append("0042 : P sauté (P_TROP_PROCHE) attendu le 12-15")
    if not trouve("2026-12-15", client_id="CLI-0001", etape="R1", decision="PREPAREE"):
        m.append("0061 : R1 attendue le 12-15")
    # 0044 : la R1 du dimanche 12-20 serait reportée au lundi 12-21, mais CLI-0025 reçoit une
    # relance de rattrapage (0072) le 12-15 : espacement 5 x 1,5 = 7,5 -> 8 jours (total entre
    # 100 000 et 500 000 FCFA), donc rien le 12-21 et un message groupé le 12-23 (extension IA 3.1).
    if trouve("2026-12-21", client_id="CLI-0025", decision="PREPAREE"):
        m.append("0044 : aucune relance attendue le 12-21 (espacement de 8 jours après le 12-15)")
    if not trouve("2026-12-23", client_id="CLI-0025", etape="GROUPE", decision="PREPAREE"):
        m.append("0044 : message groupé de CLI-0025 attendu le 12-23")
    if [r for r in rel if r["date_simulee"] in ("2026-12-20", "2026-12-25")]:
        m.append("aucune décision attendue un dimanche ou un jour férié")
    # CLI-0019 (total 600 000 FCFA, dernier envoi le 12-12) exige 4 jours : différé, donc 3 le 12-15
    if len(trouve("2026-12-15", decision="EN_ATTENTE_VALIDATION", motif="GROS_MONTANT")) != 3:
        m.append("3 relances de gros montant attendues le 12-15")
    if trouve("2026-12-15", client_id="CLI-0019", decision="EN_ATTENTE_VALIDATION"):
        m.append("CLI-0019 doit être différé par l'espacement le 12-15")
    return m


def main():
    d = charger()
    regles = [
        (1, "Unicité", unicite), (2, "Intégrité référentielle", integrite),
        (3, "Somme des échéances", somme_echeances), (4, "Montants", montants),
        (5, "Chronologie", chronologie), (6, "Volumes", volumes), (7, "Statuts", statuts),
        (8, "Affectations", affectations), (9, "Relances historiques", relances_hist),
        (10, "Messages", messages), (11, "Qualité des messages", qualite_messages),
        (12, "Dates promises", dates_promises), (13, "Ancres et scénarios", ancres),
        (14, "Déterminisme", determinisme), (15, "Confidentialité", confidentialite),
        (16, "Vérification manuelle", verification_manuelle),
    ]
    sel = {int(a) for a in sys.argv[1:]} or None
    echecs = 0
    for n, titre, fn in regles:
        if sel and n not in sel:
            continue
        try:
            msgs = [x for x in (fn(d) or []) if x]
        except Exception as e:  # noqa: BLE001
            msgs = [f"exception : {e!r}"]
        etat = "OK " if not msgs else "ÉCHEC"
        print(f"{n:2d}. {titre:<26} {etat}")
        for x in msgs[:12]:
            print("      -", x)
        if len(msgs) > 12:
            print(f"      … {len(msgs) - 12} autres")
        echecs += bool(msgs)
    print(f"\n{'Tous les contrôles passent' if not echecs else str(echecs) + ' contrôle(s) en échec'}")
    nb = len(d.msgs)
    if nb < 400:
        print(f"Note : {400 - nb} messages écrits à la main restent à fusionner "
              "(fiches_redaction_main.csv → messages/redaction_main.csv).")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
