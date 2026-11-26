// La racine de Faktu : le theme (qui suit les reglages et le telephone), les routes, et la
// barre d onglets. Reprise de la racine de Discover.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:go_router/go_router.dart';

import 'donnees/affichage.dart';
import 'donnees/donnees.dart';
import 'ecrans/a_revoir.dart';
import 'ecrans/a_traiter.dart';
import 'ecrans/accueil.dart';
import 'ecrans/compte.dart';
import 'ecrans/connexion.dart';
import 'ecrans/facture.dart';
import 'ecrans/fiche_client.dart';
import 'ecrans/journal.dart';
import 'ecrans/redactions.dart';
import 'ecrans/relances.dart';
import 'outils/sobriete.dart';
import 'theme/defilement.dart';
import 'theme/jetons.dart';
import 'theme/theme.dart';
import 'widgets/banniere.dart';
import 'widgets/mouvement.dart';
import 'widgets/onglets.dart';

GoRouter creerRouteur({String depart = '/accueil'}) => GoRouter(
  navigatorKey: navigateurRacine,
  initialLocation: depart,
  refreshListenable: Donnees.instance,
  // Sans session, la connexion ; une fois connecte, jamais la connexion.
  redirect: (context, etat) {
    final connecte = Donnees.instance.utilisateur != null;
    final surConnexion = etat.matchedLocation == '/connexion';
    if (!connecte && !surConnexion) return '/connexion';
    if (connecte && surConnexion) return '/accueil';
    return null;
  },
  routes: [
    GoRoute(path: '/connexion', builder: (context, _) => const EcranConnexion()),
    StatefulShellRoute.indexedStack(
      builder: (context, _, navigation) => Coquille(navigation: navigation),
      branches: [
        StatefulShellBranch(
          routes: [GoRoute(path: '/accueil', builder: (context, _) => const EcranAccueil(), routes: _communes())],
        ),
        StatefulShellBranch(
          routes: [GoRoute(path: '/a-traiter', builder: (context, _) => const EcranATraiter(), routes: _communes())],
        ),
        StatefulShellBranch(
          routes: [GoRoute(path: '/a-revoir', builder: (context, _) => const EcranARevoir(), routes: _communes())],
        ),
        StatefulShellBranch(
          routes: [GoRoute(path: '/compte', builder: (context, _) => const EcranCompte(), routes: _communes())],
        ),
      ],
    ),
  ],
);

/// Les pages qu on ouvre depuis n importe quel onglet, sans quitter l onglet.
List<RouteBase> _communes() => [
  GoRoute(
    path: 'client/:id',
    builder: (context, etat) => EcranFicheClient(id: etat.pathParameters['id'] ?? ''),
  ),
  GoRoute(
    path: 'facture/:id',
    builder: (context, etat) => EcranFacture(id: etat.pathParameters['id'] ?? ''),
  ),
  GoRoute(
    path: 'relance/:id',
    builder: (context, etat) => EcranRelance(id: etat.pathParameters['id'] ?? ''),
  ),
  GoRoute(path: 'relances', builder: (context, _) => const EcranRelances()),
  GoRoute(path: 'envois', builder: (context, _) => const EcranEnvois()),
  GoRoute(path: 'suspensions', builder: (context, _) => const EcranSuspensions()),
  GoRoute(path: 'parametres', builder: (context, _) => const EcranParametres()),
  GoRoute(path: 'redactions', builder: (context, _) => const EcranRedactions()),
  GoRoute(
    path: 'journal',
    builder: (context, etat) => EcranJournal(objetId: etat.uri.queryParameters['objet'], correlationId: etat.uri.queryParameters['correlation']),
  ),
];

class AppFaktu extends StatefulWidget {
  const AppFaktu({super.key, this.depart = '/accueil'});

  final String depart;

  @override
  State<AppFaktu> createState() => _AppFaktuState();
}

class _AppFaktuState extends State<AppFaktu> with WidgetsBindingObserver {
  late final _routeur = creerRouteur(depart: widget.depart);
  final _affichage = Affichage.instance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _affichage.addListener(_changer);
    Sobriete.instance.addListener(_sobriete);
    Couleurs.sombre = _nuit();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _affichage.removeListener(_changer);
    Sobriete.instance.removeListener(_sobriete);
    _routeur.dispose();
    super.dispose();
  }

  bool _nuit() => switch (_affichage.mode) {
    ModeTheme.clair => false,
    ModeTheme.sombre => true,
    ModeTheme.systeme => WidgetsBinding.instance.platformDispatcher.platformBrightness == Brightness.dark,
  };

  @override
  void didChangePlatformBrightness() {
    if (_nuit() != Couleurs.sombre) _changer();
  }

  // De retour dans Faktu : les donnees se rafraichissent (au plus toutes les 30 s).
  @override
  void didChangeAppLifecycleState(AppLifecycleState etat) {
    if (etat == AppLifecycleState.resumed && Donnees.instance.utilisateur != null) Donnees.instance.rafraichir();
  }

  void _sobriete() => setState(() {});

  // Les couleurs se lisent a la construction : quand le theme change, tout l arbre se
  // reconstruit, sans perdre la page ouverte.
  void _changer() {
    Couleurs.sombre = _nuit();
    setState(() {});
    void marquer(Element e) {
      e.markNeedsBuild();
      e.visitChildren(marquer);
    }

    (context as Element).visitChildren(marquer);
  }

  @override
  Widget build(BuildContext context) => AnnotatedRegion<SystemUiOverlayStyle>(
    value: barreDuTheme,
    child: MaterialApp.router(
      title: 'Faktu',
      debugShowCheckedModeBanner: false,
      theme: themeFaktu(),
      routerConfig: _routeur,
      scrollBehavior: const DefilementUsw(),
      locale: const Locale('fr'),
      supportedLocales: const [Locale('fr')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      builder: (context, enfant) => MediaQuery(
        data: MediaQuery.of(context).copyWith(),
        child: Allegement(leger: Sobriete.instance.leger, child: enfant!),
      ),
    ),
  );
}
