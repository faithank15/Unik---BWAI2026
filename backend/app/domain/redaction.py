"""Contrat de rédaction des courriels de relance (extension IA, section 2). Règles pures.

Un courriel se compose de trois zones : ce que le code affiche (salutation, tableau des factures,
moyens de règlement, signature, mention de simulation), ce que le LLM écrit (objet, introduction,
conclusion) et des mentions fixes. Le LLM n'écrit jamais un chiffre, une date, un nom ou une
référence : il écrit des variables d'une liste fermée que le code remplace après validation.
Les règles W1 à W8 décident si une rédaction est acceptée ; sinon le canevas fixe de l'étape
(section 14 de la spécification) sert de repli, et l'envoi n'est jamais bloqué.
"""
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

ETAPES = ("P", "R1", "R2", "R3")
TONS = ("COURTOIS", "NEUTRE", "FERME", "FORMEL")            # fermeté croissante
TON_PAR_ETAPE = {"P": "COURTOIS", "R1": "NEUTRE", "R2": "FERME", "R3": "FORMEL"}
CAS = ("PROMESSE_NON_TENUE", "APRES_PAIEMENT_PARTIEL", "RETARDATAIRE_HABITUEL",
       "PREMIER_RETARD_BON_PAYEUR", "STANDARD")
ANCIENNETES = ("COURT", "MOYEN", "LONG")
ENJEUX = ("NORMAL", "GROS_MONTANT")
CHAMPS = ("objet", "introduction", "conclusion", "ton_applique")
LONGUEURS = {"objet": 70, "introduction": 280, "conclusion": 200}
VARIABLES = ("client", "interlocuteur", "numero_facture", "nb_factures", "montant_total", "solde",
             "montant_paye", "date_echeance", "date_promesse", "date_limite", "jours_retard",
             "entreprise_emettrice")
MOTS_INTERDITS = ("huissier", "poursuite", "tribunal", "saisie", "penalite", "coupure",
                  "reputation", "menace")
MENTION_DEMONSTRATION = "Message de démonstration, aucun envoi réel"
SALUTATION_DEFAUT = "Madame, Monsieur"

RE_VARIABLE = re.compile(r"\{([^{}]*)\}")
RE_ADRESSE = re.compile(r"[\w.+-]+@[\w-]+|https?:|www\.|\b[\w-]+\.(?:com|net|org|fr|bj|io)\b",
                        re.IGNORECASE)
RE_INJECTION = re.compile(
    r"ignor\w*\s+(?:les|toutes|tes|vos)?\s*(?:instructions?|consignes?|regles?)|system\s*prompt|"
    r"\bprompt\b|\binstructions?\b|\bconsignes?\b|assistant|intelligence artificielle|"
    r"modele de langage|\bchatgpt\b|jailbreak|as an ai|oublie\w*\s+(?:tout|les)|```|[<>]")
MOTS_ANGLAIS = {"the", "and", "please", "dear", "regards", "invoice", "payment", "kindly",
                "your", "thank", "you"}


class RedactionInvalide(Exception):
    """Une rédaction viole une règle W1 à W8 : le canevas fixe de l'étape la remplace."""

    def __init__(self, regle: str, detail: str):
        super().__init__(f"{regle} : {detail}")
        self.regle, self.detail = regle, detail


@dataclass(frozen=True)
class Redaction:
    objet: str
    introduction: str
    conclusion: str
    ton_applique: str


# ---- cas, ton et catégories du contexte -------------------------------------------------
def ton_de_l_etape(etape: str) -> str:
    """Ton maximal de l'étape (P courtois, R1 neutre, R2 ferme, R3 formel)."""
    return TON_PAR_ETAPE[etape]


