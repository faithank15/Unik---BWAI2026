"""Règle d'affectation d'un paiement ou d'un avoir (spécification, section 6).

1. Références indiquées par le client, dans l'ordre, même client obligatoire ;
2. le reste, par ancienneté, sur les échéances ACTIVE du même client ;
3. jamais plus que le solde d'une échéance ; un reste non affectable demeure non affecté.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Cible:
    echeance_id: str
    date_echeance: str
    solde: int


def trier(cibles: list[Cible]) -> list[Cible]:
    """Par date d'échéance puis identifiant."""
    return sorted(cibles, key=lambda c: (c.date_echeance, c.echeance_id))


def repartir(reste: int, cibles: list[Cible]) -> tuple[list[tuple[str, int]], int]:
    """Affecte `reste` sur les cibles dans l'ordre reçu. Retourne les (échéance, montant)
    non nuls et le nouveau reste. N'écrit rien si le montant est nul."""
    affectations: list[tuple[str, int]] = []
    for c in cibles:
        if reste <= 0:
            break
        m = min(reste, c.solde)
        if m > 0:
            affectations.append((c.echeance_id, m))
            reste -= m
    return affectations, reste
