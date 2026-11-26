// Le compte : qui est connecte et ce que son role permet, le theme (clair, sombre ou celui du
// telephone), les parametres metier (lecture ; modifiables par le validateur : PUT
// /api/parametres/{cle}), la reinitialisation des donnees de demonstration (validateur), les
// limites connues (le cahier veut qu elles soient affichees) et la deconnexion.
import 'package:flutter/material.dart';

import '../donnees/affichage.dart';
import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/faktu.dart';
import '../widgets/feuille.dart';
import '../widgets/formulaires.dart';
import '../widgets/page.dart';
import '../widgets/reglages.dart';
import '../widgets/verre.dart';

class EcranCompte extends StatefulWidget {
  const EcranCompte({super.key});

  @override
  State<EcranCompte> createState() => _EcranCompteState();
}

class _EcranCompteState extends State<EcranCompte> {
  // Une feuille de choix se ferme un instant apres le choix (comme dans Discover).
  static void _fermer(BuildContext f) {
    final route = ModalRoute.of(f);
    Future<void>.delayed(const Duration(milliseconds: 320), () {
      if (f.mounted && route != null && route.isCurrent) Navigator.pop(f);
    });
  }

  Future<void> _theme() => montrerFeuille<void>(
    context,
    titre: t('Thème'),
    contenu: (f) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: StatefulBuilder(
        builder: (context, maj) => ListeMotifs(
          motifs: [(t('Paramètre par défaut du système'), t('Suit le thème clair ou sombre du téléphone')), (t('Clair'), null), (t('Sombre'), null)],
          choisi: Affichage.instance.mode.index,
          onChoisi: (i) {
            Affichage.instance.choisirTheme(ModeTheme.values[i]);
            maj(() {});
            _fermer(f);
          },
        ),
      ),
    ),
  );

  Future<void> _reinitialiser() async {
    final oui = await confirmer(
      context,
      titre: t('Réinitialiser les données ?'),
      texte: t('Le jeu de données fictif est rechargé, au 15 décembre 2026. Tout ce qui a été fait depuis est effacé.'),
      action: t('Réinitialiser'),
      icone: 'retourner',
    );
    if (!oui) return;
    try {
      await Donnees.instance.reinitialiser();
      if (mounted) bulle(context, t('Données réinitialisées au 15 décembre 2026.'), icone: 'retourner');
    } on ApiErreur catch (e) {
      if (mounted) bulle(context, e.message, icone: 'alerte');
    }
  }

  Future<void> _deconnecter() async {
    final oui = await confirmer(
      context,
      titre: t('Se déconnecter ?'),
      texte: t('Il faudra saisir à nouveau votre nom d’utilisateur et votre mot de passe.'),
      action: t('Se déconnecter'),
      icone: 'sortie',
    );
    if (oui) await Donnees.instance.deconnecter();
  }

  @override
  Widget build(BuildContext context) {
    final d = Donnees.instance;
    final u = d.utilisateur;
    return PageFaktu(
      titre: t('Compte'),
      rafraichir: false,
      enfants: [
        if (u != null)
          Plaque(
            rayon: Mesures.rayonCarte,
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
            child: Row(
              children: [
                Container(
                  width: 52,
                  height: 52,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: Couleurs.ocean, borderRadius: BorderRadius.circular(26)),
                  child: Text(
                    u.nom.isEmpty ? '?' : u.nom[0].toUpperCase(),
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Colors.white),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(u.nom, style: Textes.sousTitre.copyWith(fontSize: 18)),
                      Text([role(u.role), if (u.identifiant.isNotEmpty) u.identifiant].join(' · '), style: Textes.petit),
                    ],
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 10),
        if (u != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(
              u.validateur
                  ? t('En tant que validateur, vous approuvez les gros montants, les contestations et les échéanciers, et vous réglez les paramètres.')
                  : t(
                      'En tant que gestionnaire, vous suivez les factures, enregistrez les paiements et les réponses des clients, et traitez les dossiers à revoir. Les relances de gros montant, les contestations et les échéanciers sont décidés par un validateur.',
                    ),
              style: Textes.petit,
            ),
          ),
        const SizedBox(height: 22),
        GroupeReglages(
          titre: t('Affichage'),
          lignes: [
            LigneReglage(
              icone: 'theme',
              texte: t('Thème'),
              valeur: switch (Affichage.instance.mode) {
                ModeTheme.systeme => t('Paramètre par défaut du système'),
                ModeTheme.clair => t('Clair'),
                ModeTheme.sombre => t('Sombre'),
              },
              onTap: _theme,
            ),
          ],
        ),
        GroupeReglages(
          titre: t('Données'),
          lignes: [
            LigneReglage(
              icone: 'reglages',
              texte: t('Paramètres métier'),
              valeur: u?.validateur == true ? t('Vous pouvez les modifier') : t('Lecture seule'),
              onTap: () => ouvrir(context, 'parametres'),
            ),
            LigneReglage(icone: 'etincelle', texte: t('Courriels rédigés par l’IA'), onTap: () => ouvrir(context, 'redactions')),
            LigneReglage(icone: 'journal', texte: t('Journal'), onTap: () => ouvrir(context, 'journal')),
            if (u?.validateur == true && (d.contexte?.demonstration ?? false))
              LigneReglage(icone: 'retourner', texte: t('Réinitialiser les données'), valeur: t('Démonstration'), onTap: _reinitialiser),
          ],
        ),
        GroupeReglages(
          titre: t('Bon à savoir'),
          lignes: [
            for (final (icone, texte) in [
              ('bouclier', t('Tout est simulé : aucun message ni paiement réel.')),
              ('etincelle', t('L’IA classe seulement les réponses. Elle ne touche jamais un solde.')),
              ('globe', t('Les messages sont en français uniquement.')),
              ('piece', t('Les pénalités de retard ne sont pas ajoutées au solde.')),
            ])
              LigneReglage(icone: icone, texte: texte, info: true),
          ],
        ),
        GroupeReglages(
          lignes: [LigneReglage(icone: 'sortie', texte: t('Se déconnecter'), danger: true, onTap: _deconnecter)],
        ),
      ],
    );
  }
}

