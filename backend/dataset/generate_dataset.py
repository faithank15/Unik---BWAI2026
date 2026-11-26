#!/usr/bin/env python3
"""Générateur déterministe du jeu de données fictif du recouvrement BWAI 2026.

Mêmes entrées, mêmes fichiers : une seule graine (SEED = 20261215), aucun appel à
l'heure réelle, aucun accès réseau. La vérité terrain est calculée par un « oracle »
écrit ici, sans aucun code partagé avec le prototype.

Usage :  python generate_dataset.py --seed 20261215 --out dataset/

Les 340 messages sont fusionnés depuis messages/messages_generes_figes.csv, produit à
part par _composer_messages.py (étape distincte, modèle différent de celui qui classe).
Les 60 messages à rédiger à la main sont fusionnés depuis messages/redaction_main.csv
s'il existe (colonnes : message_id, contenu).
"""
import argparse
import copy
import csv
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

ICI = os.path.dirname(os.path.abspath(__file__))
SEED_DEFAUT = 20261215
D0 = date(2026, 12, 15)
FIN_SIM = date(2027, 1, 5)
SEUIL_GROS = 500000
MARGE_PROMESSE = 2
DELAI_ESCALADE = 5
ESPACEMENT_NORMAL = 2
ESPACEMENT_RATTRAPAGE = 5
EM_MIN = date(2026, 8, 3)
EM_MAX = date(2026, 12, 14)
ENTREPRISE = "Entreprise Démo"


def iso(d):
    return d.isoformat()


def pd(s):
    return date.fromisoformat(s)


def plus(d, n):
    return d + timedelta(days=n)


# ----------------------------------------------------------------------------------
# Calendrier
# ----------------------------------------------------------------------------------
FERIES = [
    ("2026-01-01", "Jour de l'An"), ("2026-01-10", "Fête nationale du Vodoun"),
    ("2026-04-06", "Lundi de Pâques"), ("2026-05-01", "Fête du Travail"),
    ("2026-05-14", "Ascension"), ("2026-05-25", "Lundi de Pentecôte"),
    ("2026-08-01", "Fête nationale"), ("2026-08-15", "Assomption"),
    ("2026-11-01", "Toussaint"), ("2026-12-25", "Noël"),
    ("2027-01-01", "Jour de l'An"), ("2027-01-10", "Fête nationale du Vodoun"),
]
SET_FERIES = {pd(d) for d, _ in FERIES}


def est_ouvre(d):
    return d.weekday() != 6 and d not in SET_FERIES


def prochain_ouvre(d):
    while not est_ouvre(d):
        d = plus(d, 1)
    return d


# ----------------------------------------------------------------------------------
# Clients
# ----------------------------------------------------------------------------------
# (raison sociale, secteur, ville, interlocuteur) — noms inventés, à relire.
CLIENTS_DEF = [
    ("Établissements Gbènami et Fils", "pièces automobiles", "Cotonou", "M. Roméo Gbènami"),
    ("Pharmacie Sèmèvo Services SARL", "pharmacie", "Abomey-Calavi", "Mme Flore Dossa"),
    ("Quincaillerie Hounkpè et Frères", "quincaillerie", "Cotonou", "M. Yves Hounkpè"),
    ("Imprimerie Tchitchi Services SARL", "imprimerie", "Porto-Novo", "Mme Adèle Tchitchi"),
    ("Traiteur Kossoungbo", "traiteur", "Abomey-Calavi", "Mme Pélagie Kossoungbo"),
    ("Boutique Wémèhoun", "fournitures de bureau", "Cotonou", "M. Landry Wémèhoun"),
    ("Dassi BTP SARL", "BTP", "Parakou", "M. Fiacre Dassi"),
    ("Informatique Zinsou-Alapini SARL", "informatique", "Cotonou", "Mme Nadège Alapini"),
    ("Établissements Fagnon et Fils", "transport", "Bohicon", "M. Cyriaque Fagnon"),
    ("Agro-Sèlè Services SARL", "agroalimentaire", "Ouidah", "Mme Estelle Sèlè"),
    ("Cabinet Tohoungba et Associés", "cabinet d'études", "Cotonou", "M. Hilaire Tohoungba"),
    ("Hôtel Ahouanvoèbla", "hôtellerie", "Abomey-Calavi", "Mme Prisca Ahouanvoèbla"),
    ("Boutique Akplogan", "pièces automobiles", "Cotonou", "M. Gildas Akplogan"),
    ("Lokonon Transports SARL", "transport", "Lokossa", "M. Désiré Lokonon"),
    ("Imprimerie Houéssou et Fils", "imprimerie", "Abomey-Calavi", "Mme Rosine Houéssou"),
    ("Grands Travaux Adédjouma SARL", "BTP", "Cotonou", "M. Ludovic Adédjouma"),
    ("Agro-Industrie Kpossou SARL", "agroalimentaire", "Parakou", "Mme Judith Kpossou"),
    ("Groupe Hôtelier Sagbo SARL", "hôtellerie", "Cotonou", "M. Marcellin Sagbo"),
    ("Tokpanou Informatique et Réseaux SARL", "informatique", "Abomey-Calavi", "M. Éric Tokpanou"),
    ("Boutique Gnonlonfoun", "fournitures de bureau", "Natitingou", "Mme Larissa Gnonlonfoun"),
    ("Boutique Dakpogan", "quincaillerie", "Djougou", "M. Aimé Dakpogan"),
    ("Traiteur Houngbédji", "traiteur", "Cotonou", "Mme Sylvie Houngbédji"),
    ("Boutique Yédomè", "pharmacie", "Porto-Novo", "Mme Carine Yédomè"),
    ("Boutique Mèdénou", "pièces automobiles", "Bohicon", "M. Armand Mèdénou"),
    ("Cabinet Gandonou Conseil", "cabinet d'études", "Cotonou", "Mme Odile Gandonou"),
    ("Sossavi Édition SARL", "imprimerie", "Porto-Novo", "M. Théophile Sossavi"),
    ("Établissements Ahlonsou et Fils", "quincaillerie", "Abomey-Calavi", "M. Rodrigue Ahlonsou"),
    ("Boutique Kiki-Zinsou", "traiteur", "Cotonou", "Mme Monique Kiki"),
    ("Nouveau Horizon Services SARL", "fournitures de bureau", "Cotonou", "M. Samuel Alladaye"),
    ("Djossou Transports SARL", "transport", "Ouidah", "Mme Claudine Djossou"),
]


def profil(i):
    if i <= 8:
        return "bon_payeur"
    if i <= 15:
        return "retardataire"
    if i <= 19:
        return "gros_compte"
    if i <= 24:
        return "whatsapp_seul"
    if i <= 26:
        return "courriel_seul"
    if i == 27:
        return "sans_consentement"
    if i == 28:
        return "sans_canal"
    return "nouveau"


def cid(i):
    return f"CLI-{i:04d}"


def construire_clients():
    clients, prefs = [], []
    for i, (nom, secteur, ville, inter) in enumerate(CLIENTS_DEF, 1):
        p = profil(i)
        email = f"contact@client-{i:04d}.example"
        wa = f"+22901{i:08d}"
        if p == "whatsapp_seul":
            email = ""
        elif p == "courriel_seul":
            wa = ""
        elif p == "sans_canal":
            email, wa = "", ""
        clients.append(dict(id=cid(i), raison_sociale=nom, secteur=secteur, ville=ville,
                            email=email, whatsapp=wa, actif=1))
        if p == "whatsapp_seul":
            pref, aut, cons = "WHATSAPP", "WHATSAPP", 1
        elif p == "courriel_seul":
            pref, aut, cons = "EMAIL", "EMAIL", 1
        elif p == "sans_consentement":
            pref, aut, cons = "WHATSAPP", "WHATSAPP;EMAIL", 0
        elif p == "sans_canal":
            pref, aut, cons = "WHATSAPP", "WHATSAPP;EMAIL", 1
        else:
            pref, aut, cons = ("EMAIL" if i % 2 == 0 else "WHATSAPP"), "WHATSAPP;EMAIL", 1
        prefs.append(dict(client_id=cid(i), canal_prefere=pref, canaux_autorises=aut,
                          consentement_relance=cons, interlocuteur=inter))
    return clients, prefs


def canal_client(c, prefs):
    """Canal d'envoi, ou (None, motif de revue)."""
    p = prefs[c["id"]]
    if not p["consentement_relance"]:
        return None, "CONSENTEMENT_ABSENT"
    aut = p["canaux_autorises"].split(";")

    def ok(canal):
        return canal in aut and bool(c["email"] if canal == "EMAIL" else c["whatsapp"])
    ordre = [p["canal_prefere"]] + [x for x in ("WHATSAPP", "EMAIL") if x != p["canal_prefere"]]
    for canal in ordre:
        if ok(canal):
            return canal, None
    return None, "CANAL_INVALIDE"


# ----------------------------------------------------------------------------------
# Factures et échéances
# ----------------------------------------------------------------------------------
DELAIS = {"COMPTANT": 0, "15_JOURS": 15, "30_JOURS": 30, "45_JOURS": 45, "60_JOURS": 60}
POIDS_COND = {"COMPTANT": 10, "15_JOURS": 15, "30_JOURS": 40, "45_JOURS": 15,
              "60_JOURS": 10}
TRANCHES_A = {7, 11, 15, 18}
TRANCHES_B = {28, 31, 36}
TRANCHES_C = {46, 48, 50, 52, 58}
TRANCHES = TRANCHES_A | TRANCHES_B | TRANCHES_C
MERGES = [(1, 9), (2, 10), (4, 12), (5, 13), (6, 14)]
MERGE_SET = {n for p in MERGES for n in p}
# Échues avec historique de relances (blocs dont la vie passée est reconstituée).
HIST_STRICT = {n for n in range(73, 92)} | {95, 96, 97, 98, 99, 100, 106,
                                             107, 108, 109, 110, 111, 112}


def fid(n):
    return f"FAC-2026-{n:04d}"


def numero(n):
    return f"FA-2026-{400 + n:04d}"


def choisir_cond(rng, due, interdits=()):
    ok = []
    for c, w in POIDS_COND.items():
        if c in interdits:
            continue
        if EM_MIN <= plus(due, -DELAIS[c]) <= EM_MAX:
            ok.append((c, w))
    if not ok:
        raise ValueError(f"aucune condition compatible pour l'échéance {due}")
    total = sum(w for _, w in ok)
    r = rng.random() * total
    for c, w in ok:
        r -= w
        if r <= 0:
            return c
    return ok[-1][0]


def montant_pour(rng, client_i, plafond=None):
    p = profil(client_i)
    if p == "gros_compte":
        m = rng.randrange(600, 3001) * 1000
    elif p == "whatsapp_seul":
        m = rng.randrange(20000, 150001, 500)
    else:
        r = rng.random()
        if r < 0.82:
            m = rng.randrange(50000, 500001, 500)
        elif r < 0.9:
            m = rng.randrange(20000, 50000, 500)
        else:
            m = rng.randrange(500500, 800001, 500)
    if plafond:
        m = min(m, plafond)
    return m - (m % 500)


