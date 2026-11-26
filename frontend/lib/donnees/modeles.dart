// Les objets tels que le back-end les renvoie (backend/openapi.json et les reponses reelles). Le
// frontend ne calcule rien : soldes, statuts, retards et scores arrivent tout faits. Chaque objet
// garde sa ligne JSON (`j`) et donne des acces nommes : un champ ajoute par le back-end n oblige
// pas a toucher ce fichier.
//
// Les codes (ECHUE, ENVOYEE_SIM, PAIEMENT_AMBIGU…) restent des textes : outils/libelles.dart les
// traduit en mots, et un code inconnu s affiche tel quel au lieu de casser l ecran.

typedef Json = Map<String, dynamic>;

Json json(Object? v) => v is Map ? v.cast<String, dynamic>() : <String, dynamic>{};
List<Json> jsons(Object? v) => [for (final e in (v is List ? v : const [])) json(e)];
int entier(Object? v) => v is int ? v : (v is num ? v.round() : int.tryParse('${v ?? ''}') ?? 0);
double decimal(Object? v) => v is num ? v.toDouble() : double.tryParse('${v ?? ''}') ?? 0;
DateTime? date(Object? v) => v == null ? null : DateTime.tryParse('$v');

/// « 2026-12-15 » : le format des dates de l API.
String iso(DateTime d) => '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

const roleValidateur = 'VALIDATEUR';

class Utilisateur {
  const Utilisateur(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get nom => '${j['nom_affiche'] ?? j['nom_utilisateur'] ?? ''}';
  String get identifiant => '${j['nom_utilisateur'] ?? ''}';
  String get role => '${j['role']}';
  bool get validateur => role == roleValidateur;
}

/// GET /api/contexte.
class Contexte {
  const Contexte(this.j);
  final Json j;
  DateTime get dateReference => date(j['date_reference']) ?? DateTime(2026, 12, 15);
  bool get jourOuvre => j['jour_ouvre'] != false;
  bool get demonstration => j['mode_demonstration'] == true;
}

/// Une ligne de GET /api/priorisation : une facture echue et le detail de son score.
class Priorite {
  const Priorite(this.j);
  final Json j;
  String get factureId => '${j['facture_id']}';
  String get numero => '${j['numero']}';
  String get clientId => '${j['client_id']}';
  int get retard => entier(j['retard_jours']);
  int get solde => entier(j['solde']);
  double get anciennete => decimal(j['points_anciennete']);
  double get pointsSolde => decimal(j['points_solde']);
  double get historique => decimal(j['points_historique']);
  double get score => decimal(j['score']);
  int get rang => entier(j['rang']);
  String? get suspension => j['suspension'] as String?;
}

class Client {
  const Client(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get nom => '${j['raison_sociale'] ?? j['id']}';
  String get secteur => '${j['secteur'] ?? ''}';
  String get ville => '${j['ville'] ?? ''}';
  String? get email => j['email'] as String?;
  String? get whatsapp => j['whatsapp'] as String?;
  int get encours => entier(j['encours']);
  int get nbFacturesOuvertes => entier(j['nb_factures_ouvertes']);
  Json get preferences => json(j['preferences']);
  String get canalPrefere => '${preferences['canal_prefere'] ?? j['canal_prefere'] ?? 'WHATSAPP'}';
  List<String> get canauxAutorises => [for (final c in (preferences['canaux_autorises'] as List? ?? const [])) '$c'];
  bool get consentement => (preferences['consentement_relance'] ?? j['consentement_relance']) != false;
  String? get interlocuteur => preferences['interlocuteur'] as String?;
  List<Facture> get factures => [for (final f in jsons(j['factures'])) Facture(f)];
  List<Relance> get relancesRecentes => [for (final r in jsons(j['relances_recentes'])) Relance(r)];
}

class Echeance {
  const Echeance(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get factureId => '${j['facture_id'] ?? ''}';
  int get rang => entier(j['rang']);
  DateTime get dateEcheance => date(j['date_echeance']) ?? DateTime(2026);
  int get montantDu => entier(j['montant_du']);
  int get affecte => entier(j['affecte']);
  int get solde => entier(j['solde']);
  int get retard => entier(j['retard_jours']);
  bool get remplacee => j['etat'] == 'REMPLACEE';
}

class Facture {
  const Facture(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get numero => '${j['numero'] ?? j['id']}';
  String get clientId => '${j['client_id'] ?? json(j['client'])['id'] ?? ''}';
  String? get clientNom => json(j['client'])['raison_sociale'] as String?;
  DateTime? get dateEmission => date(j['date_emission']);
  int get montantTtc => entier(j['montant_ttc']);
  int get solde => entier(j['solde']);
  int get affecte => entier(j['affecte']);
  String get statut => '${j['statut']}';
  bool get partiellementPayee => j['partiellement_payee'] == true;
  int get retard => entier(j['retard_jours']);
  String? get suspension => j['suspension'] as String?;
  String? get conditions => j['conditions_paiement'] as String?;
  double? get tauxPenalite => (j['taux_penalite_retard'] as num?)?.toDouble();
  List<Echeance> get echeances => [for (final e in jsons(j['echeances'])) Echeance(e)];
  bool get ouverte => statut != 'SOLDEE' && statut != 'ANNULEE';
}

class Paiement {
  const Paiement(this.j);
  final Json j;
  String get id => '${j['id']}';
  String? get clientId => j['client_id'] as String?;
  DateTime? get datePaiement => date(j['date_paiement']);
  int get montant => entier(j['montant']);
  String get mode => '${j['mode']}';
  String? get reference => j['reference_externe'] as String?;
  int get resteNonAffecte => entier(j['reste_non_affecte']);
  List<Json> get affectations => jsons(j['affectations']);
  List<String> get relancesAnnulees => [for (final r in (j['relances_annulees'] as List? ?? const [])) '$r'];
  bool get dejaEnregistre => j['deja_enregistre'] == true;
}

class Relance {
  const Relance(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get clientId => '${j['client_id'] ?? ''}';
  String get canal => '${j['canal'] ?? ''}';
  String get etape => '${j['etape'] ?? ''}';
  DateTime? get datePrevue => date(j['date_prevue']);
  DateTime? get dateEnvoi => date(j['date_envoi']);
  String get statut => '${j['statut']}';
  String? get motif => j['motif'] as String?;
  int get nbLignes => entier(j['nb_lignes']);
  int get totalSolde => entier(j['total_solde']);
  List<Json> get lignes => jsons(j['lignes']);
  String? get apercu => (j['contenu_apercu'] ?? j['contenu']) as String?;
  List<Json> get historique => jsons(j['historique']);
  String? get revueId => j['revue_id'] as String?;
}

/// Un message de la boite d envoi simulee (GET /api/canaux/envois).
class Envoi {
  const Envoi(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get relanceId => '${j['relance_id'] ?? ''}';
  String get clientId => '${j['client_id'] ?? ''}';
  String get canal => '${j['canal'] ?? ''}';
  String get destinataire => '${j['destinataire'] ?? ''}';
  String? get objet => j['objet'] as String?;
  String get contenu => '${j['contenu'] ?? ''}'.replaceAll('\r\n', '\n');
  DateTime? get dateEnvoi => date(j['date_envoi']);
}

class Message {
  const Message(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get clientId => '${j['client_id'] ?? ''}';
  String get canal => '${j['canal'] ?? ''}';
  DateTime? get dateReception => date(j['date_reception']);
  String get contenu => '${j['contenu'] ?? ''}';
  String get statut => '${j['statut_traitement']}';
  String? get categorieIa => j['categorie_ia'] as String?;
  double? get confiance => (j['confiance'] as num?)?.toDouble();
  bool get copieDemandee => j['copie_demandee'] == true || j['copie_demandee'] == 1;
  DateTime? get datePromise => date(j['date_promise_extraite']);
  int? get montantPromis => j['montant_promis'] == null ? null : entier(j['montant_promis']);
  String? get factureCitee => j['facture_citee_id'] as String?;
  String? get justification => j['justification'] as String?;
  String? get motifRevue => j['motif_revue'] as String?;
  String? get modele => j['modele_version'] as String?;
  String? get categorieValidee => j['categorie_validee'] as String?;
  String? get contestationId => j['contestation_id'] as String?;
  bool get aClasser => statut == 'A_CLASSER';
  bool get traite => statut == 'TRAITE';
}

class ElementRevue {
  const ElementRevue(this.j);
  final Json j;
  String get id => '${j['id']}';
  String get type => '${j['type']}';
  String get objetType => '${j['objet_type']}';
  String get objetId => '${j['objet_id']}';
  String? get clientId => j['client_id'] as String?;
  int get priorite => entier(j['priorite']);
  String get statut => '${j['statut']}';
  String? get motif => j['motif'] as String?;
  DateTime? get creeLe => date(j['date_reference_creation'] ?? j['cree_le']);

