// Ce que les ecrans lisent, et toutes les routes du back-end, a un seul endroit. On montre ce qu on
// a, puis on rafraichit en douceur (au plus toutes les 30 s, ou juste apres une action) : pas de
// requete a chaque ouverture d ecran (regles unk, 09).
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../outils/api.dart';
import 'modeles.dart';

class Donnees extends ChangeNotifier {
  Donnees._() {
    Api.instance.surSessionExpiree = () => _oublier();
  }
  static final instance = Donnees._();

  final _api = Api.instance;

  Utilisateur? utilisateur;
  Contexte? contexte;
  Tableau? tableau;
  Json? comparaison;
  List<Priorite> priorisation = const [];
  List<ElementRevue> revue = const [];
  List<Message> messagesAClasser = const [];

  /// Les 30 clients, pour mettre un nom sur chaque client_id (les listes n en donnent que l id).
  Map<String, Client> clients = const {};

  String? erreur;
  bool enCours = false;
  DateTime? _dernier;

  bool get validateur => utilisateur?.validateur ?? false;

  /// La date du jour pour Faktu : la date de reference du serveur, jamais l horloge du telephone.
  DateTime get dateReference => contexte?.dateReference ?? DateTime(2026, 12, 15);

  String nomClient(String? id) => id == null ? '' : (clients[id]?.nom ?? id);

  // --- La session ---

  Future<void> reprendreSession() async {
    try {
      final p = await SharedPreferences.getInstance();
      final jeton = p.getString('session.jeton');
      if (jeton == null) return;
      _api.jeton = jeton;
      utilisateur = Utilisateur(json(await _api.lire('/auth/moi')));
    } catch (_) {
      // Jeton expire, ou serveur injoignable : on repasse par la connexion.
      _api.jeton = null;
      utilisateur = null;
    }
  }

  Future<void> connecter(String identifiant, String motDePasse) async {
    final r = json(await _api.envoyer('/auth/login', {'nom_utilisateur': identifiant.trim(), 'mot_de_passe': motDePasse}));
    _api.jeton = '${r['jeton']}';
    utilisateur = Utilisateur(json(r['utilisateur']));
    try {
      (await SharedPreferences.getInstance()).setString('session.jeton', _api.jeton!).ignore();
    } catch (_) {}
    notifyListeners();
    await rafraichir(force: true);
  }

  Future<void> deconnecter() async {
    try {
      await _api.envoyer('/auth/logout');
    } catch (_) {
      // Hors connexion : le jeton expirera seul ; on oublie quand meme la session ici.
    }
    await _oublier();
  }

  Future<void> _oublier() async {
    _api.jeton = null;
    utilisateur = null;
    tableau = null;
    contexte = null;
    comparaison = null;
    priorisation = const [];
    revue = const [];
    messagesAClasser = const [];
    _dernier = null;
    notifyListeners();
    try {
      await (await SharedPreferences.getInstance()).remove('session.jeton');
    } catch (_) {}
  }

  // --- Le chargement ---

  Future<void> rafraichir({bool force = false}) async {
    if (enCours || utilisateur == null) return;
    if (!force && _dernier != null && DateTime.now().difference(_dernier!) < const Duration(seconds: 30)) return;
    enCours = true;
    notifyListeners();
    try {
      final r = await Future.wait([
        _api.lire('/contexte'),
        _api.lire('/tableau-de-bord'),
        _api.liste('/priorisation'),
        _api.liste('/revue', {'statut': 'OUVERTE'}),
        _api.liste('/messages', {'statut_traitement': 'A_CLASSER'}),
        _api.lire('/evaluation/comparaison-reference'),
        if (clients.isEmpty) _api.liste('/clients'),
      ]);
      contexte = Contexte(json(r[0]));
      tableau = Tableau(json(r[1]));
      priorisation = [for (final e in r[2] as List<Json>) Priorite(e)];
      revue = [for (final e in r[3] as List<Json>) ElementRevue(e)];
      messagesAClasser = [for (final e in r[4] as List<Json>) Message(e)];
      comparaison = json(r[5]);
      if (r.length > 6) clients = {for (final e in r[6] as List<Json>) '${e['id']}': Client(e)};
      erreur = null;
      _dernier = DateTime.now();
    } on ApiErreur catch (e) {
      erreur = e.message;
    } catch (_) {
      erreur = 'Impossible de charger les données. Réessayez.';
    } finally {
      enCours = false;
      notifyListeners();
    }
  }