def construire_factures(rng):
    """Retourne dict n -> facture. Les paiements sont planifiés plus loin."""
    F = {}
    meta = {}

    def ajouter(n, client, montant, due, bloc, cond=None, interdits=(), **kw):
        if n in TRANCHES:
            cond = "TRANCHES"
            em = plus(due, -30)
        else:
            if cond is None:
                cond = choisir_cond(rng, due, interdits)
            em = plus(due, -DELAIS[cond])
        assert EM_MIN <= em <= EM_MAX, (n, em)
        if cond == "TRANCHES":
            montant -= montant % 5000
            t1 = montant * 30 // 100
            t1 -= t1 % 500
            ech = [dict(rang=1, date=due, montant=t1, etat="ACTIVE", accord=None),
                   dict(rang=2, date=plus(em, 60), montant=montant - t1, etat="ACTIVE",
                        accord=None)]
        else:
            ech = [dict(rang=1, date=due, montant=montant, etat="ACTIVE", accord=None)]
        F[n] = dict(n=n, id=fid(n), numero=numero(n), client=client, montant=montant,
                    cond=cond, em=em, ech=ech, statut_doc="VALIDEE",
                    taux=(round(rng.randrange(10, 26) / 10, 1) if rng.random() < 0.4 else None),
                    refnorm=(f"FN-SIM-2026-{rng.randrange(100000, 999999)}"
                             if rng.random() < 0.6 else None),
                    bloc=bloc)
        F[n].update(kw)

    NH = ("COMPTANT",)  # exclu pour les factures dont la vie passée est reconstituée

    # Bloc A : soldées à temps (0001 à 0026)
    clients_a = [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 15, 16, 17, 18, 19, 20, 21,
                 22, 23, 25, 26]
    due_a = {}
    for n in range(1, 27):
        if n == 3:
            due_a[n] = date(2026, 11, 17)
        elif n - 8 in (1, 2, 4, 5, 6) and n > 8:
            due_a[n] = due_a[n - 8]
        else:
            due_a[n] = plus(date(2026, 9, 5), rng.randrange(0, 66))
    for n in range(1, 27):
        c = clients_a[n - 1]
        ajouter(n, c, montant_pour(rng, c), due_a[n], "A",
                interdits=NH if n == 3 else ())
    # Bloc B : soldées en retard (0027 à 0038)
    clients_b = [9, 10, 11, 12, 13, 14, 15, 9, 10, 11, 12, 13]
    for k, n in enumerate(range(27, 39)):
        c = clients_b[k]
        d = plus(date(2026, 9, 5), rng.randrange(0, 57))
        if n in TRANCHES_B:
            d = min(d, date(2026, 10, 25))
        ajouter(n, c, montant_pour(rng, c, 450000), d, "B")
    # Bloc C : non échues (0039 à 0060)
    spec_c = {
        39: (24, 40000, date(2026, 12, 18)), 40: (24, 60000, date(2026, 12, 18)),
        41: (22, 90000, date(2026, 12, 17)), 42: (23, 70000, date(2026, 12, 16)),
        43: (20, 55000, date(2026, 12, 15)), 44: (25, 120000, date(2026, 12, 19)),
        45: (12, 110000, date(2026, 12, 19)),
        46: (1, 150000, date(2026, 12, 22)), 47: (2, 220000, date(2026, 12, 24)),
        48: (29, 95000, date(2026, 12, 28)), 49: (30, 80000, date(2026, 12, 30)),
        50: (3, 180000, date(2027, 1, 2)), 51: (4, 260000, date(2027, 1, 4)),
        52: (16, 900000, date(2027, 1, 7)), 53: (5, 140000, date(2027, 1, 12)),
        54: (6, 75000, date(2027, 1, 15)), 55: (17, 1500000, date(2027, 1, 20)),
        56: (7, 310000, date(2027, 1, 25)), 57: (8, 205000, date(2027, 2, 1)),
        58: (18, 700000, date(2026, 12, 26)), 59: (19, 640000, date(2027, 2, 5)),
        60: (26, 85000, date(2027, 2, 10)),
    }
    for n, (c, m, d) in spec_c.items():
        cond = None
        if n == 42:
            cond = "15_JOURS"  # émise le 2026-12-01 (voir QUESTIONS.md)
        elif n in (39, 40, 41, 43):
            cond = "30_JOURS" if n != 41 else "15_JOURS"
        ajouter(n, c, m, d, "C", cond=cond, interdits=NH)
    # Bloc D : échues sans relance dans l'historique (0061 à 0072)
    spec_d = {61: (1, 12, 1), 62: (2, 12, 1), 63: (3, 12, 1), 64: (4, 12, 1),
              65: (27, None, 16), 66: (28, None, 20), 67: (5, None, 45), 68: (6, None, 24),
              69: (7, None, 31), 70: (8, None, 38), 71: (21, None, 52), 72: (25, None, 60)}
    for n, (c, _, retard) in spec_d.items():
        ajouter(n, c, montant_pour(rng, c, 450000), plus(D0, -retard), "D")
    # Bloc E : partiellement payées (0087 à 0094)
    spec_e = {87: (26, 3), 88: (29, 6), 89: (30, 12), 90: (23, 16), 91: (22, 18)}
    for n, (c, retard) in spec_e.items():
        ajouter(n, c, montant_pour(rng, c, 420000), plus(D0, -retard), "E", interdits=NH)
    for n, (c, d) in {92: (21, date(2027, 1, 8)), 93: (24, date(2026, 12, 30)),
                      94: (13, date(2027, 1, 15))}.items():
        ajouter(n, c, montant_pour(rng, c, 300000), d, "E", interdits=NH)
    # Bloc 0073 à 0086 : échues avec relances en cours
    spec_h = {73: (9, 9), 74: (9, 9), 75: (9, 9), 76: (10, 3), 77: (10, 3), 78: (10, 3),
              79: (11, 17), 80: (11, 17), 81: (11, 17), 82: (12, 6), 83: (13, 8),
              84: (14, 14), 85: (15, 20), 86: (20, 26)}
    for n, (c, retard) in spec_h.items():
        m = montant_pour(rng, c, 140000 if c in (9, 10, 11) else 400000)
        ajouter(n, c, m, plus(D0, -retard), "H", interdits=NH)
    # Bloc F : contestées (0095 à 0100)
    spec_f = {95: (13, date(2026, 11, 5)), 96: (14, date(2026, 11, 25)),
              97: (10, date(2026, 12, 4)), 98: (12, date(2026, 11, 24)),
              99: (15, date(2026, 11, 20)), 100: (20, date(2026, 12, 1))}
    for n, (c, d) in spec_f.items():
        ajouter(n, c, montant_pour(rng, c, 380000), d, "F", interdits=NH)
    # Bloc G : échéanciers (0101 à 0106)
    spec_g = {
        101: dict(c=2, m=450000, orig=date(2026, 10, 20), acc=date(2026, 11, 2),
                  tr=[date(2026, 11, 20), date(2026, 12, 10), date(2027, 1, 10)],
                  statut="ACCEPTE", payees=[1, 2]),
        102: dict(c=29, m=300000, orig=date(2026, 10, 25), acc=date(2026, 11, 5),
                  tr=[date(2026, 11, 10), date(2026, 12, 9), date(2027, 1, 8)],
                  statut="ACCEPTE", payees=[1]),
        103: dict(c=30, m=600000, orig=date(2026, 10, 10), acc=date(2026, 10, 28),
                  tr=[date(2026, 11, 5), date(2026, 11, 23), date(2027, 1, 5)],
                  statut="ACCEPTE", payees=[1]),
        104: dict(c=3, m=360000, orig=date(2026, 11, 1), acc=date(2026, 11, 12),
                  tr=[date(2026, 11, 25), date(2026, 12, 22), date(2027, 1, 22)],
                  statut="ACCEPTE", payees=[1]),
        105: dict(c=4, m=240000, orig=date(2026, 11, 20), acc=date(2026, 12, 1),
                  tr=[date(2026, 12, 12), date(2027, 1, 12), date(2027, 2, 12)],
                  statut="ACCEPTE", payees=[1]),
    }
    for n, g in spec_g.items():
        ajouter(n, g["c"], g["m"], g["orig"], "G", interdits=NH)
        f = F[n]
        f["ech"][0]["etat"] = "REMPLACEE"
        part = g["m"] // 3
        for r, dt in enumerate(g["tr"], 1):
            f["ech"].append(dict(rang=r, date=dt, montant=part, etat="ACTIVE",
                                 accord=f"ACC-{n - 100:04d}"))
        meta[n] = g
    ajouter(106, 19, 270000, date(2026, 12, 11), "G", cond="30_JOURS")
    meta[106] = dict(statut="PROPOSE", acc=date(2026, 12, 14))
    # Bloc I : gros montants échus (0113 à 0117)
    for n, (c, m) in {113: (16, 1200000), 114: (17, 2400000), 115: (18, 750000),
                      116: (19, 280000), 117: (19, 320000)}.items():
        ajouter(n, c, m, date(2026, 12, 14), "I")
    # Bloc J : annulées avec avoir (0118 à 0120)
    for n, (c, d) in {118: (25, date(2026, 10, 15)), 119: (26, date(2026, 11, 5)),
                      120: (29, date(2026, 11, 25))}.items():
        ajouter(n, c, montant_pour(rng, c, 350000), d, "J")
        F[n]["statut_doc"] = "ANNULEE"
    # Promesses : ajustements de dates d'échéance déjà fixés par les spécifications.
    spec_k = {107: (3, date(2026, 12, 1)), 108: (4, date(2026, 11, 20)),
              109: (5, date(2026, 12, 5)), 110: (6, date(2026, 11, 25)),
              111: (7, date(2026, 11, 15)), 112: (8, date(2026, 11, 28))}
    for n, (c, d) in spec_k.items():
        ajouter(n, c, montant_pour(rng, c, 350000), d, "K", interdits=NH)
    return F, meta


# ----------------------------------------------------------------------------------
# Paiements, avoirs et affectation
# ----------------------------------------------------------------------------------
def arrondi500(x):
    return int(x) - int(x) % 500


def planifier_paiements(rng, F, meta):
    """Liste de paiements (sans id) et d'avoirs. references : numéros de facture."""
    pay = []

    def P(client, d, montant, refs):
        assert montant > 0
        if isinstance(client, int):
            client = cid(client)
        pay.append(dict(client=client, date=d, montant=montant, refs=list(refs)))

    def fractionner(total, k):
        parts, reste = [], total
        for i in range(k - 1):
            p = arrondi500(reste * rng.randrange(30, 61) / 100)
            p = max(500, min(p, reste - 500 * (k - i - 1)))
            parts.append(p)
            reste -= p
        parts.append(reste)
        return parts

    def versements(f, dates, k):
        parts = fractionner(f["ech"][0]["montant"], k)
        for dt, m in zip(dates, parts):
            P(f["client"], dt, m, [f["numero"]])

    deux_a = 0
    for n in range(1, 27):
        f = F[n]
        if n in MERGE_SET:
            continue
        due = f["ech"][0]["date"]
        if n in TRANCHES:
            for e in f["ech"]:
                hi = min(e["date"], plus(D0, -1))
                lo = f["em"]
                dt = max(lo, plus(hi, -rng.randrange(0, 7)))
                P(f["client"], dt, e["montant"], [f["numero"]])
        elif n == 3:
            P(f["client"], plus(due, -3), f["montant"], [f["numero"]])
        else:
            deux_a += 1
            k = 2 if deux_a <= 10 else 1
            fin = max(f["em"], plus(due, -rng.randrange(0, 9)))
            dates = [fin]
            if k == 2:
                lo = f["em"]
                dates = [plus(lo, rng.randrange(0, max(1, (fin - lo).days))), fin]
                dates.sort()
            versements(f, dates, k)
    for i, j in MERGES:
        fi, fj = F[i], F[j]
        lo = max(fi["em"], fj["em"])
        hi = min(fi["ech"][0]["date"], fj["ech"][0]["date"])
        assert lo <= hi, (i, j, lo, hi)
        dt = plus(lo, rng.randrange(0, (hi - lo).days + 1))
        P(fi["client"], dt, fi["montant"] + fj["montant"], [fi["numero"], fj["numero"]])
    # Soldées en retard
    for n in range(27, 39):
        f = F[n]
        if n in TRANCHES:
            for e in f["ech"]:
                marge = (plus(D0, -1) - e["date"]).days
                dt = plus(e["date"], rng.randrange(5, min(40, marge) + 1))
                P(f["client"], dt, e["montant"], [f["numero"]])
        else:
            due = f["ech"][0]["date"]
            marge = (plus(D0, -1) - due).days
            k = 3 if n in (27, 29, 30, 33, 34) else 2
            ds = sorted(plus(due, rng.randrange(5, min(40, marge) + 1)) for _ in range(k))
            versements(f, ds, k)
    # Partiellement payées (0087 à 0094)
    for n in range(87, 95):
        f = F[n]
        m = arrondi500(f["montant"] * rng.randrange(20, 81) / 100)
        m = max(500, min(m, f["montant"] - 500))
        lo = plus(f["em"], 1)
        hi = plus(D0, -4) if n <= 91 else plus(D0, -1)
        dt = plus(lo, rng.randrange(0, (hi - lo).days + 1))
        F[n]["part_payee"] = m
        P(f["client"], dt, m, [f["numero"]])
    # Échéanciers
    for n, g in meta.items():
        if g["statut"] != "ACCEPTE":
            continue
        f = F[n]
        tr = [e for e in f["ech"] if e["etat"] == "ACTIVE"]
        for r in g["payees"]:
            e = tr[r - 1]
            P(f["client"], plus(e["date"], -rng.randrange(1, 4)), e["montant"], [f["numero"]])
    # Paiements non identifiables
    pay.append(dict(client=None, date=date(2026, 12, 3), montant=85000, refs=[], inconnu=True))
    pay.append(dict(client=None, date=date(2026, 12, 9), montant=120000, refs=[],
                    inconnu=True))
    # Avoirs
    avoirs = []
    for n in (118, 119, 120):
        f = F[n]
        avoirs.append(dict(facture=n, date=plus(f["em"], rng.randrange(3, 10)),
                           montant=f["montant"], motif="annulation de facture"))
    avoirs.append(dict(facture=68, date=date(2026, 12, 1),
                       montant=arrondi500(F[68]["montant"] * 0.1) or 500,
                       motif="remise commerciale"))
    avoirs.append(dict(facture=89, date=plus(D0, -2),
                       montant=arrondi500((F[89]["montant"] - F[89]["part_payee"]) * 0.2) or 500,
                       motif="geste commercial"))
    return pay, avoirs


def affecter(events, echeances, factures_par_num, clients_de):
    """events triés ; retourne la liste d'affectations. Règle de la section 7 du
    document de données, écrite ici indépendamment du prototype."""
    solde = {e["id"]: e["montant"] for e in echeances if e["etat"] == "ACTIVE"}
    ech_par_fac = defaultdict(list)
    ech_par_client = defaultdict(list)
    for e in echeances:
        if e["etat"] == "ACTIVE":
            ech_par_fac[e["facture"]].append(e)
            ech_par_client[clients_de[e["facture"]]].append(e)
    out, restes = [], {}

    def prendre(src, date_, e, reste, mode):
        s = solde[e["id"]]
        m = min(reste, s)
        if m <= 0:
            return reste
        solde[e["id"]] -= m
        out.append(dict(src=src, ech=e["id"], montant=m, mode=mode, date=date_))
        return reste - m

    for ev in events:
        if ev["kind"] == "PAY":
            reste = ev["montant"]
            if ev["client"]:
                for num in ev["refs"]:
                    fac = factures_par_num.get((ev["client"], num))
                    if not fac:
                        continue
                    for e in sorted(ech_par_fac[fac], key=lambda x: (x["date"], x["id"])):
                        if solde[e["id"]] > 0:
                            reste = prendre(ev["id"], ev["date"], e, reste, "INDIQUEE")
                if reste > 0:
                    for e in sorted(ech_par_client[ev["client"]],
                                    key=lambda x: (x["date"], x["id"])):
                        if solde[e["id"]] > 0:
                            reste = prendre(ev["id"], ev["date"], e, reste, "AUTO_ANCIENNETE")
            restes[ev["id"]] = reste
        else:
            total = sum(solde[e["id"]] for e in ech_par_fac[ev["facture"]])
            assert ev["montant"] <= total, (ev["id"], ev["montant"], total)
            reste = ev["montant"]
            for e in sorted(ech_par_fac[ev["facture"]], key=lambda x: (x["date"], x["id"])):
                reste = prendre(ev["id"], ev["date"], e, reste, "AUTO_ANCIENNETE")
            assert reste == 0
    return out, restes


# ----------------------------------------------------------------------------------
# État du monde et oracle des relances
# ----------------------------------------------------------------------------------
ORDRE = ["P", "R1", "R2", "R3"]
GRAVITE = {"R1": 1, "P": 2, "R2": 3, "R3": 4}
DECALAGE = {"P": -3, "R1": 1, "R2": 7, "R3": 15}


def date_brute(e_date, step):
    return plus(e_date, DECALAGE[step])


class Etat:
    pass


def solde_ech(et, ech_id, d):
    e = et.ech[ech_id]
    pris = sum(a["montant"] for a in et.aff if a["ech"] == ech_id and a["date"] <= d)
    return e["montant"] - pris


def solde_facture(et, fid_, d):
    return sum(solde_ech(et, e["id"], d) for e in et.ech.values()
               if e["facture"] == fid_ and e["etat"] == "ACTIVE")


def contestation_ouverte(et, e, d):
    for c in et.contest:
        if c["facture"] != e["facture"]:
            continue
        if c["ech"] and c["ech"] != e["id"]:
            continue
        if c["ouverture"] <= d and (c["cloture"] is None or c["cloture"] > d):
            return True
    return False


