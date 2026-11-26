"""Règles pures du moteur de relances (spécification, section 7). Aucune base, aucun HTTP.

Calendrier d'une échéance de date D : P = D-3, R1 = D+1, R2 = D+7, R3 = D+15. Une seule étape
est préparée par échéance et par jour : en cas de retard accumulé, la plus ancienne manquante,
jamais R3 directement. Un jour non ouvré (dimanche, férié) reporte l'envoi au jour ouvré suivant.
"""
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.calendrier import prochain_jour_permis

ORDRE = ("P", "R1", "R2", "R3")
GRAVITE = {"R1": 1, "P": 2, "R2": 3, "R3": 4}   # R3 > R2 > P > R1


@dataclass(frozen=True)
class ParamsRelances:
    jours: Mapping[str, int]
    rappel_preventif_actif: bool = True
    espacement_normal: int = 2
    espacement_rattrapage: int = 5
    seuil_gros_montant: int = 500_000
    seuil_espacement_moyen: int = 100_000
    coef_espacement_moyen: int = 15      # en dixièmes : 15 = × 1,5
    coef_espacement_gros: int = 20       # en dixièmes : 20 = × 2
    delai_escalade: int = 5
    marge_promesse: int = 2


@dataclass(frozen=True)
class EtapeTraitee:
    """Une étape déjà mentionnée par une ligne de relance, quel que soit le statut de celle-ci.
    `statut` vaut ENVOYEE, SAUTEE ou AUTRE ; `date_envoi` n'est connue que pour ENVOYEE."""
    statut: str
    date_envoi: date | None = None


@dataclass(frozen=True)
class Candidate:
    etape: str
    date_effective: date
    date_brute: date
    rattrapage: bool


@dataclass(frozen=True)
class ResultatEtape:
    candidate: Candidate | None
    sautees: tuple[tuple[str, str], ...]   # (étape, motif)


def date_brute(date_echeance: date, etape: str, p: ParamsRelances) -> date:
    return date_echeance + timedelta(days=p.jours[etape])


def date_effective(date_echeance: date, etape: str, p: ParamsRelances,
                   feries: Collection[date], evites: Collection[int] = ()) -> date:
    """Date brute reportée au prochain jour ouvré et non évité par le client."""
    return prochain_jour_permis(date_brute(date_echeance, etape, p), feries, evites)


def etape_a_preparer(date_echeance: date, traitees: Mapping[str, EtapeTraitee], ref: date,
                     feries: Collection[date], p: ParamsRelances,
                     p_applicable: bool = True,
                     evites: Collection[int] = ()) -> ResultatEtape:
    """Étape candidate d'une échéance à la date `ref` (section 7.2).

    L'étape candidate est la première étape non traitée, dans l'ordre P, R1, R2, R3, dont la date
    effective est atteinte. Un rappel P non traité dont la date effective est antérieure à `ref`
    ne sera jamais préparé : on le saute (P_APRES_ECHEANCE si l'échéance est passée, sinon
    P_TROP_PROCHE) puis on passe à R1. P n'est jamais préparé pour une facture dont l'accord
    d'échéancier est accepté, ni si le rappel préventif est désactivé.
    """
    sautees: list[tuple[str, str]] = []
    for etape in ORDRE:
        if etape == "P" and not (p_applicable and p.rappel_preventif_actif):
            continue
        if etape in traitees:
            continue
        eff = date_effective(date_echeance, etape, p, feries, evites)
        if etape == "P" and eff < ref:
            sautees.append(("P", "P_APRES_ECHEANCE" if date_echeance < ref else "P_TROP_PROCHE"))
            continue
        if eff <= ref:
            return ResultatEtape(Candidate(etape, eff, date_brute(date_echeance, etape, p),
                                           en_rattrapage(date_echeance, etape, eff, ref,
                                                          traitees, p, feries, evites)),
                                 tuple(sautees))
        break
    return ResultatEtape(None, tuple(sautees))


def en_rattrapage(date_echeance: date, etape: str, eff: date, ref: date,
                   traitees: Mapping[str, EtapeTraitee], p: ParamsRelances,
                   feries: Collection[date], evites: Collection[int] = ()) -> bool:
    """Rattrapage : date effective antérieure à `ref`, ou étape précédente de la même échéance
    envoyée après sa propre date effective."""
    if eff < ref:
        return True
    precedentes = [e for e in ORDRE[:ORDRE.index(etape)]
                   if e in traitees and traitees[e].statut == "ENVOYEE"]
    if not precedentes:
        return False
    prec = precedentes[-1]
    envoi = traitees[prec].date_envoi
    return envoi is not None and envoi > date_effective(date_echeance, prec, p, feries, evites)


