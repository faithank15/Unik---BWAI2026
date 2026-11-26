// Les codes du back-end en mots francais. A l ecran, jamais « COUVERTE_PAR_ECHEANCIER » : une
// table unique traduit chaque code (regles unk, 11-faktu-metier.md, section 2). Un code inconnu
// (ajoute plus tard par le back-end) s affiche lisiblement au lieu de casser l ecran.
import 'dart:ui' show Color;

import '../theme/jetons.dart';
import 'langue.dart';

/// Un statut a l ecran : toujours un mot et une icone, jamais une couleur seule.
class Apparence {
  const Apparence(this.texte, this.icone, this.couleur, {this.fond, this.barre = false});

  final String texte;
  final String icone;
  final Color couleur;

  /// Le fond de la pastille ; nul : la couleur a 12 %.
  final Color? fond;

  /// Le montant barre (facture annulee).
  final bool barre;
}

/// « SUSPENDU_MESSAGE_EN_ATTENTE » -> « Suspendu message en attente » : le repli lisible.
String lisible(String code) {
  final s = code.replaceAll('_', ' ').toLowerCase();
  return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

Apparence apparenceFacture(String statut, {int retard = 0}) => switch (statut) {
  'SOLDEE' => Apparence(t('Réglée'), 'coche', Couleurs.succes),
  'ECHUE' => Apparence(retard > 0 ? t('En retard · {n} j', {'n': retard}) : t('En retard'), 'horloge', Couleurs.erreur),
  'NON_ECHUE' => Apparence(t('À échéance'), 'calendrier', Couleurs.discret),
  'CONTESTEE' => Apparence(t('Contestée'), 'drapeau', Couleurs.texte, fond: Couleurs.secondaire),
  'COUVERTE_PAR_ECHEANCIER' => Apparence(t('Échéancier en cours'), 'calendrier', Couleurs.ocean),
  'ANNULEE' => Apparence(t('Annulée'), 'fermer', Couleurs.discret, barre: true),
  _ => Apparence(lisible(statut), 'document', Couleurs.discret),
};

Apparence apparenceRelance(String statut) => switch (statut) {
  'PLANIFIEE' => Apparence(t('Préparée'), 'calendrier', Couleurs.ocean),
  'EN_ATTENTE_VALIDATION' => Apparence(t('À valider'), 'cadenas', Couleurs.encreLimonade, fond: Couleurs.limonade),
  'ENVOYEE_SIM' => Apparence(t('Envoyée'), 'envoyer', Couleurs.succes),
  'ANNULEE' => Apparence(t('Annulée'), 'fermer', Couleurs.discret),
  'SAUTEE' => Apparence(t('Sautée'), 'avancer', Couleurs.discret),
  'ABSORBEE' => Apparence(t('Regroupée'), 'collection', Couleurs.discret),
  'REJETEE' => Apparence(t('Rejetée'), 'fermer', Couleurs.erreur),
  _ => Apparence(lisible(statut), 'envoyer', Couleurs.discret),
};

String etape(String e) => switch (e) {
  'P' => t('Rappel avant échéance'),
  'R1' => t('1re relance'),
  'R2' => t('2e relance'),
  'R3' => t('3e relance'),
  'GROUPE' => t('Relance groupée'),
  _ => lisible(e),
};

/// Pourquoi une relance est suspendue, sautee, annulee, reportee ou a valider.
String motif(String? code) => switch (code) {
  null => '',
  'P_TROP_PROCHE' => t('Échéance trop proche : le rappel avant échéance est sauté.'),
  'P_APRES_ECHEANCE' => t('Échéance déjà passée : le rappel avant échéance est sauté.'),
  'SUSPENDU_CONTESTATION' || 'CONTESTATION_OUVERTE' => t('Une contestation est ouverte.'),
  'SUSPENDU_PROMESSE' || 'PROMESSE_EN_COURS' => t('Une promesse de paiement est en cours.'),
  'SUSPENDU_ECHEANCIER' || 'ECHEANCIER_ACCEPTE' => t('Un échéancier accepté est respecté.'),
  'SUSPENDU_MESSAGE_EN_ATTENTE' || 'MESSAGE_EN_ATTENTE' => t('Une réponse du client attend d’être traitée.'),
  'SOLDE_NUL' => t('Le client a payé entre la préparation et l’envoi.'),
  'FACTURE_ANNULEE' => t('La facture est annulée.'),
  'GROS_MONTANT' => t('Gros montant : une validation est nécessaire avant l’envoi.'),
  'REJETEE_PAR_VALIDATEUR' => t('Rejetée par le validateur.'),
  'CANAL_INVALIDE' => t('Le canal de contact n’est pas valide.'),
  'CONSENTEMENT_ABSENT' => t('Le client n’a pas donné son accord pour être relancé.'),
  'JOUR_NON_OUVRE' || 'JOUR_NON_OUVRE_REPORTE' => t('Dimanche ou jour férié : reporté au jour ouvré suivant.'),
  'ESPACEMENT_NON_RESPECTE' => t('Trop tôt après le dernier message : reportée.'),
  'DEJA_TRAITEE' => t('Déjà traitée.'),
  _ => lisible(code),
};

String canal(String c) => switch (c) {
  'WHATSAPP' => 'WhatsApp',
  'EMAIL' => t('Courriel'),
  _ => lisible(c),
};

String iconeCanal(String c) => c == 'EMAIL' ? 'enveloppe' : 'whatsapp';

const modesPaiement = ['MOBILE_MONEY', 'VIREMENT', 'ESPECES', 'CHEQUE'];

String modePaiement(String m) => switch (m) {
  'MOBILE_MONEY' => t('Mobile money'),
  'VIREMENT' => t('Virement'),
  'ESPECES' => t('Espèces'),
  'CHEQUE' => t('Chèque'),
  _ => lisible(m),
};

/// Le debut d une reference fictive, par mode (comme le jeu de donnees : MM-SIM-…).
String prefixeReference(String m) => switch (m) {
  'MOBILE_MONEY' => 'MM-SIM',
  'VIREMENT' => 'VIR-SIM',
  'ESPECES' => 'ESP-SIM',
  _ => 'CHQ-SIM',
};

const categories = ['DEJA_PAYE', 'PROMESSE_PAIEMENT', 'CONTESTATION', 'DEMANDE_ECHEANCIER', 'DEMANDE_DELAI', 'DEMANDE_COPIE_FACTURE', 'AUTRE_INCERTAIN'];

/// Les categories qui portent une date (promesse, delai) : le formulaire la demande.
const categoriesAvecDate = {'PROMESSE_PAIEMENT', 'DEMANDE_DELAI'};

String categorie(String c) => switch (c) {
  'DEJA_PAYE' => t('Dit avoir déjà payé'),
  'PROMESSE_PAIEMENT' => t('Promesse de paiement'),
  'CONTESTATION' => t('Contestation'),
  'DEMANDE_ECHEANCIER' => t('Demande un échéancier'),
  'DEMANDE_DELAI' => t('Demande un délai'),
  'DEMANDE_COPIE_FACTURE' => t('Demande une copie'),
  'AUTRE_INCERTAIN' => t('Autre ou incertain'),
  _ => lisible(c),
};

/// Ce que le back-end fera de la categorie, pour decider en connaissance de cause.
String suiteCategorie(String c) => switch (c) {
  'DEJA_PAYE' => t('Les relances sont suspendues et le paiement est à vérifier. Il n’est jamais marqué payé tout seul.'),
  'PROMESSE_PAIEMENT' => t('Une promesse est créée : les relances s’arrêtent jusqu’à la date promise, plus 2 jours.'),
  'CONTESTATION' => t('Une contestation est ouverte et les relances sont suspendues.'),
  'DEMANDE_ECHEANCIER' => t('Les relances sont suspendues le temps de décider d’un échéancier.'),
  'DEMANDE_DELAI' => t('Avec une date, traitée comme une promesse.'),
  'DEMANDE_COPIE_FACTURE' => t('La copie est à renvoyer. Les relances continuent.'),
  'AUTRE_INCERTAIN' => t('Aucune action automatique.'),
  _ => '',
};

String statutMessage(String s) => switch (s) {
  'A_CLASSER' => t('À classer'),
  'CLASSE' => t('Classé'),
  'EN_REVUE' => t('En revue'),
  'TRAITE' => t('Traité'),
  _ => lisible(s),
};

String typeRevue(String t_) => switch (t_) {
  'GROS_MONTANT' => t('Gros montant'),
  'LITIGE' => t('Contestation'),
  'INCERTAIN' => t('Réponse incertaine'),
  'ESCALADE' => t('Sans suite après la 3e relance'),
  'PAIEMENT_AMBIGU' => t('Paiement à affecter'),
  'CANAL_INVALIDE' => t('Contact invalide'),
  'CONSENTEMENT_ABSENT' => t('Sans accord de relance'),
  'VERIF_PAIEMENT' => t('Paiement à vérifier'),
  'PROMESSE_A_VALIDER' => t('Promesse à valider'),
  'DEMANDE_ECHEANCIER' => t('Demande d’échéancier'),
  'DEMANDE_COPIE' => t('Copie de facture demandée'),
  _ => lisible(t_),
};

String iconeRevue(String t_) => switch (t_) {
  'GROS_MONTANT' => 'cadenas',
  'LITIGE' => 'drapeau',
  'INCERTAIN' => 'aide',
  'ESCALADE' => 'alerte',
  'PAIEMENT_AMBIGU' || 'VERIF_PAIEMENT' => 'piece',
  'CANAL_INVALIDE' || 'CONSENTEMENT_ABSENT' => 'telephone',
  'PROMESSE_A_VALIDER' || 'DEMANDE_ECHEANCIER' => 'calendrier',
  'DEMANDE_COPIE' => 'document',
  _ => 'drapeau',
};

String acteur(String a) => switch (a) {
  'SYSTEME' => t('Système'),
  'IA' => t('IA'),
  'UTILISATEUR' => t('Utilisateur'),
  _ => lisible(a),
};

String role(String r) => switch (r) {
  'GESTIONNAIRE' => t('Gestionnaire'),
  'VALIDATEUR' => t('Validateur'),
  _ => lisible(r),
};

const resolutionsContestation = ['ACCEPTEE', 'REJETEE', 'ABANDONNEE'];

String resolution(String r) => switch (r) {
  'ACCEPTEE' => t('Le client a raison'),
  'REJETEE' => t('La facture est due'),
  'ABANDONNEE' => t('Abandonnée'),
  _ => lisible(r),
};

String statutAccord(String s) => switch (s) {
  'PROPOSE' => t('Proposé'),
  'ACCEPTE' => t('Accepté'),
  'RESPECTE' => t('Respecté'),
  'ROMPU' => t('Rompu'),
  _ => lisible(s),
};

String statutPromesse(String s) => switch (s) {
  'EN_COURS' => t('En cours'),
  'TENUE' => t('Tenue'),
  'NON_TENUE' => t('Non tenue'),
  'ANNULEE' => t('Annulée'),
  _ => lisible(s),
};

/// Les evenements du journal, en mots (le code reste visible en petit pour qui le cherche).
String evenement(String type) => switch (type) {
  'IMPORT_TERMINE' => t('Import terminé'),
  'IMPORT_DEJA_FAIT' => t('Import rejoué, aucun doublon'),
  'PAIEMENT_ENREGISTRE' => t('Paiement enregistré'),
  'PAIEMENT_REJOUE' => t('Paiement rejoué, rien compté deux fois'),
  'PAIEMENT_AFFECTE' => t('Paiement affecté'),
  'PAIEMENT_NON_AFFECTE' => t('Paiement non affecté'),
  'AVOIR_ENREGISTRE' => t('Avoir enregistré'),
  'RELANCE_PLANIFIEE' => t('Relance préparée'),
  'RELANCE_ENVOYEE_SIM' => t('Relance envoyée'),
  'RELANCE_ANNULEE' => t('Relance annulée'),
  'RELANCE_SAUTEE' => t('Relance sautée'),
  'RELANCE_SUSPENDUE' => t('Relance suspendue'),
  'RELANCE_REPORTEE_ESPACEMENT' => t('Relance reportée'),
  'RELANCE_EN_ATTENTE_VALIDATION' => t('Relance à valider'),
  'RELANCE_VALIDEE' => t('Relance validée'),
  'RELANCE_REJETEE' => t('Relance rejetée'),
  'LIGNE_RETIREE' => t('Ligne retirée de la relance'),
  'ESCALADE_CREEE' => t('Escalade'),
  'MESSAGE_RECU' => t('Message reçu'),
  'MESSAGE_CLASSE' => t('Message classé par l’IA'),
  'MESSAGE_A_CLASSER' => t('Message à classer'),
  'MESSAGE_VALIDE' => t('Classement validé'),
  'CLASSIFICATION_REPLI' => t('IA indisponible, message à classer'),
  'CONTESTATION_OUVERTE' => t('Contestation ouverte'),
  'CONTESTATION_CLOTUREE' => t('Contestation close'),
  'PROMESSE_CREEE' => t('Promesse créée'),
  'PROMESSE_TENUE' => t('Promesse tenue'),
  'PROMESSE_ANNULEE' => t('Promesse annulée'),
  'ACCORD_PROPOSE' => t('Échéancier proposé'),
  'ACCORD_ACCEPTE' => t('Échéancier accepté'),
  'ACCORD_REFUSE' => t('Échéancier refusé'),
  'ACCORD_RESPECTE' => t('Échéancier respecté'),
  'REVUE_CREEE' => t('Dossier mis en revue'),
  'REVUE_RESOLUE' => t('Revue résolue'),
  'PREFERENCES_MODIFIEES' => t('Contact modifié'),
  'DATE_REFERENCE_MODIFIEE' => t('Date de référence modifiée'),
  'JOUR_NON_OUVRE' => t('Jour non ouvré'),
  'CONNEXION' => t('Connexion'),
  'CONNEXION_ECHEC' => t('Échec de connexion'),
  'DECONNEXION' => t('Déconnexion'),
  'ACCES_REFUSE' => t('Accès refusé'),
  'REFERENCE_INTROUVABLE' => t('Référence introuvable'),
  'RESET' => t('Données réinitialisées'),
  _ => lisible(type),
};

/// Les rejets d un import (codes du document de donnees), en mots.
String motifRejet(String code) => switch (code) {
  'EMAIL_MAL_FORME' => t('Adresse courriel mal formée'),
  'TELEPHONE_MAL_FORME' => t('Numéro WhatsApp mal formé'),
  'CHAMP_OBLIGATOIRE_MANQUANT' => t('Champ obligatoire manquant'),
  'DOUBLON' || 'DOUBLON_DANS_LOT' => t('Doublon dans le fichier'),
  'IDENTIFIANT_EXISTANT_DIFFERENT' => t('Identifiant déjà connu avec d’autres valeurs'),
  'SOMME_ECHEANCES_DIFFERENTE' => t('La somme des échéances ne fait pas le montant TTC'),
  _ => lisible(code),
};

/// La confiance de l IA, en clair.
String confiance(double? c) {
  if (c == null) return t('Non classé');
  return t('Confiance {n} %', {'n': (c * 100).round()});
}