def determiner_cas(promesse_non_tenue: bool, paiement_partiel: bool, nb_retards_passes: int,
                   nb_soldees: int, retards_habituel: int = 2) -> str:
    """Le premier cas qui s'applique l'emporte (section 2.3). « Bon payeur » : au moins une
    facture déjà soldée et aucun retard antérieur."""
    if promesse_non_tenue:
        return "PROMESSE_NON_TENUE"
    if paiement_partiel:
        return "APRES_PAIEMENT_PARTIEL"
    if nb_retards_passes >= retards_habituel:
        return "RETARDATAIRE_HABITUEL"
    if nb_retards_passes == 0 and nb_soldees >= 1:
        return "PREMIER_RETARD_BON_PAYEUR"
    return "STANDARD"


def categorie_anciennete(retard_max_jours: int) -> str:
    return "COURT" if retard_max_jours <= 7 else ("MOYEN" if retard_max_jours <= 21 else "LONG")


def categorie_enjeu(total_solde: int, seuil_gros_montant: int) -> str:
    return "GROS_MONTANT" if total_solde > seuil_gros_montant else "NORMAL"


def cle_cache(cas: str, ton: str, canal: str, nb_factures: str, version: str) -> str:
    """La rédaction dépend du cas, de l'étape (via son ton), du canal, de la version de consigne
    et de la catégorie « une facture / plusieurs » (singulier ou pluriel), jamais du client."""
    return f"{cas}|{ton}|{canal}|{nb_factures}|{version}"


def contexte_llm(*, etape: str, canal: str, cas: str, ton_cible: str, nb_factures: str,
                 anciennete_retard: str, enjeu: str, dernier_echange: str | None,
                 variables_disponibles: list[str]) -> dict:
    """Ce que reçoit le LLM : des catégories calculées par le code, jamais un nom, un montant,
    une date exacte, un numéro de facture ni le texte libre d'un client."""
    return {"etape": etape, "canal": canal, "cas": cas, "ton_cible": ton_cible,
            "nb_factures": nb_factures, "anciennete_retard": anciennete_retard,
            "enjeu": enjeu, "dernier_echange": dernier_echange or "AUCUN",
            "variables_disponibles": variables_disponibles}


# ---- validation W1 à W8 ----------------------------------------------------------------
def _normaliser(texte: str) -> str:
    sans_accent = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return sans_accent.lower()


def valider_redaction(brut: object, ton_plafond: str) -> Redaction:
    """W1 à W8. Lève `RedactionInvalide` avec la règle violée."""
    # W1 : JSON valide, exactement les champs attendus
    if isinstance(brut, str):
        try:
            brut = json.loads(brut)
        except ValueError as e:
            raise RedactionInvalide("W1", "JSON invalide") from e
    if not isinstance(brut, Mapping) or set(brut) != set(CHAMPS):
        raise RedactionInvalide("W1", f"champs attendus exactement : {', '.join(CHAMPS)}")
    if not all(isinstance(brut[c], str) and brut[c].strip() for c in CHAMPS):
        raise RedactionInvalide("W1", "chaque champ est un texte non vide")
    red = Redaction(*(brut[c].strip() for c in CHAMPS))
    textes = {"objet": red.objet, "introduction": red.introduction,
              "conclusion": red.conclusion}
    # W2 : variables de la liste fermée uniquement, accolades équilibrées
    for champ, texte in textes.items():
        for nom in RE_VARIABLE.findall(texte):
            if nom not in VARIABLES:
                raise RedactionInvalide("W2", f"variable refusée dans {champ} : {{{nom}}}")
        if "{" in RE_VARIABLE.sub("", texte) or "}" in RE_VARIABLE.sub("", texte):
            raise RedactionInvalide("W2", f"accolade isolée dans {champ}")
    # W3 : aucun chiffre en dehors des variables (ni date, ni montant)
    for champ, texte in textes.items():
        if re.search(r"\d", RE_VARIABLE.sub("", texte)):
            raise RedactionInvalide("W3", f"chiffre en dehors des variables dans {champ}")
    # W4 : mots interdits
    norme = _normaliser(" ".join(textes.values()))
    for mot in MOTS_INTERDITS:
        if mot in norme:
            raise RedactionInvalide("W4", f"mot interdit : {mot}")
    # W5 : longueurs
    for champ, limite in LONGUEURS.items():
        if len(textes[champ]) > limite:
            raise RedactionInvalide("W5", f"{champ} : {len(textes[champ])} > {limite} caractères")
    # W6 : le ton ne dépasse jamais celui de l'étape
    if red.ton_applique not in TONS:
        raise RedactionInvalide("W6", f"ton inconnu : {red.ton_applique}")
    if TONS.index(red.ton_applique) > TONS.index(ton_plafond):
        raise RedactionInvalide("W6", f"ton {red.ton_applique} au-dessus du plafond {ton_plafond}")
    # W7 : aucune adresse, français seulement
    tout = " ".join(textes.values())
    if RE_ADRESSE.search(tout):
        raise RedactionInvalide("W7", "adresse (courriel, lien ou téléphone) interdite")
    if any(c.isalpha() and not unicodedata.name(c, "").startswith("LATIN") for c in tout):
        raise RedactionInvalide("W7", "caractères hors alphabet latin")
    mots = set(re.findall(r"[a-z']+", _normaliser(tout)))
    if len(mots & MOTS_ANGLAIS) >= 2:
        raise RedactionInvalide("W7", "texte en anglais")
    # W8 : aucune consigne reprise du contexte, aucune formule d'injection
    if RE_INJECTION.search(_normaliser(tout)):
        raise RedactionInvalide("W8", "formule d'injection ou reprise de consigne")
    return red