def accord_accepte(et, fid_):
    return any(a["facture"] == fid_ and a["statut"] == "ACCEPTE" for a in et.accords.values())


def retard_ech(et, ech_id, d):
    e = et.ech[ech_id]
    if e["etat"] != "ACTIVE":
        return 0
    if solde_ech(et, ech_id, d) > 0 and e["date"] < d:
        return (d - e["date"]).days
    return 0


def suspension(et, e, d):
    """Motif de suspension ou None (section 7.3)."""
    if contestation_ouverte(et, e, d):
        return "SUSPENDU_CONTESTATION"
    for p in et.promesses:
        if p["facture"] == e["facture"] and p["statut"] == "EN_COURS" \
                and d <= plus(p["date"], MARGE_PROMESSE):
            return "SUSPENDU_PROMESSE"
    if accord_accepte(et, e["facture"]):
        impayee = any(x["facture"] == e["facture"] and x["etat"] == "ACTIVE"
                      and retard_ech(et, x["id"], d) > 0 for x in et.ech.values())
        if not impayee:
            return "SUSPENDU_ECHEANCIER"
    for m in et.messages_attente:
        if m["client"] == et.facture_client[e["facture"]] \
                and (m["facture"] is None or m["facture"] == e["facture"]) \
                and m["debut"] <= d:
            return "SUSPENDU_MESSAGE_EN_ATTENTE"
    return None


def jour_sim(et, d):
    """Une journée de planification + envoi (spec. section 7). Retourne les lignes
    attendues et un détail utilisé par les scénarios."""
    rows, detail = [], []
    if not est_ouvre(d):
        return rows, detail

    def ligne(client, canal, etape, echs, decision, motif):
        rows.append(dict(date=iso(d), client=client, canal=canal or "", etape=etape,
                         echeances=";".join(echs), decision=decision, motif=motif))

    # 3. promesses
    for p in et.promesses:
        if p["statut"] == "EN_COURS":
            if solde_facture(et, p["facture"], d) == 0:
                p["statut"] = "TENUE"
            elif plus(p["date"], MARGE_PROMESSE) < d:
                p["statut"] = "NON_TENUE"
    # 4-5. candidats, suspensions
    susp = defaultdict(list)
    candidats = []
    for e in sorted(et.ech.values(), key=lambda x: x["id"]):
        if e["etat"] != "ACTIVE" or et.inv[e["facture"]]["statut_doc"] != "VALIDEE":
            continue
        if solde_ech(et, e["id"], d) <= 0:
            continue
        c = et.facture_client[e["facture"]]
        m = suspension(et, e, d)
        canal, _ = canal_client(et.clients[c], et.prefs)
        if m:
            susp[(c, canal or "", m)].append(e["id"])
        else:
            candidats.append(e)
    for (c, canal, m), echs in sorted(susp.items()):
        ligne(c, canal, "", sorted(echs), "SUSPENDUE", m)
    # Étape à préparer
    groupes = defaultdict(list)
    revue_vue = set()
    for e in candidats:
        c = et.facture_client[e["facture"]]
        canal, motif_revue = canal_client(et.clients[c], et.prefs)
        steps = et.steps.setdefault(e["id"], {})
        p_applicable = not accord_accepte(et, e["facture"])
        cand, saute = None, []
        for s in ORDRE:
            if s == "P" and not p_applicable:
                continue
            if s in steps:
                continue
            eff = prochain_ouvre(date_brute(e["date"], s))
            if s == "P" and eff < d:
                saute.append(("P", "P_APRES_ECHEANCE" if e["date"] < d else "P_TROP_PROCHE"))
                continue
            if eff <= d:
                cand = (s, eff)
            break
        if canal is None:
            if cand and (c, motif_revue) not in revue_vue \
                    and ("REVUE", motif_revue, c) not in et.revues:
                et.revues.add(("REVUE", motif_revue, c))
                revue_vue.add((c, motif_revue))
                ligne(c, "", "", [e["id"]], "REVUE", motif_revue)
            continue
        for s, motif in saute:
            steps[s] = ("SAUTEE", d)
            ligne(c, canal, "P", [f"{e['id']}:P"], "SAUTEE", motif)
        if cand:
            s, eff = cand
            prec = [x for x in ORDRE[:ORDRE.index(s)] if steps.get(x, ("",))[0] == "SENT"]
            tard = False
            if prec:
                x = prec[-1]
                tard = steps[x][1] > prochain_ouvre(date_brute(e["date"], x))
            groupes[(c, canal)].append(dict(
                e=e, step=s, eff=eff, raw=date_brute(e["date"], s),
                rattrapage=(eff < d) or tard))
    # 6-7. regroupement, espacement, gros montant, envoi simulé
    for (c, canal), lignes in sorted(groupes.items()):
        dernier = max(et.envois.get((c, canal), [date.min]))
        ecart = ESPACEMENT_RATTRAPAGE if any(l["rattrapage"] for l in lignes) \
            else ESPACEMENT_NORMAL
        if dernier != date.min and (d - dernier).days < ecart:
            continue
        total = sum(solde_ech(et, l["e"]["id"], d) for l in lignes)
        ton = max((l["step"] for l in lignes), key=lambda s: GRAVITE[s])
        etape = lignes[0]["step"] if len(lignes) == 1 else "GROUPE"
        decision = "EN_ATTENTE_VALIDATION" if total > SEUIL_GROS else "PREPAREE"
        if decision == "EN_ATTENTE_VALIDATION":
            motif = "GROS_MONTANT"
        elif any(l["eff"] == d and l["raw"] != d for l in lignes):
            motif = "JOUR_NON_OUVRE_REPORTE"
        elif len(lignes) > 1:
            motif = "REGROUPE"
        else:
            motif = ""
        echs = sorted(f"{l['e']['id']}:{l['step']}" for l in lignes)
        ligne(c, canal, etape, echs, decision, motif)
        if len(lignes) > 1:
            for l in lignes:
                if GRAVITE[l["step"]] < GRAVITE[ton]:
                    ligne(c, canal, l["step"], [f"{l['e']['id']}:{l['step']}"],
                          "ABSORBEE", "REGROUPE")
        for l in lignes:
            et.steps[l["e"]["id"]][l["step"]] = ("SENT", d)
        et.envois.setdefault((c, canal), []).append(d)
        detail.append(dict(client=c, canal=canal, etape=etape, ton=ton, decision=decision,
                           total=total, lignes=[(l["e"]["id"], l["step"]) for l in lignes]))
    # 8. escalade
    for e in sorted(et.ech.values(), key=lambda x: x["id"]):
        if e["etat"] != "ACTIVE" or e["id"] in et.escalades:
            continue
        if et.inv[e["facture"]]["statut_doc"] != "VALIDEE" or solde_ech(et, e["id"], d) <= 0:
            continue
        s3 = et.steps.get(e["id"], {}).get("R3")
        if s3 and s3[0] == "SENT" and (d - s3[1]).days >= DELAI_ESCALADE \
                and not suspension(et, e, d):
            et.escalades.add(e["id"])
            c = et.facture_client[e["facture"]]
            canal, _ = canal_client(et.clients[c], et.prefs)
            ligne(c, canal, "", [e["id"]], "REVUE", "ESCALADE")
    return rows, detail


def simuler(et, debut, fin):
    rows, details = [], {}
    d = debut
    while d <= fin:
        r, det = jour_sim(et, d)
        rows += r
        details[d] = det
        d = plus(d, 1)
    return rows, details


# ----------------------------------------------------------------------------------
# Canevas (section 14 de la spécification) — pour le contenu des relances historiques
# ----------------------------------------------------------------------------------
CANEVAS = {
    "P": {
        "WHATSAPP": "{salutation}, un rappel amical de {entreprise} : voici ce qui arrive "
                    "bientôt à échéance.\n{bloc_factures}\nPour régler : référence de "
                    "paiement {reference_paiement}\n{mention_simulation}.\nMerci et bonne "
                    "journée !",
        "EMAIL": "Objet : Rappel d'échéance à venir – {entreprise}\n\n{salutation},\n\nNous "
                 "vous rappelons que les règlements suivants arrivent à échéance "
                 "prochainement :\n{bloc_factures}\n\nTotal : {total_solde} FCFA.\nPour "
                 "régler, vous pouvez utiliser la référence de paiement "
                 "{reference_paiement} {mention_simulation}.\n\nSi vous avez déjà payé, "
                 "merci de ne pas tenir compte de ce message.\n\nCordialement,\n{entreprise}",
    },
    "R1": {
        "WHATSAPP": "{salutation}, sauf erreur de notre part, nous n'avons pas encore reçu "
                    "le règlement de {entreprise} pour :\n{bloc_factures}\nRéférence de "
                    "paiement : {reference_paiement} {mention_simulation}.\nSi vous avez "
                    "déjà payé, merci de nous l'indiquer.",
        "EMAIL": "Objet : Rappel : règlement en attente – {entreprise}\n\n{salutation},\n\n"
                 "Sauf erreur de notre part, nous n'avons pas encore reçu le règlement de :"
                 "\n{bloc_factures}\n\nTotal restant dû : {total_solde} FCFA.\nRéférence de "
                 "paiement : {reference_paiement} {mention_simulation}.\n\nSi vous avez "
                 "déjà effectué ce règlement, merci de nous l'indiquer ; dans le cas "
                 "contraire, nous vous remercions de procéder au paiement.\n\nCordialement,"
                 "\n{entreprise}",
    },
    "R2": {
        "WHATSAPP": "{salutation}, malgré notre précédent rappel, les sommes suivantes "
                    "restent impayées auprès de {entreprise} :\n{bloc_factures}\nMerci de "
                    "régulariser rapidement, référence {reference_paiement} "
                    "{mention_simulation}. En cas de difficulté, répondez-nous pour en "
                    "discuter.",
        "EMAIL": "Objet : Second rappel : règlement en attente – {entreprise}\n\n"
                 "{salutation},\n\nMalgré notre précédent rappel, nous constatons que les "
                 "sommes suivantes restent impayées :\n{bloc_factures}\n\nTotal restant "
                 "dû : {total_solde} FCFA.\nNous vous demandons de régulariser cette "
                 "situation dans les meilleurs délais, avec la référence de paiement "
                 "{reference_paiement} {mention_simulation}.\n\nSi une difficulté explique "
                 "ce retard, nous vous invitons à nous répondre afin d'en discuter.\n\n"
                 "Cordialement,\n{entreprise}",
    },
    "R3": {
        "WHATSAPP": "{salutation}, dernier rappel de {entreprise} : les sommes suivantes "
                    "sont toujours impayées.\n{bloc_factures}\nSans règlement ou réponse de "
                    "votre part, nous examinerons avec vous les suites à donner à ce "
                    "dossier. Référence de paiement : {reference_paiement} "
                    "{mention_simulation}.",
        "EMAIL": "Objet : Dernier avis avant examen du dossier – {entreprise}\n\n"
                 "{salutation},\n\nNos précédents rappels sont restés sans effet. Les "
                 "sommes suivantes demeurent impayées :\n{bloc_factures}\n\nTotal restant "
                 "dû : {total_solde} FCFA.\nÀ défaut de règlement ou de réponse de votre "
                 "part, nous serons amenés à examiner avec vous les suites à donner à ce "
                 "dossier.\n\nRéférence de paiement : {reference_paiement} "
                 "{mention_simulation}.\n\nCordialement,\n{entreprise}",
    },
}


def fmt_montant(m):
    return f"{m:,}".replace(",", " ")


def fmt_date(d):
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def rendre_canevas(ton, canal, interlocuteur, lignes, num_relance):
    """lignes : liste de (numero_facture, date_echeance, solde, taux)."""
    bloc = []
    for numero_, dt, solde, taux in sorted(lignes, key=lambda x: (x[1], x[0])):
        s = f"- Facture {numero_} : échéance du {fmt_date(dt)}, solde {fmt_montant(solde)} FCFA"
        if taux is not None:
            s += f" (pénalité de retard prévue : {str(taux).replace('.', ',')} % par mois)"
        bloc.append(s)
    total = sum(x[2] for x in lignes)
    return CANEVAS[ton][canal].format(
        salutation=f"Bonjour {interlocuteur}" if interlocuteur else "Bonjour",
        entreprise=ENTREPRISE, bloc_factures="\n".join(bloc),
        total_solde=fmt_montant(total),
        reference_paiement=f"MM-SIM-2026-{num_relance:06d}",
        mention_simulation="(simulation : aucun paiement réel)")


# ----------------------------------------------------------------------------------
# Écriture
# ----------------------------------------------------------------------------------
def ecrire_csv(chemin, colonnes, lignes):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(colonnes)
        for l in lignes:
            w.writerow([("" if l.get(c) is None else l.get(c)) for c in colonnes])