def ton(etapes: Collection[str]) -> str:
    """Ton d'un message regroupé : l'étape la plus grave (R3 > R2 > P > R1)."""
    return max(etapes, key=lambda e: GRAVITE[e])


def etape_de_relance(etapes: Collection[str]) -> str:
    """Étape portée par la relance : celle de sa ligne, ou GROUPE s'il y en a plusieurs."""
    liste = list(etapes)
    return liste[0] if len(liste) == 1 else "GROUPE"


def lignes_absorbees(etapes_par_echeance: Mapping[str, str]) -> set[str]:
    """Échéances d'un message regroupé dont l'étape est moins grave que son ton."""
    if len(etapes_par_echeance) < 2:
        return set()
    t = ton(list(etapes_par_echeance.values()))
    return {e for e, s in etapes_par_echeance.items() if GRAVITE[s] < GRAVITE[t]}


def coefficient_espacement(total: int, p: ParamsRelances) -> int:
    """Coefficient (en dixièmes) selon le montant total du message : × 1 jusqu'au seuil moyen,
    × 1,5 jusqu'au seuil de gros montant inclus, × 2 au-delà (extension IA, section 3.1)."""
    if total > p.seuil_gros_montant:
        return p.coef_espacement_gros
    if total > p.seuil_espacement_moyen:
        return p.coef_espacement_moyen
    return 10


def ecart_minimal(au_moins_un_rattrapage: bool, p: ParamsRelances, total: int = 0) -> int:
    """Espacement effectif en jours : espacement standard (normal ou rattrapage) multiplié par
    le coefficient du montant, arrondi au jour entier supérieur. Le délai d'escalade après R3
    ne varie pas."""
    base = p.espacement_rattrapage if au_moins_un_rattrapage else p.espacement_normal
    return -(-base * coefficient_espacement(total, p) // 10)


def espacement_respecte(ref: date, dernier_envoi: date | None, ecart: int) -> bool:
    return dernier_envoi is None or (ref - dernier_envoi).days >= ecart


def motif_de_planification(total_solde: int, nb_lignes: int, report: bool,
                           p: ParamsRelances) -> str | None:
    """Motif porté par une relance préparée : GROS_MONTANT, puis JOUR_NON_OUVRE_REPORTE
    (date brute non ouvrée préparée le jour ouvré suivant), puis REGROUPE."""
    if total_solde > p.seuil_gros_montant:
        return "GROS_MONTANT"
    if report:
        return "JOUR_NON_OUVRE_REPORTE"
    if nb_lignes > 1:
        return "REGROUPE"
    return None


def cle_idempotence(client_id: str, canal: str, lignes: Collection[tuple[str, str]],
                    date_prevue: date) -> str:
    """client|canal|échéance:étape triées|date. Replanifier le même jour ne crée rien."""
    corps = "+".join(sorted(f"{e}:{s}" for e, s in lignes))
    return f"{client_id}|{canal}|{corps}|{date_prevue.isoformat()}"


def escalade_due(date_r3_envoyee: date | None, ref: date, p: ParamsRelances) -> bool:
    """Escalade : R3 envoyée depuis au moins `delai_escalade` jours."""
    return date_r3_envoyee is not None and (ref - date_r3_envoyee).days >= p.delai_escalade


MOTIFS_SUSPENSION_VERS_ANNULATION = {
    "SUSPENDU_CONTESTATION": "CONTESTATION_OUVERTE",
    "SUSPENDU_PROMESSE": "PROMESSE_EN_COURS",
    "SUSPENDU_ECHEANCIER": "ECHEANCIER_ACCEPTE",
    "SUSPENDU_MESSAGE_EN_ATTENTE": "MESSAGE_EN_ATTENTE",
}


def choisir_canal(canal_prefere: str | None, canaux_autorises: Collection[str],
                  consentement: bool | None, email: str | None,
                  whatsapp: str | None) -> tuple[str | None, str | None]:
    """Canal d'envoi, ou (None, motif de revue). Le canal est le canal préféré s'il est autorisé
    et que le client a la coordonnée correspondante, sinon l'autre canal autorisé qui remplit
    cette condition. Un client sans préférences est considéré sans consentement."""
    if not consentement:
        return None, "CONSENTEMENT_ABSENT"

    def valide(canal: str) -> bool:
        return canal in canaux_autorises and bool(email if canal == "EMAIL" else whatsapp)
    ordre = ([canal_prefere] if canal_prefere else []) + [
        c for c in ("WHATSAPP", "EMAIL") if c != canal_prefere]
    for canal in ordre:
        if valide(canal):
            return canal, None
    return None, "CANAL_INVALIDE"
