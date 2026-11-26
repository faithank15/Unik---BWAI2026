"""Un portefeuille simulé d'agence de microcrédit, au format d'import de Faktu.
Chaque prêt est une « facture » remboursée en tranches mensuelles (échéances).
Deux lignes fautives exprès, pour voir le rapport de rejet."""
import csv, sys, os
from datetime import date

sortie = sys.argv[1]
os.makedirs(sortie, exist_ok=True)

emprunteurs = [
    ("Adjoa Houngbo", "commerce de pagnes", "Cotonou", "+2290197110001", "Mme Adjoa Houngbo"),
    ("Kossi Agbéssi", "atelier de couture", "Porto-Novo", "+2290197110002", "M. Kossi Agbéssi"),
    ("Groupement Mivodé", "transformation de manioc", "Bohicon", "+2290197110003", "Mme Rachida Lawani"),
    ("Fatoumata Bio", "vente de céréales", "Parakou", "+2290197110004", "Mme Fatoumata Bio"),
    ("Sèna Dossou", "salon de coiffure", "Abomey-Calavi", "+2290197110005", "Mme Sèna Dossou"),
    ("Coopérative Tonou", "pêche artisanale", "Grand-Popo", "+2290197110006", "M. Hervé Tonou"),
    ("Moïse Ahouansou", "réparation de motos", "Cotonou", "+2290197110007", "M. Moïse Ahouansou"),
    ("Clarisse Zinsou", "restauration", "Ouidah", "+2290197110008", "Mme Clarisse Zinsou"),
    ("Issa Moumouni", "élevage de volailles", "Djougou", "+2290197110009", "M. Issa Moumouni"),
    ("Rosine Kpadé", "boutique de quartier", "Lokossa", "+22997110", "Mme Rosine Kpadé"),  # numéro fautif exprès
]

def mois(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, min(d.day, 28))

# (emprunteur, montant du prêt, date de décaissement, nombre de tranches)
prets = [
    (0, 300000, date(2026, 7, 5), 6),
    (1, 150000, date(2026, 8, 10), 4),
    (2, 900000, date(2026, 6, 15), 9),
    (3, 240000, date(2026, 9, 1), 4),
    (4, 120000, date(2026, 10, 3), 3),
    (5, 600000, date(2026, 5, 20), 10),
    (6, 180000, date(2026, 9, 25), 3),
    (7, 360000, date(2026, 8, 1), 6),
    (8, 450000, date(2026, 7, 12), 6),
    (9, 90000, date(2026, 11, 2), 3),
    (0, 200000, date(2026, 11, 20), 4),
]

with open(f"{sortie}/clients.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["id", "raison_sociale", "secteur", "ville", "email", "whatsapp", "actif"])
    for i, (nom, sect, ville, tel, _) in enumerate(emprunteurs, 1):
        w.writerow([f"CLI-MC{i:03d}", nom, sect, ville, "", tel, 1])

with open(f"{sortie}/preferences_contact.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["client_id", "canal_prefere", "canaux_autorises", "consentement_relance", "interlocuteur"])
    for i, e in enumerate(emprunteurs, 1):
        w.writerow([f"CLI-MC{i:03d}", "WHATSAPP", "WHATSAPP", 1, e[4]])

fac = open(f"{sortie}/factures.csv", "w", newline="", encoding="utf-8")
ech = open(f"{sortie}/echeances.csv", "w", newline="", encoding="utf-8")
wf, we = csv.writer(fac), csv.writer(ech)
wf.writerow(["id", "client_id", "numero", "date_emission", "montant_ttc", "conditions_paiement", "taux_penalite_retard", "ref_facture_normalisee", "statut_document"])
we.writerow(["id", "facture_id", "rang", "date_echeance", "montant_du", "etat", "accord_id"])
n_ech = 0
for k, (e, montant, debut, nb) in enumerate(prets, 1):
    fid = f"FAC-MC-{k:04d}"
    wf.writerow([fid, f"CLI-MC{e+1:03d}", f"PRET-2026-{k:04d}", debut.isoformat(), montant, "TRANCHES", "", "", "VALIDEE"])
    tranche = montant // nb
    for r in range(1, nb + 1):
        du = tranche if r < nb else montant - tranche * (nb - 1)
        if k == 4 and r == nb:
            du -= 10000  # tranches qui ne font pas le montant du prêt : rejet exprès
        n_ech += 1
        we.writerow([f"ECH-MC-{n_ech:04d}", fid, r, mois(debut, r).isoformat(), du, "ACTIVE", ""])
fac.close(); ech.close()
print("ok", len(prets), "prêts,", n_ech, "échéances")