# ---- assemblage ------------------------------------------------------------------------
def formater_montant(m: int) -> str:
    return f"{m:,}".replace(",", " ")


def formater_date(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def substituer(texte: str, faits: Mapping[str, str]) -> str:
    """Remplace chaque {variable} par sa valeur ; une variable sans valeur refuse la rédaction."""
    def remplacer(m: re.Match) -> str:
        nom = m.group(1)
        if nom not in faits:
            raise RedactionInvalide("W2", f"variable sans valeur dans ce message : {{{nom}}}")
        return faits[nom]
    return RE_VARIABLE.sub(remplacer, texte)


@dataclass(frozen=True)
class LigneCourriel:
    numero_facture: str
    date_emission: date
    date_echeance: date
    jours_retard: int
    solde: int


def tableau_des_factures(lignes: list[LigneCourriel], total: int) -> str:
    ordonnees = sorted(lignes, key=lambda x: (x.date_echeance, x.numero_facture))
    corps = [f"- Facture {x.numero_facture} : émise le {formater_date(x.date_emission)}, "
             f"échéance le {formater_date(x.date_echeance)}, {x.jours_retard} jour(s) de "
             f"retard, reste dû {formater_montant(x.solde)} FCFA" for x in ordonnees]
    return "\n".join(corps + [f"Total restant dû : {formater_montant(total)} FCFA"])


def assembler_courriel(red: Redaction, faits: Mapping[str, str], lignes: list[LigneCourriel],
                       raison_sociale: str, reference_paiement: str, entreprise: str
                       ) -> tuple[str, str]:
    """(objet, corps) : zones du code autour de l'introduction et de la conclusion du LLM."""
    objet = substituer(red.objet, faits)
    introduction = substituer(red.introduction, faits)
    conclusion = substituer(red.conclusion, faits)
    salutation = faits.get("interlocuteur") or SALUTATION_DEFAUT
    total = sum(x.solde for x in lignes)
    corps = (f"Bonjour {salutation},\n{raison_sociale}\n\n{introduction}\n\n"
             f"{tableau_des_factures(lignes, total)}\n\n{conclusion}\n\n"
             f"Référence de paiement : {reference_paiement} (simulation : aucun paiement "
             f"réel).\n\nCordialement,\n{entreprise}, service de recouvrement\n\n"
             f"{MENTION_DEMONSTRATION}")
    return objet, corps
