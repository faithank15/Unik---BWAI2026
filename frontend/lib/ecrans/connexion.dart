// La connexion : les comptes de test du back-end, gestionnaire et validateur (cahier, section 9).
// Pas de creation de compte : les comptes sont fournis par l equipe.
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../outils/api.dart';
import '../outils/langue.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/icone.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';

class EcranConnexion extends StatefulWidget {
  const EcranConnexion({super.key});

  @override
  State<EcranConnexion> createState() => _EcranConnexionState();
}

class _EcranConnexionState extends State<EcranConnexion> {
  final _identifiant = TextEditingController();
  final _motDePasse = TextEditingController();
  String? _erreur;
  bool _enCours = false;

  @override
  void dispose() {
    _identifiant.dispose();
    _motDePasse.dispose();
    super.dispose();
  }

  Future<void> _connecter() async {
    if (_identifiant.text.trim().isEmpty || _motDePasse.text.isEmpty) {
      setState(() => _erreur = t('Saisissez votre nom d’utilisateur et votre mot de passe.'));
      return;
    }
    setState(() {
      _enCours = true;
      _erreur = null;
    });
    try {
      await Donnees.instance.connecter(_identifiant.text, _motDePasse.text);
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    } finally {
      if (mounted) setState(() => _enCours = false);
    }
  }

  @override
  Widget build(BuildContext context) => PageFormulaire(
    retour: false,
    enfants: [
      const Center(child: LogoFaktu(taille: 76)),
      const SizedBox(height: 22),
      Titre(t('Connectez-vous à Faktu'), style: Textes.titre, centre: true),
      const SizedBox(height: 8),
      TextePage([(t('Suivez les impayés de vos clients et relancez chacun au bon moment.'), false)], centre: true),
      const SizedBox(height: 30),
      ChampVerre(
        libelle: t('Nom d’utilisateur'),
        icone: 'profil',
        controleur: _identifiant,
        indice: 'gestionnaire',
        action: TextInputAction.next,
        remplissage: const [AutofillHints.username],
      ),
      const SizedBox(height: 16),
      ChampVerre(
        libelle: t('Mot de passe'),
        icone: 'cadenas',
        controleur: _motDePasse,
        secret: true,
        action: TextInputAction.done,
        onSubmitted: (_) => _connecter(),
        erreur: _erreur,
        remplissage: const [AutofillHints.password],
      ),
      const SizedBox(height: 24),
      BoutonVerre(texte: t('Se connecter'), plein: true, enCours: _enCours, onTap: _connecter),
      const SizedBox(height: 16),
      Text(t('Comptes de démonstration : gestionnaire ou validateur.'), textAlign: TextAlign.center, style: Textes.petit),
    ],
  );
}