  /// Dans le detail (GET /api/revue/{id}) : l objet concerne.
  Json get objet => json(j['objet']);

  /// Le back-end reserve ces types au validateur (services/messages.py, resoudre_revue_manuelle).
  bool get reserveAuValidateur => const {'ESCALADE', 'LITIGE', 'GROS_MONTANT', 'DEMANDE_ECHEANCIER'}.contains(type);
}

class Evenement {
  const Evenement(this.j);
  final Json j;
  int get id => entier(j['id']);
  DateTime? get horodatage => date(j['horodatage']);
  DateTime? get dateReference => date(j['date_reference']);
  String get acteur => '${j['acteur_type'] ?? ''}';
  String get type => '${j['type_evenement'] ?? ''}';
  String get objetType => '${j['objet_type'] ?? ''}';
  String get objetId => '${j['objet_id'] ?? ''}';
  String? get correlationId => j['correlation_id'] as String?;
  Object? get avant => j['avant'];
  Object? get apres => j['apres'];
  Object? get details => j['details'];
}

/// GET /api/tableau-de-bord.
class Tableau {
  const Tableau(this.j);
  final Json j;
  Json get encours => json(j['encours']);
  int get encoursTotal => entier(encours['total']);
  int get encoursEchu => entier(encours['echu']);
  int get encoursNonEchu => entier(encours['non_echu']);
  int get nbOuvertes => entier(encours['nb_factures_ouvertes']);
  Map<String, int> get parStatut => {for (final e in json(j['factures_par_statut']).entries) e.key: entier(e.value)};
  Json get retards => json(j['retards']);
  Map<String, int> get relances => {for (final e in json(j['relances']).entries) e.key: entier(e.value)};
  Map<String, int> get suspensions => {for (final e in json(j['actions_suspendues']).entries) e.key: entier(e.value)};
  Json get reglements => json(j['reglements_simules']);
  int get revueOuvertes => entier(json(j['revue'])['total_ouvertes']);
  Map<String, int> get messagesParStatut => {for (final e in json(json(j['messages'])['par_statut']).entries) e.key: entier(e.value)};
  Json get promesses => json(j['promesses']);
}
