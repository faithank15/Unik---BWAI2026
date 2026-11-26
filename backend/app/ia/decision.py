"""Décision après classification (spécification, section 9) : action automatique ou revue.

L'IA ne modifie jamais un solde, un paiement ou un statut : elle classe, le code décide. Le
seuil est `seuil_confiance_sensible` pour CONTESTATION et DEJA_PAYE (et les trois catégories qui
passent toujours en revue), `seuil_confiance_prudent` pour PROMESSE_PAIEMENT et DEMANDE_DELAI.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.ia.validation import Resultat

PRUDENTES = ("PROMESSE_PAIEMENT", "DEMANDE_DELAI")
REVUE_PAR_CATEGORIE = {
    "DEJA_PAYE": "VERIF_PAIEMENT", "CONTESTATION": "LITIGE",
    "DEMANDE_ECHEANCIER": "DEMANDE_ECHEANCIER", "DEMANDE_COPIE_FACTURE": "DEMANDE_COPIE",
    "AUTRE_INCERTAIN": "INCERTAIN",
}


@dataclass(frozen=True)
class ParametresDecision:
    seuil_sensible: Decimal = Decimal("0.60")
    seuil_prudent: Decimal = Decimal("0.85")
    plafond_promesse_jours: int = 30


@dataclass(frozen=True)
class Decision:
    decision_ia: str                     # AUTO ou REVUE
    statut_message: str                  # CLASSE ou EN_REVUE
    revues: tuple[tuple[str, str | None], ...] = ()   # (type de revue, motif)
    creer: str | None = None             # PROMESSE ou CONTESTATION
    origine_promesse: str = "PROMESSE"
    motif_revue: str | None = None
    notes: list[str] = field(default_factory=list)


def seuil_de(categorie: str, p: ParametresDecision) -> Decimal:
    return p.seuil_prudent if categorie in PRUDENTES else p.seuil_sensible


def decider(r: Resultat, p: ParametresDecision, facture_identifiable: bool,
            date_reference: date) -> Decision:
    extra = ((("DEMANDE_COPIE", "COPIE_DEMANDEE"),)
             if r.copie_demandee and r.categorie != "DEMANDE_COPIE_FACTURE" else ())
    if r.motif_repli:                                                  # sortie invalide
        return Decision("REVUE", "EN_REVUE", (("INCERTAIN", r.motif_repli),), None,
                        motif_revue=r.motif_repli)
    if Decimal(str(r.confiance)) < seuil_de(r.categorie, p):           # confiance faible
        return Decision("REVUE", "EN_REVUE", (("INCERTAIN", "CONFIANCE_FAIBLE"),) + extra,
                        motif_revue="CONFIANCE_FAIBLE")
    if r.drapeaux:                                                     # V6 ou V7
        return Decision("REVUE", "EN_REVUE", (("INCERTAIN", r.drapeaux[0]),) + extra,
                        motif_revue=r.drapeaux[0])
    cat = r.categorie
    if cat in PRUDENTES:
        origine = "PROMESSE" if cat == "PROMESSE_PAIEMENT" else "DELAI"
        limite = date_reference + timedelta(days=p.plafond_promesse_jours)
        if not facture_identifiable:
            motif = "FACTURE_NON_IDENTIFIABLE"
        elif r.date_promise is None:
            motif = "SANS_DATE"
        elif r.date_promise < date_reference:
            motif = "DATE_PASSEE"
        elif r.date_promise > limite:
            motif = "AU_DELA_DU_PLAFOND"
        else:
            return Decision("AUTO", "CLASSE", extra, "PROMESSE", origine)
        return Decision("REVUE", "EN_REVUE", (("PROMESSE_A_VALIDER", motif),) + extra, None,
                        origine, motif)
    creer = "CONTESTATION" if cat == "CONTESTATION" and facture_identifiable else None
    return Decision("AUTO", "EN_REVUE", ((REVUE_PAR_CATEGORIE[cat], None),) + extra, creer)
