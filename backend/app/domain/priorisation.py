"""Priorisation des factures échues (score sur 100). Heuristique documentée qui organise
le travail humain ; elle ne prédit pas le non-paiement.

  ancienneté = min(retard / plafond_retard, 1) × poids_anciennete        (40, plafond 30 j)
  solde      = min(solde / plafond_solde, 1) × poids_solde                (35, plafond 1 000 000)
  historique = part des factures soldées en retard × poids_historique    (25 ; 12,5 sans historique)

Tout se calcule en Decimal ; arrondi à 2 décimales, à la hausse à .5.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DEUX_DECIMALES = Decimal("0.01")


@dataclass(frozen=True)
class ParametresPriorisation:
    plafond_retard_jours: int = 30
    plafond_solde: int = 1_000_000
    poids_anciennete: int = 40
    poids_solde: int = 35
    poids_historique: int = 25
    historique_neutre_points: Decimal = Decimal("12.5")


@dataclass(frozen=True)
class Score:
    anciennete: Decimal
    montant: Decimal
    historique: Decimal
    total: Decimal

    def affichable(self) -> dict[str, str]:
        q = DEUX_DECIMALES
        return {"points_anciennete": str(self.anciennete.quantize(q, ROUND_HALF_UP)),
                "points_solde": str(self.montant.quantize(q, ROUND_HALF_UP)),
                "points_historique": str(self.historique.quantize(q, ROUND_HALF_UP)),
                "score": str(self.total)}


def score(retard_max: int, solde: int, ratio_historique: Decimal | None,
          p: ParametresPriorisation) -> Score:
    anciennete = min(Decimal(retard_max) / p.plafond_retard_jours, Decimal(1)) \
        * p.poids_anciennete
    montant = min(Decimal(solde) / p.plafond_solde, Decimal(1)) * p.poids_solde
    if ratio_historique is None:
        historique = Decimal(p.historique_neutre_points)
    else:
        historique = Decimal(ratio_historique) * p.poids_historique
    total = (anciennete + montant + historique).quantize(DEUX_DECIMALES, ROUND_HALF_UP)
    return Score(anciennete, montant, historique, total)


def ratio_retard(nb_en_retard: int, nb_soldees: int) -> Decimal | None:
    """Part des factures soldées du client qui l'ont été en retard ; None sans historique."""
    if nb_soldees == 0:
        return None
    return Decimal(nb_en_retard) / Decimal(nb_soldees)


def cle_de_tri(score_total: Decimal, echeance_en_retard_la_plus_ancienne: str,
               facture_id: str) -> tuple:
    """Score décroissant, puis échéance en retard la plus ancienne, puis identifiant."""
    return (-score_total, echeance_en_retard_la_plus_ancienne, facture_id)