def ecrire_json(chemin, obj):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def lire_csv(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------------
def generer(seed, out):
    rng = random.Random(seed)
    clients, prefs_l = construire_clients()
    prefs = {p["client_id"]: p for p in prefs_l}
    clients_par_id = {c["id"]: c for c in clients}
    F, meta = construire_factures(rng)

    # Identifiants d'échéances et d'accords
    ech_list, ech_par_n = [], {}
    k = 0
    for n in range(1, 121):
        f = F[n]
        ech_par_n[n] = []
        for e in f["ech"]:
            k += 1
            e["id"] = f"ECH-{k:04d}"
            e["facture"] = f["id"]
            ech_list.append(e)
            ech_par_n[n].append(e)
    facture_client = {F[n]["id"]: cid(F[n]["client"]) for n in F}
    fac_par_num = {(cid(F[n]["client"]), F[n]["numero"]): F[n]["id"] for n in F}

    # Paiements et avoirs
    pay, avoirs = planifier_paiements(rng, F, meta)
    # Complément de versements pour approcher les 90 paiements du cahier
    cible = 84
    sup = [n for n in range(27, 39) if n not in TRANCHES and n not in (27, 29, 30, 33, 34)]
    for n in sup:
        if len(pay) >= cible:
            break
        f = F[n]
        existants = [p for p in pay if p["refs"] == [f["numero"]]
                     and p["client"] == cid(f["client"])]
        gros = max(existants, key=lambda p: p["montant"])
        if gros["montant"] >= 1500:
            moitie = arrondi500(gros["montant"] / 2)
            gros["montant"] -= moitie
            pay.append(dict(client=gros["client"], date=gros["date"], montant=moitie,
                            refs=list(gros["refs"])))
    pay.sort(key=lambda p: (p["date"], p["client"] or "", p["montant"], p["refs"]))

    # Modes de paiement : 65 % MM, 20 % virement, 10 % espèces, 5 % chèque
    N = len(pay)
    nb_mm, nb_vir, nb_esp = round(N * 0.65), round(N * 0.20), round(N * 0.10)
    modes = (["MOBILE_MONEY"] * nb_mm + ["VIREMENT"] * nb_vir + ["ESPECES"] * nb_esp)
    modes += ["CHEQUE"] * (N - len(modes))
    rng.shuffle(modes)
    cpt = Counter()
    prefix = {"MOBILE_MONEY": "MM", "VIREMENT": "VIR", "ESPECES": "ESP", "CHEQUE": "CHQ"}
    for i, p in enumerate(pay, 1):
        p["id"] = f"PAY-{i:04d}"
        p["mode"] = modes[i - 1]
        cpt[p["mode"]] += 1
        p["reference"] = f"{prefix[p['mode']]}-SIM-2026-{rng.randrange(100000, 999999):06d}"
    # Références uniques par mode
    vues = set()
    for p in pay:
        while (p["mode"], p["reference"]) in vues:
            p["reference"] = f"{prefix[p['mode']]}-SIM-2026-{rng.randrange(100000, 999999):06d}"
        vues.add((p["mode"], p["reference"]))
    for i, a in enumerate(sorted(avoirs, key=lambda a: (a["date"], a["facture"])), 1):
        a["id"] = f"AVO-{i:04d}"

    def evenements(payments, avoirs_):
        evs = []
        for p in payments:
            evs.append(dict(kind="PAY", id=p["id"], date=p["date"], client=p["client"],
                            montant=p["montant"], refs=p["refs"]))
        for a in avoirs_:
            evs.append(dict(kind="AVO", id=a["id"], date=a["date"], facture=F[a["facture"]]["id"],
                            montant=a["montant"]))
        evs.sort(key=lambda e: (e["date"], e["id"]))
        return evs

    base_aff, restes = affecter(evenements(pay, avoirs), ech_list, fac_par_num, facture_client)

    # Six paiements sans référence indiquée, affectés par ancienneté si le résultat est
    # identique à l'affectation indiquée.
    ref_id = {a["src"]: [] for a in base_aff}
    for a in base_aff:
        ref_id[a["src"]].append((a["ech"], a["montant"]))
    candidats = [p for p in pay if p["client"] and len(p["refs"]) == 1
                 and p["id"] in ref_id]
    rng.shuffle(candidats)
    auto = 0
    for p in candidats:
        if auto >= 6:
            break
        sauve = p["refs"]
        p["refs"] = []
        aff2, _ = affecter(evenements(pay, avoirs), ech_list, fac_par_num, facture_client)
        if sorted((a["src"], a["ech"], a["montant"]) for a in aff2) == \
                sorted((a["src"], a["ech"], a["montant"]) for a in base_aff):
            auto += 1
        else:
            p["refs"] = sauve
    affectations, restes = affecter(evenements(pay, avoirs), ech_list, fac_par_num,
                                    facture_client)
    assert auto == 6, f"seulement {auto} paiements sans référence possibles"

    # Dossiers : accords, contestations, promesses
    accords = {}
    for n, g in meta.items():
        accords[f"ACC-{n - 100:04d}"] = dict(facture=F[n]["id"], statut=g["statut"],
                                             date=g["acc"], nb=3 if g["statut"] == "PROPOSE"
                                             else len([e for e in F[n]["ech"]
                                                       if e["etat"] == "ACTIVE"]))
    contest_def = [
        (95, date(2026, 11, 20), None, "montant non conforme"),
        (96, date(2026, 12, 2), None, "marchandise non livrée"),
        (97, date(2026, 12, 10), None, "doublon de facturation"),
        (98, date(2026, 12, 8), None, "qualité non conforme"),
        (99, date(2026, 11, 27), date(2026, 12, 8), "montant non conforme"),
        (100, date(2026, 12, 3), date(2026, 12, 11), "marchandise non livrée"),
    ]
    contest = []
    for i, (n, ouv, clo, motif) in enumerate(contest_def, 1):
        contest.append(dict(id=f"CTE-{i:04d}", facture=F[n]["id"], ech=None, motif=motif,
                            ouverture=ouv, cloture=clo, n=n))
    promesse_def = [  # n, date promise, statut, montant, création (interne)
        (107, date(2026, 12, 18), "EN_COURS", 150000, date(2026, 12, 4)),
        (108, date(2026, 12, 24), "EN_COURS", None, date(2026, 11, 30)),
        (109, date(2027, 1, 10), "EN_COURS", 120000, date(2026, 12, 8)),
        (110, date(2026, 12, 13), "EN_COURS", None, date(2026, 12, 1)),
        (111, date(2026, 12, 4), "NON_TENUE", None, date(2026, 11, 24)),
        (112, date(2026, 12, 9), "NON_TENUE", 90000, date(2026, 12, 1)),
    ]
    promesses = []
    for i, (n, dt, st, mt, cr) in enumerate(promesse_def, 1):
        promesses.append(dict(id=f"PRO-{i:04d}", client=cid(F[n]["client"]),
                              facture=F[n]["id"], date=dt, montant=mt, statut=st,
                              creation=cr, n=n))

    # État du monde (avant historique)
    et = Etat()
    et.clients, et.prefs = clients_par_id, prefs
    et.inv = {F[n]["id"]: F[n] for n in F}
    et.ech = {e["id"]: dict(id=e["id"], facture=e["facture"], rang=e["rang"], date=e["date"],
                            montant=e["montant"], etat=e["etat"], accord=e["accord"])
              for e in ech_list}
    et.facture_client = facture_client
    et.aff = [dict(a) for a in affectations]
    et.contest = [dict(facture=c["facture"], ech=c["ech"], ouverture=c["ouverture"],
                       cloture=c["cloture"]) for c in contest]
    et.promesses = [dict(facture=p["facture"], date=p["date"], statut=p["statut"])
                    for p in promesses]
    et.accords = {k: dict(facture=v["facture"], statut=v["statut"]) for k, v in accords.items()}
    et.steps, et.envois, et.escalades, et.revues = {}, {}, set(), set()
    et.messages_attente = []

    # Historique des relances (reconstitué comme le ferait le moteur, jusqu'au 14 décembre)
    hist, hist_lignes = construire_historique(F, et, prefs, clients_par_id, contest, promesses,
                                              ech_par_n)
    # L'état initial reflète l'historique chargé
    for r in hist:
        for l in hist_lignes[r["id"]]:
            kind = "SENT" if r["statut"] == "ENVOYEE_SIM" else "ANNULEE"
            et.steps.setdefault(l["echeance_id"], {})[l["etape_echeance"]] = (
                kind, pd(r["date_envoi"]) if r["date_envoi"] else pd(r["date_prevue"]))
        if r["statut"] == "ENVOYEE_SIM":
            et.envois.setdefault((r["client_id"], r["canal"]), []).append(pd(r["date_envoi"]))

    return dict(rng=rng, F=F, meta=meta, clients=clients, prefs_l=prefs_l, prefs=prefs,
                ech_list=ech_list, ech_par_n=ech_par_n, pay=pay, avoirs=avoirs,
                affectations=affectations, restes=restes, accords=accords, contest=contest,
                promesses=promesses, et=et, hist=hist, hist_lignes=hist_lignes,
                facture_client=facture_client, fac_par_num=fac_par_num,
                evenements=evenements)


def construire_historique(F, et, prefs, clients_par_id, contest, promesses, ech_par_n):
    """Relances déjà envoyées avant la date de référence (état initial)."""
    # Fenêtres de pause et arrêts par facture
    pauses = defaultdict(list)
    for c in contest:
        fin = c["cloture"] or D0
        pauses[c["n"]].append((c["ouverture"], plus(fin, -1) if c["cloture"] else D0))
    for p in promesses:
        pauses[p["n"]].append((p["creation"], plus(p["date"], MARGE_PROMESSE)))
    annule = {99: ("R2", "CONTESTATION_OUVERTE")}
    envois_pre = []  # (date, client, canal, [(ech, step)], statut, motif)
    # P déjà dus avant le 15/12 pour les non échues 0041 et 0043
    cibles = sorted(HIST_STRICT | {41, 43})
    for n in cibles:
        f = F[n]
        c = cid(f["client"])
        canal, _ = canal_client(clients_par_id[c], prefs)
        assert canal, n
        for e in ech_par_n[n]:
            if e["etat"] != "ACTIVE":
                continue
            for s in ORDRE:
                if s == "P" and n in range(101, 106):
                    continue
                eff = prochain_ouvre(date_brute(e["date"], s))
                if eff >= D0:
                    break
                if eff < f["em"]:
                    continue
                if any(a <= eff <= b for a, b in pauses[n]):
                    # étape tombant le jour d'ouverture : relance annulée (0099 R2)
                    if n in annule and annule[n][0] == s:
                        envois_pre.append((eff, c, canal, [(e["id"], s)], "ANNULEE",
                                           annule[n][1]))
                        continue
                    # étape sautée par une pause : les suivantes ne sont pas envoyées,
                    # elles reprendront à la planification (jamais R3 directement)
                    break
                if n in annule and annule[n][0] == s:
                    envois_pre.append((eff, c, canal, [(e["id"], s)], "ANNULEE", annule[n][1]))
                    continue
                envois_pre.append((eff, c, canal, [(e["id"], s)], "ENVOYEE_SIM", None))
    # Relance P planifiée puis annulée parce que la facture 0003 a été payée
    f3 = F[3]
    e3 = ech_par_n[3][0]
    p3 = prochain_ouvre(date_brute(e3["date"], "P"))
    envois_pre.append((p3, cid(f3["client"]), canal_client(clients_par_id[cid(f3["client"])],
                                                           prefs)[0],
                       [(e3["id"], "P")], "ANNULEE", "SOLDE_NUL"))
    # Regroupement par (date, client, canal)
    groupes = defaultdict(list)
    for dt, c, canal, lignes, statut, motif in envois_pre:
        groupes[(dt, c, canal, statut, motif)].append(lignes[0])
    rels, _lignes_par = [], {}
    for (dt, c, canal, statut, motif), lignes in sorted(groupes.items(),
                                                        key=lambda x: (x[0][0], x[0][1],
                                                                       x[0][2], x[0][3])):
        rels.append((dt, c, canal, statut, motif, lignes))
    hist, hist_lignes = [], {}
    for i, (dt, c, canal, statut, motif, lignes) in enumerate(rels, 1):
        rid = f"REL-{i:04d}"
        sorted({s for _, s in lignes}, key=lambda s: GRAVITE[s])
        etape = lignes[0][1] if len(lignes) == 1 else "GROUPE"
        ton = max((s for _, s in lignes), key=lambda s: GRAVITE[s])
        # lignes avec solde au moment de l'envoi
        out_l, rendu = [], []
        for ech_id, s in sorted(lignes):
            e = et.ech[ech_id]
            solde = solde_ech(et, ech_id, dt)
            fac = et.inv[e["facture"]]
            out_l.append(dict(relance_id=rid, echeance_id=ech_id, etape_echeance=s,
                              solde_au_moment_de_l_envoi=(solde if statut == "ENVOYEE_SIM"
                                                          else "")))
            rendu.append((fac["numero"], e["date"], solde, fac["taux"]))
        contenu = rendre_canevas(ton, canal, prefs[c]["interlocuteur"], rendu, i)
        cle = f"{c}|{canal}|{'+'.join(sorted(f'{e}:{s}' for e, s in lignes))}|{iso(dt)}"
        hist.append(dict(id=rid, client_id=c, canal=canal, etape=etape, date_prevue=iso(dt),
                         date_envoi=iso(dt) if statut == "ENVOYEE_SIM" else "",
                         statut=statut, motif=motif or "", contenu=contenu,
                         cle_idempotence=cle))
        hist_lignes[rid] = out_l
    return hist, hist_lignes


# ----------------------------------------------------------------------------------
# Vérité terrain
# ----------------------------------------------------------------------------------
def statut_facture(et, fid_, d):
    inv = et.inv[fid_]
    if inv["statut_doc"] == "ANNULEE":
        return "ANNULEE"
    if solde_facture(et, fid_, d) == 0:
        return "SOLDEE"
    if any(c["facture"] == fid_ and c["ouverture"] <= d and (c["cloture"] is None
                                                              or c["cloture"] > d)
           for c in et.contest):
        return "CONTESTEE"
    retard_max = max([retard_ech(et, e["id"], d) for e in et.ech.values()
                      if e["facture"] == fid_ and e["etat"] == "ACTIVE"] or [0])
    if accord_accepte(et, fid_) and retard_max == 0:
        return "COUVERTE_PAR_ECHEANCIER"
    if retard_max > 0:
        return "ECHUE"
    return "NON_ECHUE"


def verites(w, d=D0):
    et = w["et"]
    F = w["F"]
    statuts, soldes = [], []
    for e in sorted(et.ech.values(), key=lambda x: x["id"]):
        aff = sum(a["montant"] for a in et.aff if a["ech"] == e["id"] and a["date"] <= d)
        soldes.append(dict(echeance_id=e["id"], affecte=aff, solde=e["montant"] - aff,
                           retard_jours=retard_ech(et, e["id"], d)))
    st_par_fac = {}
    for n in range(1, 121):
        f = F[n]
        st = statut_facture(et, f["id"], d)
        ech_act = [e for e in et.ech.values() if e["facture"] == f["id"] and e["etat"] == "ACTIVE"]
        affecte = sum(a["montant"] for e in ech_act for a in et.aff
                      if a["ech"] == e["id"] and a["date"] <= d)
        solde = solde_facture(et, f["id"], d)
        statuts.append(dict(facture_id=f["id"], statut=st, solde_facture=solde,
                            partiellement_payee=1 if affecte > 0 and solde > 0 else 0))
        st_par_fac[f["id"]] = st
    # Historique de retard par client : part des factures soldées en retard
    ratio = {}
    for n in range(1, 121):
        f = F[n]
        if st_par_fac[f["id"]] != "SOLDEE":
            continue
        c = cid(f["client"])
        ech_ids = {e["id"]: e for e in et.ech.values() if e["facture"] == f["id"]}
        en_retard = any(a["src"].startswith("PAY-") and a["ech"] in ech_ids
                        and a["date"] > ech_ids[a["ech"]]["date"] for a in et.aff)
        t = ratio.setdefault(c, [0, 0])
        t[0] += 1 if en_retard else 0
        t[1] += 1
    prio = []
    for n in range(1, 121):
        f = F[n]
        if st_par_fac[f["id"]] != "ECHUE":
            continue
        ech_act = [e for e in et.ech.values() if e["facture"] == f["id"] and e["etat"] == "ACTIVE"]
        retards = [(retard_ech(et, e["id"], d), e) for e in ech_act]
        retard_max = max(r for r, _ in retards)
        plus_ancienne = min(e["date"] for r, e in retards if r > 0)
        solde = solde_facture(et, f["id"], d)
        c = cid(f["client"])
        anc = min(Decimal(retard_max) / Decimal(30), Decimal(1)) * Decimal(40)
        mt = min(Decimal(solde) / Decimal(1000000), Decimal(1)) * Decimal(35)
        if c in ratio:
            hist = Decimal(ratio[c][0]) / Decimal(ratio[c][1]) * Decimal(25)
        else:
            hist = Decimal("12.5")
        total = (anc + mt + hist).quantize(Decimal("0.01"), ROUND_HALF_UP)
        q = Decimal("0.01")
        prio.append(dict(facture_id=f["id"], retard_jours=retard_max, solde=solde,
                         points_anciennete=anc.quantize(q, ROUND_HALF_UP),
                         points_solde=mt.quantize(q, ROUND_HALF_UP),
                         points_historique=hist.quantize(q, ROUND_HALF_UP), score=total,
                         _anc=plus_ancienne))
    prio.sort(key=lambda r: (-r["score"], r["_anc"], r["facture_id"]))
    for i, r in enumerate(prio, 1):
        r["rang"] = i
        del r["_anc"]
    return statuts, soldes, prio, st_par_fac


# ----------------------------------------------------------------------------------
# Lot défectueux
# ----------------------------------------------------------------------------------
COL_FAC = ["id", "client_id", "numero", "date_emission", "montant_ttc",
           "conditions_paiement", "taux_penalite_retard", "ref_facture_normalisee",
           "statut_document"]
COL_ECH = ["id", "facture_id", "rang", "date_echeance", "montant_du", "etat", "accord_id"]
COL_CLI = ["id", "raison_sociale", "secteur", "ville", "email", "whatsapp", "actif"]


def ligne_facture(f):
    return dict(id=f["id"], client_id=cid(f["client"]), numero=f["numero"],
                date_emission=iso(f["em"]), montant_ttc=f["montant"],
                conditions_paiement=f["cond"], taux_penalite_retard=f["taux"],
                ref_facture_normalisee=f["refnorm"], statut_document=f["statut_doc"])


def ligne_ech(e):
    return dict(id=e["id"], facture_id=e["facture"], rang=e["rang"],
                date_echeance=iso(e["date"]), montant_du=e["montant"], etat=e["etat"],
                accord_id=e["accord"])


def lot_defectueux(w, out):
    F = w["F"]
    rng = random.Random(20261215 + 7)
    fac, ech, cli = [], [], []

    def ajouter_fac(i, client, numero_, em, montant, cond="30_JOURS", tranches=None):
        row = dict(id=f"FAC-2026-{i}", client_id=client, numero=numero_,
                   date_emission=em, montant_ttc=montant, conditions_paiement=cond,
                   taux_penalite_retard="", ref_facture_normalisee="",
                   statut_document="VALIDEE")
        fac.append(row)
        return row

    def ajouter_ech(i, rang, fid_, dt, montant):
        row = dict(id=f"ECH-{i}-{rang}"[:0] + f"ECH-9{len(ech) + 1:03d}", facture_id=fid_,
                   rang=rang, date_echeance=dt, montant_du=montant, etat="ACTIVE",
                   accord_id="")
        ech.append(row)
        return row

    # Clients du lot
    cli.append(dict(id="CLI-9001", raison_sociale="Sodjinou Équipements SARL",
                    secteur="BTP", ville="Cotonou", email="contact@client-9001.example",
                    whatsapp="+2290100009001", actif=1))
    cli.append(dict(id="CLI-9002", raison_sociale="Boutique Alladatin", secteur="traiteur",
                    ville="Bohicon", email="contact@client-9002.example", whatsapp="",
                    actif=1))
    cli.append(dict(id="CLI-9003", raison_sociale="Atelier Bocco et Fils",
                    secteur="pièces automobiles", ville="Parakou", email="",
                    whatsapp="+22997123", actif=1))
    cli.append(dict(id="CLI-9004", raison_sociale="Papeterie Zossou", secteur="imprimerie",
                    ville="Lokossa", email="contact@client-9004", whatsapp="", actif=1))
    # Huit factures valides
    valides = [("CLI-9001", "2026-11-03", 120000), ("CLI-9001", "2026-11-17", 250000),
               ("CLI-9001", "2026-12-02", 90000), ("CLI-9002", "2026-11-10", 60000),
               ("CLI-9002", "2026-12-07", 175000), (cid(20), "2026-11-25", 45000),
               (cid(25), "2026-12-01", 300000), (cid(25), "2026-12-10", 400000)]
    for k, (c, em, m) in enumerate(valides, 1):
        f = ajouter_fac(9000 + k, c, f"FA-2026-{9000 + k}", em, m)
        dt = iso(pd(em) + timedelta(days=30))
        if k >= 7:
            t1 = m * 30 // 100
            ajouter_ech(0, 1, f["id"], dt, t1)
            ajouter_ech(0, 2, f["id"], iso(pd(em) + timedelta(days=60)), m - t1)
            f["conditions_paiement"] = "TRANCHES"
            ech[-2]["date_echeance"] = iso(pd(em) + timedelta(days=30))
        else:
            ajouter_ech(0, 1, f["id"], dt, m)
    # Treize factures défectueuses
    defauts = []  # (facture row, [échéances], code, fichier du défaut, détail)
    f10 = F[10]
    dup = dict(ligne_facture(f10))
    dup["taux_penalite_retard"] = "" if dup["taux_penalite_retard"] is None \
        else dup["taux_penalite_retard"]
    dup["ref_facture_normalisee"] = dup["ref_facture_normalisee"] or ""
    fac.append(dup)
    de = ligne_ech(w["ech_par_n"][10][0])
    ech.append(de)
    defauts.append((dup, "factures.csv", "DOUBLON_EXACT",
                    f"Ligne identique à la facture {f10['id']} déjà présente."))
    for k, n in enumerate((12, 20), 1):
        fn = F[n]
        f = ajouter_fac(9008 + k, cid(fn["client"]), fn["numero"], "2026-11-20", 130000)
        ajouter_ech(0, 1, f["id"], "2026-12-20", 130000)
        defauts.append((f, "factures.csv", "DOUBLON_NUMERO",
                        f"Le client {cid(fn['client'])} a déjà une facture numéro "
                        f"{fn['numero']} ({fn['id']})."))
    f = ajouter_fac(9011, "", "FA-2026-9011", "2026-11-20", 100000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 100000)
    defauts.append((f, "factures.csv", "CHAMP_OBLIGATOIRE_VIDE",
                    "Le champ client_id est vide."))
    f = ajouter_fac(9012, cid(21), "FA-2026-9012", "", 100000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 100000)
    defauts.append((f, "factures.csv", "CHAMP_OBLIGATOIRE_VIDE",
                    "Le champ date_emission est vide."))
    f = ajouter_fac(9013, cid(22), "FA-2026-9013", "2026-11-20", 0)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 50000)
    defauts.append((f, "factures.csv", "MONTANT_NON_POSITIF",
                    "montant_ttc doit être strictement positif (valeur : 0)."))
    f = ajouter_fac(9014, cid(23), "FA-2026-9014", "2026-11-20", 80000)
    e = ajouter_ech(0, 1, f["id"], "2026-12-20", -80000)
    defauts.append((e, "echeances.csv", "MONTANT_NON_POSITIF",
                    "montant_du doit être strictement positif (valeur : -80000)."))
    f = ajouter_fac(9015, cid(24), "FA-2026-9015", "2026-11-20", 200000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 120000)
    ajouter_ech(0, 2, f["id"], "2027-01-20", 60000)
    defauts.append((f, "factures.csv", "SOMME_ECHEANCES_DIFFERENTE",
                    "La somme des échéances (180000) diffère du montant_ttc (200000)."))
    f = ajouter_fac(9016, cid(26), "FA-2026-9016", "2026-11-20", 150000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 120000)
    defauts.append((f, "factures.csv", "SOMME_ECHEANCES_DIFFERENTE",
                    "La somme des échéances (120000) diffère du montant_ttc (150000)."))
    f = ajouter_fac(9017, "CLI-9999", "FA-2026-9017", "2026-11-20", 100000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 100000)
    defauts.append((f, "factures.csv", "CLIENT_INCONNU",
                    "Le client CLI-9999 est absent du fichier clients et du portefeuille."))
    f = ajouter_fac(9018, cid(29), "FA-2026-9018", "2026-02-30", 100000)
    ajouter_ech(0, 1, f["id"], "2026-12-20", 100000)
    defauts.append((f, "factures.csv", "DATE_INVALIDE",
                    "date_emission 2026-02-30 n'existe pas."))
    f = ajouter_fac(9019, cid(30), "FA-2026-9019", "2026-11-20", 100000)
    e = ajouter_ech(0, 1, f["id"], "15/12/2026", 100000)
    defauts.append((e, "echeances.csv", "DATE_INVALIDE",
                    "date_echeance 15/12/2026 est mal formatée (attendu AAAA-MM-JJ)."))
    f = ajouter_fac(9020, cid(8), "FA-2026-9020", "2026-12-01", 100000)
    e = ajouter_ech(0, 1, f["id"], "2026-11-20", 100000)
    defauts.append((e, "echeances.csv", "ECHEANCE_AVANT_EMISSION",
                    "date_echeance 2026-11-20 est antérieure à date_emission 2026-12-01."))
    # Clients défectueux
    defauts.append((cli[2], "clients.csv", "TELEPHONE_MAL_FORME",
                    "whatsapp +22997123 hors format (+229 suivi de 10 chiffres)."))
    defauts.append((cli[3], "clients.csv", "EMAIL_MAL_FORME",
                    "email contact@client-9004 invalide."))
    # Les identifiants d'échéances sont attribués après mélange stable
    rng.shuffle(fac)
    rng.shuffle(ech)
    for i, e in enumerate([e for e in ech if e is not de], 1):
        e["id"] = f"ECH-9{i:03d}"
    rng.shuffle(cli)
    ligne_de = {}
    for nom, lst in (("factures.csv", fac), ("echeances.csv", ech), ("clients.csv", cli)):
        for i, row in enumerate(lst, 2):
            ligne_de[(nom, id(row))] = i
    rejets = []
    for obj, fichier, code, detail in defauts:
        rejets.append(dict(fichier=fichier, ligne=ligne_de[(fichier, id(obj))],
                           motif_code=code, detail=detail))
    rejets.sort(key=lambda r: (r["fichier"], r["ligne"]))
    d = os.path.join(out, "lot_defectueux")
    ecrire_csv(os.path.join(d, "clients.csv"), COL_CLI, cli)
    ecrire_csv(os.path.join(d, "factures.csv"), COL_FAC, fac)
    ecrire_csv(os.path.join(d, "echeances.csv"), COL_ECH, ech)
    ecrire_csv(os.path.join(d, "rejets_attendus.csv"),
               ["fichier", "ligne", "motif_code", "detail"], rejets)
    return dict(nb_lignes=len(cli) + len(fac), nb_rejets=len(rejets),
                nb_acceptees=len(cli) + len(fac) - len(rejets), rejets=rejets)