  /// Une action, puis les donnees a jour : l ecran montre la reponse du serveur, jamais une
  /// supposition (regles unk, 11, section 7).
  Future<T> agir<T>(Future<T> Function() action, {bool clientsAussi = false}) async {
    final r = await action();
    if (clientsAussi) clients = const {};
    await rafraichir(force: true);
    return r;
  }

  // --- Les lectures a la demande ---

  Future<Client> client(String id) async => Client(json(await _api.lire('/clients/$id')));
  Future<List<Client>> chercherClients(String q) async => [
    for (final e in await _api.liste('/clients', {'q': q.isEmpty ? null : q})) Client(e),
  ];
  Future<Facture> facture(String id) async => Facture(json(await _api.lire('/factures/$id')));
  Future<Json> explication(String factureId) async => json(await _api.lire('/factures/$factureId/explication'));
  Future<List<Facture>> factures({String? clientId, String? statut, String? q}) async => [
    for (final e in await _api.liste('/factures', {'client_id': clientId, 'statut': statut, 'q': q})) Facture(e),
  ];
  Future<List<Echeance>> echeancesOuvertes(String clientId) async => [
    for (final e in await _api.liste('/echeances', {'client_id': clientId})) Echeance(e),
  ].where((e) => e.solde > 0 && !e.remplacee).toList();
  Future<List<Paiement>> paiements({String? clientId}) async => [
    for (final e in await _api.liste('/paiements', {'client_id': clientId})) Paiement(e),
  ];
  Future<Paiement> paiement(String id) async => Paiement(json(await _api.lire('/paiements/$id')));
  Future<List<Relance>> relances({String? statut, String? clientId}) async => [
    for (final e in await _api.liste('/relances', {'statut': statut, 'client_id': clientId})) Relance(e),
  ];
  Future<Relance> relance(String id) async => Relance(json(await _api.lire('/relances/$id')));
  Future<List<Json>> suspensions() => _api.liste('/relances/suspensions');
  Future<List<Envoi>> envois({String? clientId}) async => [
    for (final e in await _api.liste('/canaux/envois', {'client_id': clientId})) Envoi(e),
  ].reversed.toList();
  Future<List<Message>> messages({String? clientId}) async => [
    for (final e in await _api.liste('/messages', {'client_id': clientId})) Message(e),
  ];
  Future<Message> message(String id) async => Message(json(await _api.lire('/messages/$id')));
  Future<ElementRevue> elementRevue(String id) async => ElementRevue(json(await _api.lire('/revue/$id')));
  Future<List<Json>> contestations({String? factureId, String? statut}) => _api.liste('/contestations', {'facture_id': factureId, 'statut': statut});
  Future<List<Json>> promesses({String? factureId}) => _api.liste('/promesses', {'facture_id': factureId});
  Future<List<Json>> accords({String? factureId}) => _api.liste('/accords', {'facture_id': factureId});
  Future<List<Json>> parametres() async => jsons(json(await _api.lire('/parametres'))['elements']);

  /// Les 200 evenements les plus recents (le journal entier peut compter des milliers de lignes).
  Future<List<Evenement>> journal({String? objetId, String? correlationId, String? type}) async => [
    for (final e in jsons(
      json(
        await _api.lire('/journal', {'objet_id': objetId, 'correlation_id': correlationId, 'type_evenement': type, 'tri': '-id', 'limite': 200}),
      )['elements'],
    ))
      Evenement(e),
  ];

  // --- Les actions (chacune suivie d un rafraichissement) ---

  Future<Json> planifier() => agir(() async => json(await _api.envoyer('/relances/planifier')));
  Future<Json> envoyerRelances() => agir(() async => json(await _api.envoyer('/relances/envoyer')));
  Future<void> validerRelance(String id) => agir(() => _api.envoyer('/relances/$id/valider'));
  Future<void> rejeterRelance(String id) => agir(() => _api.envoyer('/relances/$id/rejeter'));