/// Les parametres metier (seuils, delais, ponderations). Le validateur les modifie ; chaque
/// changement est journalise par le back-end.
class EcranParametres extends StatefulWidget {
  const EcranParametres({super.key});

  @override
  State<EcranParametres> createState() => _EcranParametresState();
}

class _EcranParametresState extends State<EcranParametres> {
  List<Json>? _liste;
  String? _erreur;

  // Les reglages de test (pannes simulees) restent hors de l application.
  static const _caches = {'date_reference', 'simulation_interruption_apres'};

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    try {
      final l = await Donnees.instance.parametres();
      if (!mounted) return;
      setState(() {
        _liste = l.where((p) => !_caches.contains(p['cle'])).toList();
        _erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  Future<void> _modifier(Json p) async {
    final valeur = TextEditingController(text: '${p['valeur'] ?? ''}');
    String? erreur;
    final ok = await montrerFeuille<bool>(
      context,
      titre: '${p['description'] ?? p['cle']}',
      contenu: (f) => StatefulBuilder(
        builder: (f, maj) => CorpsFeuille(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (p['type'] == 'BOOLEEN')
                ChoixPastilles(
                  valeurs: const ['true', 'false'],
                  choisie: valeur.text,
                  nom: (v) => v == 'true' ? t('Oui') : t('Non'),
                  onChoisi: (v) => maj(() => valeur.text = v),
                )
              else
                ChampVerre(
                  icone: 'reglages',
                  controleur: valeur,
                  clavier: p['type'] == 'TEXTE' ? TextInputType.text : const TextInputType.numberWithOptions(decimal: true),
                ),
              ErreurFormulaire(erreur),
              const SizedBox(height: 16),
              BoutonVerre(
                texte: t('Enregistrer'),
                plein: true,
                onTap: () async {
                  try {
                    await Donnees.instance.modifierParametre('${p['cle']}', valeur.text.trim().replaceAll(',', '.'));
                    if (f.mounted) Navigator.pop(f, true);
                  } on ApiErreur catch (e) {
                    maj(() => erreur = e.message);
                  }
                },
              ),
            ],
          ),
        ),
      ),
    );
    if (ok == true) await _charger();
  }

  @override
  Widget build(BuildContext context) {
    final validateur = Donnees.instance.validateur;
    return PageFaktu(
      titre: t('Paramètres métier'),
      sousTitre: validateur ? t('Chaque changement est inscrit au journal') : t('Seul un validateur peut les modifier'),
      retour: true,
      rafraichir: false,
      enfants: [
        if (_liste == null && _erreur != null)
          EtatErreur(message: _erreur!, onReessayer: _charger)
        else if (_liste == null)
          const Attente()
        else
          GroupeLignes(
            retrait: 16,
            lignes: [
              for (final p in _liste!)
                InkWell(
                  onTap: validateur ? () => _modifier(p) : null,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    child: Row(
                      children: [
                        Expanded(child: Text('${p['description'] ?? p['cle']}', style: Textes.corps.copyWith(fontSize: 14.5))),
                        const SizedBox(width: 12),
                        Text(
                          p['type'] == 'BOOLEEN' ? ('${p['valeur']}' == 'true' ? t('Oui') : t('Non')) : '${p['valeur']}',
                          style: Textes.libelle.copyWith(color: validateur ? Couleurs.ocean : Couleurs.texte),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}