# ----------------------------------------------------------------------------------
# Messages clients
# ----------------------------------------------------------------------------------
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def resoudre_date(kind, rec):
    """Convention de la section 10 : date promise à partir du jour de réception."""
    if not kind:
        return None
    if kind == "AUJOURDHUI":
        return rec
    if kind == "DEMAIN":
        return plus(rec, 1)
    if kind.startswith("JOUR:"):
        cible = JOURS.index(kind.split(":")[1])
        delta = (cible - rec.weekday()) % 7 or 7
        return plus(rec, delta)
    if kind.startswith("DANS_N:"):
        return plus(rec, int(kind.split(":")[1]))
    if kind == "LUNDI_PROCHAIN":
        return plus(rec, (7 - rec.weekday()) % 7 or 7)
    if kind.startswith("LE_N:"):
        n = int(kind.split(":")[1])
        d = rec.replace(day=n)
        if d < rec:
            m = 1 if rec.month == 12 else rec.month + 1
            y = rec.year + 1 if rec.month == 12 else rec.year
            d = date(y, m, n)
        return d
    if kind == "FIN_MOIS":
        m = 1 if rec.month == 12 else rec.month + 1
        y = rec.year + 1 if rec.month == 12 else rec.year
        return plus(date(y, m, 1), -1)
    raise ValueError(kind)


QUOTAS_MAIN = {
    "DEV": {"PROMESSE_PAIEMENT": 3, "AUTRE_INCERTAIN": 3, "DEJA_PAYE": 2, "CONTESTATION": 2,
            "DEMANDE_ECHEANCIER": 2, "DEMANDE_DELAI": 2, "DEMANDE_COPIE_FACTURE": 1},
    "TEST": {"PROMESSE_PAIEMENT": 9, "AUTRE_INCERTAIN": 9, "DEJA_PAYE": 7, "CONTESTATION": 7,
             "DEMANDE_ECHEANCIER": 4, "DEMANDE_DELAI": 4, "DEMANDE_COPIE_FACTURE": 5},
}
CONTEXTES_MAIN = {
    "PROMESSE_PAIEMENT": "Le client répond à une relance R{r} sur sa facture échue et "
                         "s'engage à payer à une date qu'il formule à sa façon.",
    "AUTRE_INCERTAIN": "Le client répond à côté du sujet ou de façon ambiguë (aucune "
                       "intention claire de payer, contester ou demander un document).",
    "DEJA_PAYE": "Le client affirme avoir déjà réglé la facture réclamée, avec ou sans "
                 "preuve ni référence.",
    "CONTESTATION": "Le client conteste le montant, la livraison, la qualité ou un "
                    "doublon de facturation.",
    "DEMANDE_ECHEANCIER": "Le client demande à payer en plusieurs tranches.",
    "DEMANDE_DELAI": "Le client demande un délai, avec ou sans date précise.",
    "DEMANDE_COPIE_FACTURE": "Le client réclame la facture, un duplicata ou un relevé, "
                             "sans autre intention.",
}
DIFFS_MAIN = ["NEGATION", "DATE_RELATIVE", "MULTI_INTENTION", "MAUVAISE_REFERENCE", "TIERS",
              "HORS_SUJET_OU_VIDE", "LANGUE_LOCALE", "INJECTION"]