  Future<Paiement> ajouterPaiement({
    String? clientId,
    required DateTime date,
    required int montant,
    required String mode,
    required String reference,
    List<String> factures = const [],
  }) => agir(
    () async => Paiement(
      json(
        await _api.envoyer('/paiements', {
          'client_id': clientId,
          'date_paiement': iso(date),
          'montant': montant,
          'mode': mode,
          'reference_externe': reference,
          'references_indiquees': factures,
        }),
      ),
    ),
  );

  Future<void> affecterPaiement(String paiementId, Map<String, int> parEcheance) => agir(
    () => _api.envoyer('/paiements/$paiementId/affecter', {
      'affectations': [
        for (final e in parEcheance.entries)
          if (e.value > 0) {'echeance_id': e.key, 'montant': e.value},
      ],
    }),
  );

  Future<void> ajouterAvoir({required String factureId, required DateTime date, required int montant, required String motif}) =>
      agir(() => _api.envoyer('/avoirs', {'facture_id': factureId, 'date': iso(date), 'montant': montant, 'motif': motif}));

  Future<Json> ajouterMessage({required String clientId, required String canal, required String contenu, String? factureCitee}) =>
      agir(() async => json(await _api.envoyer('/messages', {'client_id': clientId, 'canal': canal, 'contenu': contenu, 'facture_citee': factureCitee})));

  Future<void> reclasser(String messageId) => agir(() => _api.envoyer('/messages/$messageId/classer'));

  Future<void> validerCategorie(String messageId, {required String categorie, DateTime? datePromise, int? montant, String? factureId, String? commentaire}) =>
      agir(
        () => _api.envoyer('/messages/$messageId/valider-categorie', {
          'categorie': categorie,
          'date_promise': datePromise == null ? null : iso(datePromise),
          'montant_promis': montant,
          'facture_id': factureId,
          'commentaire': commentaire,
        }),
      );

  Future<void> ouvrirContestation(String factureId, String motif) => agir(() => _api.envoyer('/contestations', {'facture_id': factureId, 'motif': motif}));
  Future<void> cloturerContestation(String id, {required String resolution, required String commentaire}) =>
      agir(() => _api.envoyer('/contestations/$id/cloturer', {'resolution': resolution, 'commentaire': commentaire}));

  Future<void> creerPromesse(String factureId, DateTime datePromise, int? montant) =>
      agir(() => _api.envoyer('/promesses', {'facture_id': factureId, 'date_promise': iso(datePromise), 'montant_promis': montant}));
  Future<void> annulerPromesse(String id) => agir(() => _api.envoyer('/promesses/$id/annuler'));

  Future<void> proposerAccord(String factureId, List<(DateTime, int)> tranches) => agir(
    () => _api.envoyer('/accords', {
      'facture_id': factureId,
      'tranches': [
        for (final (d, m) in tranches) {'date_echeance': iso(d), 'montant': m},
      ],
    }),
  );
  Future<void> accepterAccord(String id) => agir(() => _api.envoyer('/accords/$id/accepter'));
  Future<void> refuserAccord(String id) => agir(() => _api.envoyer('/accords/$id/refuser'));

  Future<void> modifierPreferences(String clientId, Json preferences) =>
      agir(() => _api.envoyer('/clients/$clientId/preferences', preferences, 'PUT'), clientsAussi: true);

  Future<void> resoudreRevue(String id, String decision, {String? commentaire}) =>
      agir(() => _api.envoyer('/revue/$id/resoudre', {'decision': decision, 'commentaire': commentaire}));

  Future<Json> importer(Map<String, (String, List<int>)> fichiers) =>
      agir(() async => json(await _api.envoyerFichiers('/imports', fichiers)), clientsAussi: true);

  Future<void> modifierParametre(String cle, String valeur) => agir(() => _api.envoyer('/parametres/$cle', {'valeur': valeur}, 'PUT'));

  // La demonstration (validateur, si le back-end a DEMO_HOOKS_ENABLED).
  Future<Json> avancer(int jours, {bool executer = true}) =>
      agir(() async => json(await _api.envoyer('/admin/avancer', {'jours': jours, 'executer': executer})));
  Future<void> reinitialiser() => agir(() => _api.envoyer('/admin/reset'), clientsAussi: true);
}
