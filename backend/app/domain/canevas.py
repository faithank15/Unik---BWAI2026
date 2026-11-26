"""Messages types des relances (spécification, section 14).

Un canevas fixe par étape et par canal ; l'IA n'écrit jamais un message. Variables :
{salutation}, {entreprise}, {bloc_factures}, {total_solde}, {reference_paiement},
{mention_simulation}. La référence de paiement est fictive et signalée comme telle.
"""
import re
from dataclasses import dataclass
from datetime import date

MENTION_SIMULATION = "(simulation : aucun paiement réel)"

CANEVAS: dict[str, dict[str, str]] = {
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


@dataclass(frozen=True)
class LigneMessage:
    numero_facture: str
    date_echeance: date
    solde: int
    taux_penalite: float | None = None


def formater_montant(m: int) -> str:
    """1800000 devient « 1 800 000 »."""
    return f"{m:,}".replace(",", " ")


def formater_date(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def ligne_facture(ligne: LigneMessage) -> str:
    s = (f"- Facture {ligne.numero_facture} : échéance du {formater_date(ligne.date_echeance)}, "
         f"solde {formater_montant(ligne.solde)} FCFA")
    if ligne.taux_penalite is not None:
        taux = str(ligne.taux_penalite).replace(".", ",")
        s += f" (pénalité de retard prévue : {taux} % par mois)"
    return s


def rendre(ton: str, canal: str, interlocuteur: str | None, entreprise: str,
           lignes: list[LigneMessage], reference_paiement: str) -> tuple[str | None, str]:
    """Retourne (objet, contenu). L'objet n'existe que pour le courriel ; le contenu ne
    contient alors que le corps du message."""
    ordonnees = sorted(lignes, key=lambda x: (x.date_echeance, x.numero_facture))
    texte = CANEVAS[ton][canal].format(
        salutation=f"Bonjour {interlocuteur}" if interlocuteur else "Bonjour",
        entreprise=entreprise,
        bloc_factures="\n".join(ligne_facture(x) for x in ordonnees),
        total_solde=formater_montant(sum(x.solde for x in lignes)),
        reference_paiement=reference_paiement, mention_simulation=MENTION_SIMULATION)
    if canal == "EMAIL" and texte.startswith("Objet :"):
        objet, _, corps = texte.partition("\n\n")
        return objet[len("Objet :"):].strip(), corps
    return None, texte


def variables_restantes(texte: str) -> list[str]:
    """Variables {...} oubliées dans un texte rendu (doit être vide)."""
    return re.findall(r"\{[a-z_]+\}", texte)