def lier_messages(w, statuts_par_fac, rng):
    """Associe les gabarits figés au portefeuille. Retourne messages, étiquettes, fiches,
    et le dictionnaire des messages réservés aux scénarios."""
    F = w["F"]
    figes = lire_csv(os.path.join(ICI, "messages", "messages_generes_figes.csv"))
    ouvertes = defaultdict(list)
    for n in range(1, 121):
        if statuts_par_fac[F[n]["id"]] in ("ECHUE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER"):
            ouvertes[F[n]["client"]].append(F[n])
    eligibles = sorted(ouvertes)
    cycle = list(eligibles)
    rng.shuffle(cycle)
    numeros_tous = [F[n]["numero"] for n in F]
    msgs, etiq = [], []
    reserves = {"S17": None, "S18": None, "S23": []}
    forces = {}
    # Messages réservés aux scénarios (jeu DEV uniquement)
    dev = [m for m in figes if m["split"] == "DEV"]
    s17 = next(m for m in dev if m["categorie"] == "DEJA_PAYE")
    s18 = next(m for m in dev if m["categorie"] == "AUTRE_INCERTAIN")
    s23 = [m for m in dev if m["categorie"] in ("PROMESSE_PAIEMENT", "CONTESTATION",
                                               "DEMANDE_DELAI", "DEJA_PAYE")
           and m is not s17][:5]
    forces[s17["id"]] = 1
    forces[s18["id"]] = 2
    for m, c in zip(s23, (3, 4, 5, 6, 7)):
        forces[m["id"]] = c
    for i, m in enumerate(figes):
        c = forces.get(m["id"], cycle[i % len(cycle)])
        fac_c = ouvertes[c]
        if m["id"] in forces:
            fac_c = [F[{1: 61, 2: 62, 3: 63, 4: 64, 5: 67, 6: 68, 7: 69}[c]]]
        cible = rng.choice(fac_c)
        mode = m["facture_mode"]
        if m["id"] in forces:
            mode = "EXACTE"
        if mode == "EXACTE":
            citee = cible["numero"]
        elif mode == "MAUVAISE":
            autres = [x for x in numeros_tous if x not in [f["numero"] for f in
                                                           F.values() if f["client"] == c]]
            citee = rng.choice(autres + ["FA-2026-9999"])
        else:
            citee = ""
        jour = pd("2026-12-01") + timedelta(days=rng.randrange(0, 15))
        heure = f"{rng.randrange(7, 20):02d}:{rng.randrange(0, 60):02d}:{rng.randrange(0, 60):02d}"
        rec = f"{iso(jour)}T{heure}+01:00"
        texte = m["texte"].replace("{FACT}", citee or "")
        if mode == "AUCUNE":
            texte = m["texte"].replace(" {FACT}", "")
        dp = resoudre_date(m["date_kind"], jour)
        msgs.append(dict(id=m["id"], client_id=cid(c), canal=m["canal"], date_reception=rec,
                         facture_citee=citee, contenu=texte))
        etiq.append(dict(message_id=m["id"], categorie_principale=m["categorie"],
                         copie_demandee=m["copie_demandee"],
                         date_promise=iso(dp) if dp else "",
                         montant_promis=m["montant_promis"],
                         facture_visee=citee if mode == "EXACTE" else "",
                         difficultes=m["difficultes"], split=m["split"], origine="GENERE",
                         relu="NON"))
    reserves["S17"] = s17["id"]
    reserves["S18"] = s18["id"]
    reserves["S23"] = [m["id"] for m in s23]
    # Fiches de rédaction pour les 60 messages écrits à la main
    fiches, num = [], 341
    clients_cycle = list(eligibles)
    rng.shuffle(clients_cycle)
    ordre_diff = DIFFS_MAIN * 4
    k_diff = 0
    for split in ("DEV", "TEST"):
        for cat, n in QUOTAS_MAIN[split].items():
            for _ in range(n):
                c = clients_cycle[(num - 341) % len(clients_cycle)]
                canal = "WHATSAPP" if (num - 341) % 5 in (0, 1, 2) else "EMAIL"
                difficultes = ""
                if k_diff < 24 and (num - 341) % 5 in (0, 2, 3):
                    difficultes = ordre_diff[k_diff]
                    k_diff += 1
                ctx = CONTEXTES_MAIN[cat].replace("{r}", str(1 + (num % 3)))
                fiches.append(dict(message_id=f"MSG-{num:04d}", client_id=cid(c), canal=canal,
                                   categorie_cible=cat,
                                   contexte=ctx + f" Client {cid(c)}.",
                                   difficultes_a_inclure=difficultes, split=split))
                num += 1
    return msgs, etiq, fiches, reserves


def fusionner_redaction_main(w, msgs, etiq, fiches, statuts_par_fac, seed):
    """Fusionne messages/redaction_main.csv (colonnes : message_id, contenu, copie_demandee,
    date_kind, montant_promis, facture_mode, difficultes). Le client, le canal, la catégorie
    et le jeu (DEV ou TEST) viennent de la fiche ; la date de réception, le numéro de facture
    cité et la date promise sont liés de façon déterministe, comme pour les messages figés."""
    chemin = os.path.join(ICI, "messages", "redaction_main.csv")
    if not os.path.exists(chemin):
        return 0
    F = w["F"]
    lignes = {r["message_id"]: r for r in lire_csv(chemin) if r["contenu"].strip()}
    ouvertes = defaultdict(list)
    for n in range(1, 121):
        if statuts_par_fac[F[n]["id"]] in ("ECHUE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER"):
            ouvertes[F[n]["client"]].append(F[n])
    numeros_tous = [F[n]["numero"] for n in F]
    n_fusion = 0
    for f in fiches:
        r = lignes.get(f["message_id"])
        if r is None:
            continue
        num = int(f["message_id"][4:])
        rng = random.Random(f"{seed}-main-{num}")
        c = int(f["client_id"][4:])
        mode = r["facture_mode"]
        if mode == "EXACTE":
            citee = rng.choice(ouvertes[c])["numero"]
        elif mode == "MAUVAISE":
            propres = {x["numero"] for x in F.values() if x["client"] == c}
            citee = rng.choice([x for x in numeros_tous if x not in propres])
        else:
            citee = ""
        jour = date(2026, 12, 1 + (num * 7) % 15)
        reception = f"{iso(jour)}T{8 + num % 10:02d}:{(num * 7) % 60:02d}:00+01:00"
        dp = resoudre_date(r["date_kind"], jour)
        msgs.append(dict(id=f["message_id"], client_id=f["client_id"], canal=f["canal"],
                         date_reception=reception, facture_citee=citee,
                         contenu=r["contenu"].replace("{FACT}", citee)))
        etiq.append(dict(message_id=f["message_id"], categorie_principale=f["categorie_cible"],
                         copie_demandee=r["copie_demandee"],
                         date_promise=iso(dp) if dp else "", montant_promis=r["montant_promis"],
                         facture_visee=citee if mode == "EXACTE" else "",
                         difficultes=r["difficultes"], split=f["split"], origine="MAIN",
                         relu="NON"))
        n_fusion += 1
    return n_fusion


# ----------------------------------------------------------------------------------
# Scénarios
# ----------------------------------------------------------------------------------
def lignes_pour(rows, ech_ids):
    sel = []
    for r in rows:
        ids = {x.split(":")[0] for x in r["echeances"].split(";") if x}
        if ids & set(ech_ids):
            sel.append(r)
    return sel


def ech_de(w, n, actives=True):
    return [e["id"] for e in w["ech_par_n"][n] if (e["etat"] == "ACTIVE" or not actives)]


