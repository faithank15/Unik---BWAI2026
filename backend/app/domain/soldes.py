"""Statut d'une facture (spécification, section 6). Règles pures : les valeurs d'entrée
(solde, retard, dossiers) viennent des vues SQL et des tables de dossiers.

Les règles s'appliquent dans l'ordre et la première qui correspond l'emporte. Une promesse
ou un message en attente ne change pas le statut : ils suspendent les relances sans masquer
l'échéance (le statut reste ECHUE).
"""
from dataclasses import dataclass

ORDRE_STATUTS = ["ANNULEE", "SOLDEE", "CONTESTEE", "COUVERTE_PAR_ECHEANCIER", "ECHUE",
                 "NON_ECHUE"]


@dataclass(frozen=True)
class EntreeStatut:
    statut_document: str          # VALIDEE ou ANNULEE
    solde: int                    # somme des soldes des échéances ACTIVE
    contestation_ouverte: bool
    accord_accepte: bool
    retard_max: int               # plus grand retard des échéances, en jours


def evaluer_statut(e: EntreeStatut) -> tuple[str, list[dict]]:
    """Retourne (statut, règles écartées avec leur motif d'exclusion), ce qui rend le statut
    auditable (explication d'une facture, jalon M4)."""
    regles = [
        ("ANNULEE", e.statut_document == "ANNULEE",
         "Le document n'est pas annulé"),
        ("SOLDEE", e.solde == 0, f"Le solde de la facture est de {e.solde} FCFA"),
        ("CONTESTEE", e.contestation_ouverte, "Aucune contestation ouverte"),
        ("COUVERTE_PAR_ECHEANCIER", e.accord_accepte and e.retard_max == 0,
         "Aucun accord d'échéancier accepté sans tranche échue impayée"),
        ("ECHUE", e.retard_max > 0, "Aucune échéance en retard"),
    ]
    ecartees: list[dict] = []
    for nom, condition, motif_exclusion in regles:
        if condition:
            return nom, ecartees
        ecartees.append({"regle": nom, "motif": motif_exclusion})
    return "NON_ECHUE", ecartees


def partiellement_payee(affecte: int, solde: int) -> bool:
    """Indicateur affiché en plus du statut : montant affecté positif et solde positif."""
    return affecte > 0 and solde > 0
