"""Messages types : rendu par instantané, aucune variable restante, références et mention de
simulation toujours présentes, total égal à la somme des soldes."""
from datetime import date

import pytest

from app.domain.canevas import (
    LigneMessage,
    formater_date,
    formater_montant,
    rendre,
    variables_restantes,
)

LIGNES = [LigneMessage("FA-2026-0412", date(2026, 12, 10), 1_200_000),
          LigneMessage("FA-2026-0388", date(2026, 11, 2), 600_000, 1.5)]
REF = "MM-SIM-2026-000141"
ETAPES = ["P", "R1", "R2", "R3"]


def test_formats():
    assert formater_montant(1_800_000) == "1 800 000"
    assert formater_montant(950) == "950"
    assert formater_date(date(2026, 12, 5)) == "05/12/2026"


def test_instantane_r1_whatsapp():
    objet, texte = rendre("R1", "WHATSAPP", "M. Roméo", "Entreprise Démo",
                          [LigneMessage("FA-2026-0412", date(2026, 12, 10), 240_000)], REF)
    assert objet is None
    assert texte == (
        "Bonjour M. Roméo, sauf erreur de notre part, nous n'avons pas encore reçu le règlement "
        "de Entreprise Démo pour :\n"
        "- Facture FA-2026-0412 : échéance du 10/12/2026, solde 240 000 FCFA\n"
        "Référence de paiement : MM-SIM-2026-000141 (simulation : aucun paiement réel).\n"
        "Si vous avez déjà payé, merci de nous l'indiquer.")


def test_instantane_r3_courriel_avec_penalite():
    objet, texte = rendre("R3", "EMAIL", None, "Entreprise Démo", LIGNES, REF)
    assert objet == "Dernier avis avant examen du dossier – Entreprise Démo"
    assert texte.startswith("Bonjour,\n\nNos précédents rappels sont restés sans effet.")
    assert "- Facture FA-2026-0388 : échéance du 02/11/2026, solde 600 000 FCFA " \
           "(pénalité de retard prévue : 1,5 % par mois)" in texte
    assert "- Facture FA-2026-0412 : échéance du 10/12/2026, solde 1 200 000 FCFA\n" in texte
    assert texte.index("FA-2026-0388") < texte.index("FA-2026-0412")  # triées par date
    assert "Total restant dû : 1 800 000 FCFA." in texte
    assert texte.endswith("Cordialement,\nEntreprise Démo")


@pytest.mark.parametrize("etape", ETAPES)
@pytest.mark.parametrize("canal", ["WHATSAPP", "EMAIL"])
def test_controles_sur_chaque_message_rendu(etape, canal):
    objet, texte = rendre(etape, canal, "Mme Inès", "Entreprise Démo", LIGNES, REF)
    complet = (objet or "") + "\n" + texte
    assert variables_restantes(complet) == []
    assert REF in texte and "(simulation : aucun paiement réel)" in texte
    for l_ in LIGNES:
        assert l_.numero_facture in texte
    if canal == "EMAIL":
        assert objet and "Total" in texte and "1 800 000" in texte
    else:
        assert objet is None
    assert texte.count("Facture FA-") == 2
    # la pénalité n'apparaît que pour la facture qui porte un taux
    assert texte.count("pénalité de retard") == 1


def test_une_penalite_n_est_mentionnee_que_si_la_facture_porte_un_taux():
    _, texte = rendre("R1", "WHATSAPP", None, "E", [LIGNES[0]], REF)
    assert "pénalité" not in texte


def test_salutation_sans_interlocuteur():
    _, texte = rendre("P", "WHATSAPP", None, "E", [LIGNES[0]], REF)
    assert texte.startswith("Bonjour, un rappel amical")