def scenarios(w, out, nominal, lot_def, ev, reserves, statuts, sim_rows, det_jour):
    F, et = w["F"], w["et"]
    base_et = et

    def copie():
        return copy.deepcopy(base_et)

    sc = {}
    j1 = [r for r in sim_rows if r["date"] == iso(D0)]
    d1 = det_jour[D0]

    def mini(rows):
        return [dict(date=r["date"], client=r["client"], canal=r["canal"], etape=r["etape"],
                     echeances=r["echeances"], decision=r["decision"], motif=r["motif"])
                for r in rows]

    sc["S01"] = dict(
        titre="Import nominal rejoué deux fois : aucun doublon", date_reference=iso(D0),
        prerequis=["base vide (reset sans chargement)",
                   "accords_echeancier.csv chargé avant l'import (voir QUESTIONS.md)"],
        actions=["POST /api/imports (lot_nominal : clients, preferences_contact, factures, "
                 "echeances)", "POST /api/imports avec les mêmes fichiers"],
        attendu=dict(premiere=dict(statut="TERMINE", clients=30, factures=120,
                                   echeances=nominal["nb_echeances"], rejets=0),
                     seconde=dict(statut="DEJA_IMPORTE", creations=0)))
    sc["S02"] = dict(
        titre="Import avec défauts : rejets motivés", date_reference=iso(D0),
        prerequis=["lot_nominal importé"],
        actions=["POST /api/imports (lot_defectueux)"],
        attendu=dict(nb_lignes=lot_def["nb_lignes"], nb_acceptees=lot_def["nb_acceptees"],
                     nb_rejets=lot_def["nb_rejets"],
                     rejets_attendus="lot_defectueux/rejets_attendus.csv",
                     rejets=lot_def["rejets"]))
    sc["S03"] = dict(
        titre="Soldes, statuts et paiement partiel", date_reference=iso(D0),
        prerequis=["état initial au 2026-12-15"],
        actions=[f"GET /api/factures/{F[n]['id']}" for n in range(87, 95)],
        attendu=[s for s in statuts if 87 <= int(s["facture_id"][-4:]) <= 94])
    sc["S04"] = dict(
        titre="Paiement couvrant plusieurs factures du même client", date_reference=iso(D0),
        prerequis=["état initial"], actions=["POST /api/paiements (paiement_multifactures.csv)"],
        attendu=dict(paiement=ev["multi"]["id"],
                     affectations=[dict(echeance_id=e, mode="INDIQUEE",
                                        montant_affecte=et.ech[e]["montant"])
                                   for n in (73, 74) for e in ech_de(w, n)],
                     factures_soldees=[F[73]["id"], F[74]["id"]], reste_non_affecte=0))
    sc["S05"] = dict(
        titre="Paiement ambigu : non affecté, en revue", date_reference=iso(D0),
        prerequis=["état initial"], actions=["POST /api/paiements (paiement_ambigu.csv)"],
        attendu=dict(paiement=ev["ambigu"]["id"], affectations=[],
                     reste_non_affecte=int(ev["ambigu"]["montant"]),
                     revue=dict(type="PAIEMENT_AMBIGU", objet_type="PAIEMENT",
                                objet_id=ev["ambigu"]["id"])))
    sc["S06"] = dict(
        titre="Paiement rejoué : aucune double comptabilisation", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["POST /api/paiements (paiement_rejoue.csv, copie d'un paiement existant)"],
        attendu=dict(http=200, deja_enregistre=True, nb_paiements_inchange=len(w["pay"]),
                     evenement="PAIEMENT_REJOUE", paiement=ev["rejoue"]["id"]))
    e61 = ech_de(w, 61)[0]
    sc["S07"] = dict(
        titre="Relance annulée : paiement reçu entre la préparation et l'envoi",
        date_reference=iso(D0), prerequis=["état initial"],
        actions=["POST /api/relances/planifier", "POST /api/paiements "
                 "(paiement_entre_preparation_et_envoi.csv)", "POST /api/relances/envoyer"],
        attendu=dict(echeance_id=e61, facture_id=F[61]["id"], etape="R1",
                     statut_final="ANNULEE", motif="SOLDE_NUL", envois_pour_ce_client=0,
                     relance_avant_paiement=mini(lignes_pour(j1, [e61]))))
    simples = [g for g in d1 if g["decision"] == "PREPAREE" and len(g["lignes"]) == 1][:4]
    sc["S08"] = dict(
        titre="Traitements concurrents : une seule action", date_reference=iso(D0),
        prerequis=["relances planifiées au 2026-12-15"],
        actions=["POST /api/relances/planifier", "2 × POST /api/relances/envoyer en parallèle"],
        attendu=dict(relances_verifiees=simples,
                     par_relance=dict(envoyees_sim=1, evenements_envoi=1, envois_simules=1),
                     total_envoyees_ce_jour=len([g for g in d1 if g["decision"] == "PREPAREE"])))
    gros = [g for g in d1 if g["decision"] == "EN_ATTENTE_VALIDATION"]
    sc["S09"] = dict(
        titre="Gros montant : validation humaine avant envoi", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["POST /api/relances/planifier", "POST /api/relances/envoyer",
                 "POST /api/relances/{id}/valider (VALIDATEUR)"],
        attendu=dict(en_attente_validation=gros, nb=len(gros),
                     dont_regroupes=len([g for g in gros if len(g["lignes"]) > 1]),
                     envoi_avant_validation=0, revue_type="GROS_MONTANT",
                     validation_par="VALIDATEUR (un GESTIONNAIRE reçoit 403)"))
    # S10 : contestations
    ouvertes = {F[n]["id"]: ech_de(w, n) for n in (95, 96, 97, 98)}
    et2 = copie()
    et2.contest[1]["cloture"] = D0   # CTE-0002 : FAC-2026-0096, client CLI-0014
    rows2, det2 = jour_sim(et2, D0)
    sc["S10"] = dict(
        titre="Contestation : suspension puis reprise", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["POST /api/relances/planifier",
                 "POST /api/contestations/CTE-0002/cloturer (VALIDATEUR, REJETEE)",
                 "POST /api/relances/planifier le même jour"],
        attendu=dict(suspendues=mini([r for r in j1 if r["motif"] == "SUSPENDU_CONTESTATION"]),
                     contestations_ouvertes=ouvertes,
                     apres_cloture_CTE_0002=mini(lignes_pour(rows2, ech_de(w, 96)))))
    # S11 : promesses
    reprise = copie()
    rows_reprise, _ = simuler(reprise, D0, plus(D0, 1))
    et3 = copie()
    for a in ev["tenue_aff"]:
        et3.aff.append(a)
    rows3, _ = jour_sim(et3, D0)
    promesse_ech = {n: ech_de(w, n) for n in range(107, 113)}
    sc["S11"] = dict(
        titre="Promesse tenue ou non tenue", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["POST /api/relances/planifier", "POST /api/paiements "
                 "(paiement_promesse_tenue.csv)", "avancer d'un jour puis planifier"],
        attendu=dict(
            le_15=mini([r for n in range(107, 113)
                        for r in lignes_pour(j1, promesse_ech[n])]),
            le_16=mini([r for n in range(107, 113)
                        for r in lignes_pour([x for x in rows_reprise
                                              if x["date"] == iso(plus(D0, 1))],
                                             promesse_ech[n])]),
            cas_limite_0110=dict(
                date_promise="2026-12-13", suspendue_le_15=True, suspendue_le_16=False,
                premiere_decision_apres_suspension=mini(sorted(
                    [r for r in lignes_pour(sim_rows, promesse_ech[110])
                     if r["decision"] != "SUSPENDUE"], key=lambda r: r["date"])[:1]),
                note="La suspension court jusqu'au 12-15 inclus ; la reprise du 12-16 peut "
                     "être différée par l'espacement (envoi du 12-15 au même client)."),
            promesse_tenue_apres_paiement=dict(promesse="PRO-0001", statut="TENUE",
                                               relances=mini(lignes_pour(rows3,
                                                                          promesse_ech[107])))))
    ech_tr = [[e["id"] for e in w["ech_par_n"][n] if e["etat"] == "ACTIVE"
               and e["rang"] == 2][0] for n in (102, 103)]
    sc["S12"] = dict(
        titre="Échéancier : relance sur la tranche manquée seulement",
        date_reference=iso(D0), prerequis=["état initial"],
        actions=["POST /api/relances/planifier"],
        attendu=dict(tranches_manquees=[dict(facture_id=F[n]["id"], echeance_id=e,
                                             solde=solde_ech(et, e, D0))
                                        for n, e in zip((102, 103), ech_tr)],
                     relances=mini(lignes_pour(j1, ech_tr))))
    prochain_ouvre(date_brute(w["ech_par_n"][45][0]["date"], "P"))
    sc["S13"] = dict(
        titre="Échéances le même jour : un message regroupé", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["POST /api/relances/planifier le 2026-12-15 puis le 2026-12-16"],
        attendu=dict(
            le_15=mini(lignes_pour(j1, ech_de(w, 39) + ech_de(w, 40))),
            le_16=mini([r for r in sim_rows if r["date"] == iso(plus(D0, 1))
                        and r["client"] == "CLI-0012"
                        and r["decision"] in ("PREPAREE", "ABSORBEE", "EN_ATTENTE_VALIDATION")]),
            note="Le 12-16, R2 de FAC-2026-0082 absorbe le rappel P de FAC-2026-0045."))
    e67 = ech_de(w, 67)
    sc["S14"] = dict(
        titre="Import tardif : R1 puis R2 et R3 espacés", date_reference=iso(D0),
        prerequis=["état initial"],
        actions=["planifier et envoyer chaque jour du 2026-12-15 au 2027-01-05"],
        attendu=dict(facture_id=F[67]["id"], retard_jours_au_15_12=45,
                     decisions=mini(sorted(lignes_pour(sim_rows, e67),
                                           key=lambda r: r["date"]))))
    nonouv = [iso(pd("2026-12-20")), iso(pd("2026-12-25"))]
    sc["S15"] = dict(
        titre="Report d'envoi un dimanche ou un jour férié", date_reference="2026-12-20",
        prerequis=["état initial"],
        actions=["avancer au 2026-12-20, planifier ; au 2026-12-21 ; au 2026-12-25 ; au 2026-12-26"],
        attendu=dict(jours_sans_decision=nonouv,
                     decisions_sur_jours_non_ouvres=[r for r in sim_rows if r["date"] in nonouv],
                     reportees=mini([r for r in sim_rows if r["motif"] ==
                                     "JOUR_NON_OUVRE_REPORTE" and r["date"] in
                                     (iso(pd("2026-12-21")), iso(pd("2026-12-26")))])))
    sc["S16"] = dict(
        titre="Rappel P sauté", date_reference=iso(D0), prerequis=["état initial"],
        actions=["POST /api/relances/planifier"],
        attendu=dict(sautees=mini([r for r in j1 if r["decision"] == "SAUTEE"][:12]),
                     exemples=dict(P_TROP_PROCHE=F[42]["id"], P_APRES_ECHEANCE=F[61]["id"]),
                     nb_P_TROP_PROCHE=len([r for r in j1 if r["motif"] == "P_TROP_PROCHE"]),
                     nb_P_APRES_ECHEANCE=len([r for r in j1 if r["motif"] ==
                                              "P_APRES_ECHEANCE"])))
    sc["S17"] = dict(
        titre="Réponse « déjà payé » : revue, jamais de marquage automatique",
        date_reference=iso(D0), prerequis=["faux LLM : DEJA_PAYE, confiance 0,9"],
        actions=[f"POST /api/messages ({reserves['S17']})",
                 f"POST /api/messages/{reserves['S17']}/classer?synchrone=true"],
        attendu=dict(message=reserves["S17"], client="CLI-0001", facture=F[61]["id"],
                     revue="VERIF_PAIEMENT", statut_message="EN_REVUE",
                     solde_inchange=solde_facture(et, F[61]["id"], D0), paiements_crees=0,
                     relances_suspendues="SUSPENDU_MESSAGE_EN_ATTENTE"))
    sc["S18"] = dict(
        titre="Réponse à faible confiance : revue", date_reference=iso(D0),
        prerequis=["faux LLM : AUTRE_INCERTAIN ou confiance 0,40"],
        actions=[f"POST /api/messages ({reserves['S18']})",
                 f"POST /api/messages/{reserves['S18']}/classer?synchrone=true"],
        attendu=dict(message=reserves["S18"], client="CLI-0002", revue="INCERTAIN",
                     motif="CONFIANCE_FAIBLE", promesses_creees=0, contestations_creees=0,
                     relances_suspendues="pendant la revue"))
    lot = [g for g in d1 if g["decision"] == "PREPAREE"]
    sc["S19"] = dict(
        titre="Reprise après interruption en plein lot", date_reference=iso(D0),
        prerequis=["état initial", "au moins 10 messages éligibles hors validation humaine"],
        actions=["POST /api/relances/planifier",
                 "PUT /api/parametres/simulation_interruption_apres = 5",
                 "POST /api/relances/envoyer (lot INTERROMPU après 5)",
                 "PUT /api/parametres/simulation_interruption_apres = vide",
                 "POST /api/relances/envoyer (reprise)"],
        attendu=dict(relances_a_envoyer=len(lot), apres_interruption=5,
                     apres_reprise=len(lot), doublons=0, relances=lot))
    rev = [r for r in j1 if r["decision"] == "REVUE"]
    sc["S20"] = dict(
        titre="Consentement absent ou canal invalide : revue", date_reference=iso(D0),
        prerequis=["état initial"], actions=["POST /api/relances/planifier"],
        attendu=dict(envois_pour=["CLI-0027", "CLI-0028"],
                     revues=mini([r for r in rev if r["motif"] in
                                  ("CONSENTEMENT_ABSENT", "CANAL_INVALIDE")]), envois=0))
    e84 = ech_de(w, 84)[0]
    et4 = copie()
    r_seq, _ = simuler(et4, D0, plus(D0, 1))
    sc["S21"] = dict(
        titre="Avoir couvrant le solde : relances annulées", date_reference="2026-12-16",
        prerequis=["état initial", "avancer au 2026-12-16"],
        actions=["POST /api/relances/planifier", "POST /api/avoirs (avoir_couvrant.csv)",
                 "POST /api/relances/envoyer"],
        attendu=dict(echeance_id=e84, facture_id=F[84]["id"], etape="R3",
                     relance_planifiee=mini(lignes_pour([r for r in r_seq if r["date"] ==
                                                         iso(plus(D0, 1))], [e84])),
                     solde_apres_avoir=0, statut_facture="SOLDEE",
                     relance_statut_final="ANNULEE", motif="SOLDE_NUL"))
    esc = [r for r in j1 if r["motif"] == "ESCALADE"]
    sc["S22"] = dict(
        titre="Escalade après R3", date_reference=iso(D0), prerequis=["état initial"],
        actions=["POST /api/relances/planifier"],
        attendu=dict(escalades=mini(esc), factures=[F[85]["id"], F[86]["id"]],
                     nouvelles_relances_pour_ces_echeances=0))
    sc["S23"] = dict(
        titre="API du LLM indisponible : messages à classer", date_reference=iso(D0),
        prerequis=["PUT /api/parametres/simulation_llm_indisponible = true"],
        actions=["POST /api/messages × 5", "POST /api/messages/{id}/classer (échec)",
                 "PUT /api/parametres/simulation_llm_indisponible = false",
                 "attendre le worker ou classer"],
        attendu=dict(messages=reserves["S23"], statut_apres_panne="A_CLASSER",
                     relances_suspendues="SUSPENDU_MESSAGE_EN_ATTENTE",
                     reste_du_systeme="calculs, paiements et relances fonctionnent",
                     apres_retablissement="classés"))
    for k, v in sc.items():
        v2 = dict(id=k, **v)
        ecrire_json(os.path.join(out, "verite_terrain", "scenarios", f"{k}.json"), v2)
    return sc


# ----------------------------------------------------------------------------------
# Programme principal (suite)
# ----------------------------------------------------------------------------------
COL_PAY = ["id", "client_id", "date_paiement", "montant", "mode", "reference_externe",
           "source", "statut", "references_indiquees"]


def ligne_paiement(p):
    return dict(id=p["id"], client_id=p["client"] or "", date_paiement=iso(p["date"]),
                montant=p["montant"], mode=p["mode"], reference_externe=p["reference"],
                source="SIMULE", statut="RECU", references_indiquees=";".join(p["refs"]))


def ecrire_tout(w, out, seed):
    F, et = w["F"], w["et"]
    rng = w["rng"]
    nominal = os.path.join(out, "lot_nominal")
    ecrire_csv(os.path.join(nominal, "clients.csv"), COL_CLI, w["clients"])
    ecrire_csv(os.path.join(nominal, "preferences_contact.csv"),
               ["client_id", "canal_prefere", "canaux_autorises", "consentement_relance",
                "interlocuteur"], w["prefs_l"])
    ecrire_csv(os.path.join(nominal, "factures.csv"), COL_FAC,
               [ligne_facture(F[n]) for n in range(1, 121)])
    ecrire_csv(os.path.join(nominal, "echeances.csv"), COL_ECH, [ligne_ech(e) for e in
                                                                 w["ech_list"]])
    ecrire_csv(os.path.join(nominal, "avoirs.csv"),
               ["id", "facture_id", "date", "montant", "motif"],
               [dict(id=a["id"], facture_id=F[a["facture"]]["id"], date=iso(a["date"]),
                     montant=a["montant"], motif=a["motif"])
                for a in sorted(w["avoirs"], key=lambda a: a["id"])])
    ecrire_csv(os.path.join(nominal, "paiements.csv"), COL_PAY,
               [ligne_paiement(p) for p in w["pay"]])
    ecrire_csv(os.path.join(nominal, "jours_feries.csv"), ["date", "libelle"],
               [dict(date=d, libelle=l) for d, l in FERIES])
    # État initial
    ei = os.path.join(out, "etat_initial")
    ecrire_csv(os.path.join(ei, "accords_echeancier.csv"),
               ["id", "facture_id", "date_accord", "statut", "nb_tranches"],
               [dict(id=k, facture_id=v["facture"], date_accord=iso(v["date"]),
                     statut=v["statut"], nb_tranches=v["nb"])
                for k, v in sorted(w["accords"].items())])
    ecrire_csv(os.path.join(ei, "contestations.csv"),
               ["id", "facture_id", "echeance_id", "motif", "message_source_id",
                "date_ouverture", "statut", "date_cloture"],
               [dict(id=c["id"], facture_id=c["facture"], echeance_id="", motif=c["motif"],
                     message_source_id="", date_ouverture=iso(c["ouverture"]),
                     statut="CLOTUREE" if c["cloture"] else "OUVERTE",
                     date_cloture=iso(c["cloture"]) if c["cloture"] else "")
                for c in w["contest"]])
    ecrire_csv(os.path.join(ei, "promesses_paiement.csv"),
               ["id", "client_id", "facture_id", "date_promise", "montant_promis",
                "message_source_id", "statut"],
               [dict(id=p["id"], client_id=p["client"], facture_id=p["facture"],
                     date_promise=iso(p["date"]), montant_promis=p["montant"],
                     message_source_id="", statut=p["statut"]) for p in w["promesses"]])
    ecrire_csv(os.path.join(ei, "relances_historique.csv"),
               ["id", "client_id", "canal", "etape", "date_prevue", "date_envoi", "statut",
                "motif", "contenu", "cle_idempotence"], w["hist"])
    ecrire_csv(os.path.join(ei, "relance_lignes_historique.csv"),
               ["relance_id", "echeance_id", "etape_echeance",
                "solde_au_moment_de_l_envoi"],
               [l for r in w["hist"] for l in w["hist_lignes"][r["id"]]])
    # Vérité terrain
    statuts, soldes, prio, st_par_fac = verites(w)
    vt = os.path.join(out, "verite_terrain")
    ecrire_csv(os.path.join(vt, "statuts_factures.csv"),
               ["facture_id", "statut", "solde_facture", "partiellement_payee"], statuts)
    ecrire_csv(os.path.join(vt, "soldes_echeances.csv"),
               ["echeance_id", "affecte", "solde", "retard_jours"], soldes)
    ecrire_csv(os.path.join(vt, "affectations_attendues.csv"),
               ["paiement_id", "echeance_id", "montant_affecte", "mode"],
               [dict(paiement_id=a["src"], echeance_id=a["ech"], montant_affecte=a["montant"],
                     mode=a["mode"]) for a in w["affectations"]])
    ecrire_csv(os.path.join(vt, "priorisation.csv"),
               ["rang", "facture_id", "retard_jours", "solde", "points_anciennete",
                "points_solde", "points_historique", "score"], prio)
    et_sim = copy.deepcopy(et)
    sim_rows, det_jour = simuler(et_sim, D0, FIN_SIM)
    sim_rows.sort(key=lambda r: (r["date"], r["client"], r["canal"], r["etape"],
                                 r["decision"], r["echeances"]))
    ecrire_csv(os.path.join(vt, "relances_attendues.csv"),
               ["date_simulee", "client_id", "canal", "etape", "echeances", "decision",
                "motif"],
               [dict(date_simulee=r["date"], client_id=r["client"], canal=r["canal"],
                     etape=r["etape"], echeances=r["echeances"], decision=r["decision"],
                     motif=r["motif"]) for r in sim_rows])
    # Lot défectueux
    lot_def = lot_defectueux(w, out)
    # Événements
    ev_dir = os.path.join(out, "evenements")
    N = len(w["pay"])
    c9, c1, c3 = cid(9), cid(1), cid(3)
    multi = dict(id=f"PAY-{N + 1:04d}", client=c9, date=D0, mode="VIREMENT",
                 reference="VIR-SIM-2026-900001", refs=[F[73]["numero"], F[74]["numero"]],
                 montant=F[73]["montant"] + F[74]["montant"])
    ambigu = dict(id=f"PAY-{N + 1:04d}", client=None, date=D0, mode="MOBILE_MONEY",
                  reference="MM-SIM-2026-900002", refs=[], montant=98000)
    entre = dict(id=f"PAY-{N + 1:04d}", client=c1, date=D0, mode="MOBILE_MONEY",
                 reference="MM-SIM-2026-900003", refs=[F[61]["numero"]],
                 montant=F[61]["montant"])
    tenue = dict(id=f"PAY-{N + 1:04d}", client=c3, date=D0, mode="MOBILE_MONEY",
                 reference="MM-SIM-2026-900004", refs=[F[107]["numero"]],
                 montant=F[107]["montant"])
    rejoue = dict(w["pay"][0])
    for nom, p in (("paiement_multifactures", multi), ("paiement_ambigu", ambigu),
                   ("paiement_rejoue", rejoue), ("paiement_entre_preparation_et_envoi", entre),
                   ("paiement_promesse_tenue", tenue)):
        ecrire_csv(os.path.join(ev_dir, nom + ".csv"), COL_PAY, [ligne_paiement(p)])
    e84 = ech_de(w, 84)[0]
    avo = dict(id=f"AVO-{len(w['avoirs']) + 1:04d}", facture_id=F[84]["id"],
               date=iso(plus(D0, 1)), montant=solde_ech(et, e84, D0),
               motif="annulation partielle de prestation")
    ecrire_csv(os.path.join(ev_dir, "avoir_couvrant.csv"),
               ["id", "facture_id", "date", "montant", "motif"], [avo])
    ev = dict(multi=ligne_paiement(multi), ambigu=ligne_paiement(ambigu),
              rejoue=ligne_paiement(rejoue), tenue_aff=[
                  dict(src=tenue["id"], ech=ech_de(w, 107)[0], montant=tenue["montant"],
                       mode="INDIQUEE", date=D0)])
    # Messages
    msgs, etiq, fiches, reserves = lier_messages(w, st_par_fac, rng)
    nb_main = fusionner_redaction_main(w, msgs, etiq, fiches, st_par_fac, seed)
    msgs.sort(key=lambda m: m["id"])
    etiq.sort(key=lambda m: m["message_id"])
    mdir = os.path.join(out, "messages")
    ecrire_csv(os.path.join(mdir, "messages_clients.csv"),
               ["id", "client_id", "canal", "date_reception", "facture_citee", "contenu"], msgs)
    ecrire_csv(os.path.join(mdir, "etiquettes.csv"),
               ["message_id", "categorie_principale", "copie_demandee", "date_promise",
                "montant_promis", "facture_visee", "difficultes", "split", "origine", "relu"],
               etiq)
    ecrire_csv(os.path.join(mdir, "fiches_redaction_main.csv"),
               ["message_id", "client_id", "canal", "categorie_cible", "contexte",
                "difficultes_a_inclure", "split"], fiches)
    # Paramètres
    ecrire_json(os.path.join(out, "params.json"), dict(
        seed=seed, date_reference=iso(D0), seuil_gros_montant=SEUIL_GROS, jours_p=-3,
        jours_r1=1, jours_r2=7, jours_r3=15, espacement_normal_jours=ESPACEMENT_NORMAL,
        espacement_rattrapage_jours=ESPACEMENT_RATTRAPAGE,
        delai_escalade_jours=DELAI_ESCALADE, marge_promesse_jours=MARGE_PROMESSE,
        plafond_promesse_jours=30, plafond_retard_jours=30, plafond_solde=1000000,
        poids_anciennete=40, poids_solde=35, poids_historique=25,
        historique_neutre_points=12.5, rappel_preventif_actif=True,
        nom_entreprise_emettrice=ENTREPRISE, fin_simulation=iso(FIN_SIM)))
    scenarios(w, out, dict(nb_echeances=len(w["ech_list"])), lot_def, ev, reserves, statuts,
              sim_rows, det_jour)
    return dict(statuts=statuts, prio=prio, sim_rows=sim_rows, lot_def=lot_def,
                nb_main=nb_main, st_par_fac=st_par_fac, det_jour=det_jour, msgs=msgs)


def verifier_attendus(w, res):
    """Contrôles internes : un échec signale une incohérence du générateur."""
    erreurs = []
    c = Counter(s["statut"] for s in res["statuts"])
    attendu = {"ANNULEE": 3, "SOLDEE": 38, "CONTESTEE": 4, "COUVERTE_PAR_ECHEANCIER": 3,
               "NON_ECHUE": 25, "ECHUE": 47}
    if dict(c) != attendu:
        erreurs.append(f"statuts {dict(c)} != {attendu}")
    if not 80 <= len(w["pay"]) <= 100:
        erreurs.append(f"{len(w['pay'])} paiements, attendu 80 à 100")
    j1 = [r for r in res["sim_rows"] if r["date"] == iso(D0)]
    d1 = res["det_jour"][D0]
    prep = [g for g in d1 if g["decision"] == "PREPAREE"]
    if len(prep) < 10:
        erreurs.append(f"{len(prep)} messages éligibles le 15/12, attendu au moins 10")
    gros = [g for g in d1 if g["decision"] == "EN_ATTENTE_VALIDATION"]
    if len(gros) != 4 or sorted(len(g["lignes"]) for g in gros) != [1, 1, 1, 2]:
        erreurs.append(f"gros montants : {[(g['client'], len(g['lignes'])) for g in gros]}")
    if not any(g["client"] == "CLI-0024" and g["etape"] == "GROUPE" and g["ton"] == "P"
               for g in d1):
        erreurs.append("0039 et 0040 ne forment pas un message P regroupé le 15/12")
    if not any(r["motif"] == "P_TROP_PROCHE" for r in j1):
        erreurs.append("aucun rappel P sauté pour P_TROP_PROCHE (facture 0042)")
    if len([r for r in j1 if r["motif"] == "ESCALADE"]) != 2:
        erreurs.append("il devrait y avoir 2 escalades le 15/12")
    if len(res["lot_def"]["rejets"]) != 15 or res["lot_def"]["nb_acceptees"] != 10:
        erreurs.append("le lot défectueux ne donne pas 15 rejets et 10 acceptées")
    return erreurs


def hash_fichiers(out):
    h = {}
    for racine, _, fichiers in sorted(os.walk(out)):
        for f in sorted(fichiers):
            chemin = os.path.join(racine, f)
            rel = os.path.relpath(chemin, out)
            if rel.startswith("__pycache__") or "__pycache__" in rel or f in (
                    "README.md",) or f.endswith(".pyc"):
                continue
            with open(chemin, "rb") as fh:
                h[rel] = hashlib.sha256(fh.read()).hexdigest()
    return h


README_TEXTE = """# Jeu de données fictif – recouvrement BWAI 2026

Jeu **entièrement fictif**, déterministe (graine `{seed}`), régénérable en une commande :

```bash
python generate_dataset.py --seed {seed} --out dataset/     # depuis la racine du dépôt
python tests_coherence.py                                   # les 16 contrôles de cohérence
python _composer_messages.py                                # étape distincte : 340 messages figés
```

Date de référence : **2026-12-15** (mardi). Aucun accès réseau, aucune dépendance au-delà de
la bibliothèque standard de Python (3.11 ou plus).

## Contenu

| Dossier | Rôle |
| --- | --- |
| `lot_nominal/` | Portefeuille importé : 30 clients, 120 factures, {nb_ech} échéances, {nb_pay} paiements, 5 avoirs, jours fériés |
| `lot_defectueux/` | 25 unités d'import dont 15 rejets attendus (scénario S02) |
| `etat_initial/` | Dossiers en cours chargés par la réinitialisation : accords, contestations, promesses, {nb_hist} relances historiques |
| `evenements/` | Paiements et avoir à injecter pendant les scénarios (jamais chargés au départ) |
| `messages/` | 340 messages figés et étiquetés, fiches de rédaction des 60 messages à écrire à la main |
| `verite_terrain/` | Résultats attendus (statuts, soldes, affectations, priorisation, relances jour par jour) et 23 scénarios |

## Conventions propres à ce générateur

Le document de données laisse certains formats ouverts. Voici ce que fait ce jeu ; chaque point
est repris dans `docs/QUESTIONS.md` du dépôt.

- **`relances_attendues.csv`** : une ligne par jour ouvré, client et canal où quelque chose est
  décidé, du 2026-12-15 au 2027-01-05, sans événement injecté, gros montants validés et envoyés
  le jour même. La colonne `echeances` liste `ECH-xxxx:étape` séparés par `;` pour les décisions
  `PREPAREE`, `EN_ATTENTE_VALIDATION`, `SAUTEE` et `ABSORBEE` ; elle liste seulement les `ECH-xxxx`
  pour `SUSPENDUE` et `REVUE`. Une relance regroupée a l'étape `GROUPE` (son ton est l'étape la
  plus grave) ; ses lignes moins graves sont répétées en `ABSORBEE`.
- **Suspensions** : une ligne `SUSPENDUE` par jour, client, canal et motif, pour toute échéance
  candidate (ACTIVE, solde positif, facture valide) suspendue, même sans étape due.
- **Revues** : `CONSENTEMENT_ABSENT`, `CANAL_INVALIDE` et `ESCALADE` ne sont écrites qu'à la
  création de l'entrée (une seule fois par client ou par échéance). Une décision reportée par
  l'espacement ne produit aucune ligne : elle réapparaît le jour où elle est envoyée.
- **Motifs** : `GROS_MONTANT` l'emporte, puis `JOUR_NON_OUVRE_REPORTE` (date brute non ouvrée,
  préparée le jour ouvré suivant), puis `REGROUPE`.
- **Consentement** : le contrôle du consentement et du canal précède la création d'un rappel P
  sauté : un client sans consentement n'a aucune relance, pas même `SAUTEE`.
- **`affectations_attendues.csv`** : pour un avoir, la colonne `paiement_id` contient l'identifiant
  `AVO-xxxx` (mode `AUTO_ANCIENNETE`).
- **`priorisation.csv`** : les trois composantes sont arrondies à 2 décimales pour l'affichage ;
  le score est l'arrondi (à la hausse à .5) de la somme non arrondie. Historique : un client est
  « en retard » sur une facture soldée si un **paiement** (pas un avoir) est daté après l'échéance.
- **Lot défectueux** : `nb_lignes` compte les lignes de `clients.csv` et de `factures.csv`
  (25 = 4 + 21) ; les échéances sont validées avec leur facture. Un défaut d'échéance est rapporté
  sur la ligne de `echeances.csv`, un défaut de facture ou de client sur sa propre ligne
  (l'en-tête est la ligne 1). 15 rejets, 10 lignes acceptées.
- **Contestations** : `echeance_id` vide (portent sur la facture entière).
- **Contenu des relances historiques** : canevas de la spécification ; pour le courriel, la ligne
  `Objet : …` ouvre le contenu.
- **Messages** : les 340 messages générés sont figés dans `messages/messages_generes_figes.csv`
  (gabarits liés au portefeuille à la génération). Les 60 messages « écrits à la main »
  (`messages/redaction_main.csv`, colonnes `message_id`, `contenu`, `copie_demandee`, `date_kind`,
  `montant_promis`, `facture_mode`, `difficultes`) suivent les fiches de `fiches_redaction_main.csv`.
  **Faute de temps, ils ont été rédigés par Claude (Anthropic) à la demande de l'équipe, et non
  par des personnes** : c'est une limite pour la valeur de preuve de ce sous-ensemble (voir plus
  bas). Le client, le canal, la catégorie et le jeu viennent de la fiche ; la date de réception,
  le numéro de facture cité et la date promise sont liés de façon déterministe. La colonne `relu`
  vaut `NON` partout : la relecture croisée de 20 % des étiquettes reste à faire par l'équipe.

## Limites connues

- Noms d'entreprises et de personnes inventés : une relecture humaine reste nécessaire pour
  écarter toute ressemblance avec une entreprise réelle.
- Jours fériés : liste partielle (fêtes mobiles islamiques absentes) ; seuls 2026-12-25 et
  2027-01-01 comptent dans la fenêtre simulée.
- Expressions en fon et en yoruba : mots isolés mêlés au français, à faire relire par un
  locuteur avant toute évaluation sérieuse (catégorie `LANGUE_LOCALE`, limite connue).
- Les 400 messages ont été composés par Claude (Anthropic), donc par un modèle différent de
  celui qui classera (Gemini), mais les 340 premiers à partir de phrases-types : leur diversité
  réelle est inférieure à celle de messages saisis par des clients. Les 60 messages « à la main »
  n'ont **pas** été écrits par des humains, contrairement à la précaution du cahier des charges
  contre les scores gonflés : les remplacer par de vrais messages reste souhaitable.

## Empreintes SHA-256

| Fichier | SHA-256 |
| --- | --- |
{hashes}
"""


def ecrire_readme(out, seed, w):
    h = hash_fichiers(out)
    lignes = "\n".join(f"| `{k}` | `{v}` |" for k, v in sorted(h.items())
                       if k.endswith((".csv", ".json", ".py")))
    texte = README_TEXTE.format(seed=seed, nb_ech=len(w["ech_list"]), nb_pay=len(w["pay"]),
                                nb_hist=len(w["hist"]), hashes=lignes)
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(texte)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED_DEFAUT)
    ap.add_argument("--out", default=ICI)
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    w = generer(a.seed, out)
    res = ecrire_tout(w, out, a.seed)
    ecrire_readme(out, a.seed, w)
    erreurs = verifier_attendus(w, res)
    print(f"{len(w['ech_list'])} échéances, {len(w['pay'])} paiements, "
          f"{len(w['avoirs'])} avoirs, {len(w['hist'])} relances historiques, "
          f"{len(res['sim_rows'])} décisions simulées, {len(res['msgs'])} messages")
    print("statuts :", dict(Counter(s["statut"] for s in res["statuts"])))
    for e in erreurs:
        print("ÉCART :", e)
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
