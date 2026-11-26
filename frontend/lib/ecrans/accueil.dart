// Le tableau de bord (GET /api/tableau-de-bord) : la date de reference toujours visible, l encours,
// les factures par statut, les relances du jour, ce qui attend une personne, et le gain mesure face
// a la regle naive (GET /api/evaluation/comparaison-reference). Chaque chiffre ouvre sa liste.
// Les deux temps des relances sont separes, comme dans le back-end : preparer, puis envoyer (entre
// les deux, un paiement recu annule la relance : scenario S07).
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import '../widgets/faktu.dart';
import '../widgets/feuille.dart';
import '../widgets/icone.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';

class EcranAccueil extends StatelessWidget {
  const EcranAccueil({super.key});

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: Donnees.instance,
    builder: (context, _) {
      final d = Donnees.instance;
      final tb = d.tableau;
      return PageFaktu(
        titre: t('Tableau de bord'),
        sousTitre: t('Au {d}', {'d': dateDuJour(d.dateReference)}),
        enfants: [
          if (tb == null && d.erreur != null)
            EtatErreur(message: d.erreur!, onReessayer: () => d.rafraichir(force: true))
          else if (tb == null)
            const Attente()
          else
            ..._contenu(context, d, tb),
        ],
      );
    },
  );

  List<Widget> _contenu(BuildContext context, Donnees d, Tableau tb) {
    final rel = tb.relances;
    final aValider = rel['en_attente_validation'] ?? 0;
    final gain = json(d.comparaison?['gain']);
    final evitees = entier(gain['relances_injustifiees_evitees']);
    final aRevoir = tb.revueOuvertes + d.messagesAClasser.length;
    return [
      Plaque(
        rayon: Mesures.rayonCarte,
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t('Encours à recouvrer'), style: Textes.petit),
            const SizedBox(height: 4),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(fcfa(tb.encoursTotal), style: Textes.titre.copyWith(fontSize: 32)),
            ),
            const SizedBox(height: 4),
            Text(
              t('dont {e} en retard, sur {n}', {'e': fcfa(tb.encoursEchu), 'n': accorder(tb.nbOuvertes, '{n} facture ouverte', '{n} factures ouvertes')}),
              style: Textes.petit,
            ),
            const SizedBox(height: 14),
            _Repartition(tb.parStatut),
          ],
        ),
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: CarteChiffre(
              valeur: nombre(d.priorisation.length),
              libelle: accorder(d.priorisation.length, 'facture à relancer', 'factures à relancer'),
              icone: 'horloge',
              couleur: d.priorisation.isEmpty ? null : Couleurs.erreur,
              onTap: () => context.go('/a-traiter'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: CarteChiffre(
              valeur: nombre(aRevoir),
              libelle: accorder(aRevoir, 'dossier à revoir', 'dossiers à revoir'),
              icone: 'drapeau',
              onTap: () => context.go('/a-revoir'),
            ),
          ),
        ],
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: CarteChiffre(
              valeur: nombre(evitees),
              libelle: accorder(evitees, 'relance injustifiée évitée', 'relances injustifiées évitées'),
              icone: 'bouclier',
              couleur: Couleurs.succes,
              onTap: () => ouvrir(context, 'suspensions'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: CarteChiffre(
              valeur: nombre(rel['envoyees_sim'] ?? 0),
              libelle: t('relances envoyées aujourd’hui'),
              icone: 'envoyer',
              onTap: () => ouvrir(context, 'envois'),
            ),
          ),
        ],
      ),
      const SizedBox(height: 22),
      TitreSection(t('Relances du jour')),
      Plaque(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final (code, cle) in [
                  ('PLANIFIEE', 'planifiees'),
                  ('EN_ATTENTE_VALIDATION', 'en_attente_validation'),
                  ('ENVOYEE_SIM', 'envoyees_sim'),
                  ('ANNULEE', 'annulees'),
                  ('SAUTEE', 'sautees'),
                ])
                  if ((rel[cle] ?? 0) > 0)
                    PastilleStatut(
                      Apparence(
                        '${apparenceRelance(code).texte} ${rel[cle]}',
                        apparenceRelance(code).icone,
                        apparenceRelance(code).couleur,
                        fond: apparenceRelance(code).fond,
                      ),
                    ),
                if (rel.values.every((v) => v == 0)) Text(t('Rien de préparé pour aujourd’hui.'), style: Textes.petit),
              ],
            ),
            if (d.contexte?.jourOuvre == false) ...[
              const SizedBox(height: 8),
              Text(t('Aujourd’hui n’est pas un jour ouvré : aucun envoi.'), style: Textes.petit.copyWith(color: Couleurs.erreur)),
            ],
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: BoutonVerre(texte: t('Préparer'), icone: 'calendrier', onTap: () => _planifier(context)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: BoutonVerre(texte: t('Envoyer'), icone: 'envoyer', plein: true, onTap: () => _envoyer(context)),
                ),
              ],
            ),
            if (aValider > 0) ...[
              const SizedBox(height: 10),
              Text(
                accorder(aValider, '{n} relance de gros montant attend un validateur.', '{n} relances de gros montant attendent un validateur.'),
                style: Textes.petit,
              ),
            ],
          ],
        ),
      ),
      const SizedBox(height: 22),
      TitreSection(t('Voir')),
      GroupeLignes(
        retrait: 54,
        lignes: [
          _Lien(icone: 'calendrier', texte: t('Toutes les relances'), onTap: () => ouvrir(context, 'relances')),
          _Lien(icone: 'enveloppe', texte: t('Messages envoyés'), detail: t('La boîte d’envoi simulée'), onTap: () => ouvrir(context, 'envois')),
          _Lien(
            icone: 'bouclier',
            texte: t('Relances suspendues'),
            detail: accorder(tb.suspensions.values.fold(0, (a, b) => a + b), '{n} échéance', '{n} échéances'),
            onTap: () => ouvrir(context, 'suspensions'),
          ),
          _Lien(icone: 'journal', texte: t('Journal'), detail: t('Chaque décision et sa raison'), onTap: () => ouvrir(context, 'journal')),
        ],
      ),
      const SizedBox(height: 22),
      _DateReference(date: d.dateReference, validateur: d.validateur, demonstration: d.contexte?.demonstration ?? false),
    ];
  }

  Future<void> _planifier(BuildContext context) async {
    try {
      final r = await Donnees.instance.planifier();
      if (!context.mounted) return;
      final creees = entier(r['creees']);
      final suspendues = (r['suspendues'] as List? ?? const []).length;
      bulle(
        context,
        [
          accorder(creees, '{n} relance préparée', '{n} relances préparées'),
          if (entier(r['sautees']) > 0) accorder(entier(r['sautees']), '{n} sautée', '{n} sautées'),
          if (suspendues > 0) accorder(suspendues, '{n} suspendue', '{n} suspendues'),
          if (entier(r['escalades']) > 0) accorder(entier(r['escalades']), '{n} escalade', '{n} escalades'),
        ].join(' · '),
        icone: 'calendrier',
      );
    } on ApiErreur catch (e) {
      if (context.mounted) bulle(context, e.message, icone: 'alerte');
    }
  }

  Future<void> _envoyer(BuildContext context) async {
    try {
      final r = await Donnees.instance.envoyerRelances();
      if (!context.mounted) return;
      bulle(
        context,
        [
          accorder(entier(r['envoyees']), '{n} relance envoyée', '{n} relances envoyées'),
          if (entier(r['annulees']) > 0) accorder(entier(r['annulees']), '{n} annulée', '{n} annulées'),
          if (entier(r['en_attente_validation']) > 0) accorder(entier(r['en_attente_validation']), '{n} à valider', '{n} à valider'),
        ].join(' · '),
        icone: 'envoyer',
      );
    } on ApiErreur catch (e) {
      if (context.mounted) bulle(context, e.message, icone: 'alerte');
    }
  }
}

/// La repartition des factures par statut : une barre en morceaux, et la legende en mots.
class _Repartition extends StatelessWidget {
  const _Repartition(this.parStatut);

  final Map<String, int> parStatut;

  static const _ordre = ['ECHUE', 'NON_ECHUE', 'COUVERTE_PAR_ECHEANCIER', 'CONTESTEE', 'SOLDEE', 'ANNULEE'];

  @override
  Widget build(BuildContext context) {
    final presents = [
      for (final s in _ordre)
        if ((parStatut[s] ?? 0) > 0) s,
    ];
    if (presents.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: SizedBox(
            height: 8,
            child: Row(
              children: [
                for (final s in presents)
                  Expanded(
                    flex: parStatut[s]!,
                    child: Container(
                      // Un filet de 2 px du fond entre les morceaux : ils se lisent separes.
                      margin: const EdgeInsets.only(right: 2),
                      color: apparenceFacture(s).couleur.withValues(alpha: s == 'NON_ECHUE' || s == 'ANNULEE' ? 0.45 : 1),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 14,
          runSpacing: 6,
          children: [
            for (final s in presents)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icone(apparenceFacture(s).icone, taille: 14, couleur: apparenceFacture(s).couleur),
                  const SizedBox(width: 5),
                  Text('${apparenceFacture(s).texte} ${parStatut[s]}', style: Textes.petit.copyWith(color: Couleurs.texte)),
                ],
              ),
          ],
        ),
      ],
    );
  }
}

class _Lien extends StatelessWidget {
  const _Lien({required this.icone, required this.texte, required this.onTap, this.detail});

  final String icone;
  final String texte;
  final String? detail;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 13, 12, 13),
      child: Row(
        children: [
          Icone(icone, taille: 22),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(texte, style: Textes.libelle),
                if (detail != null) Text(detail!, style: Textes.petit),
              ],
            ),
          ),
          Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
        ],
      ),
    ),
  );
}

/// La date de reference : toutes les decisions se prennent a cette date (cahier, section 6). Le
/// validateur peut l avancer (POST /api/admin/avancer) pour montrer les jours suivants.
class _DateReference extends StatelessWidget {
  const _DateReference({required this.date, required this.validateur, required this.demonstration});

  final DateTime date;
  final bool validateur;
  final bool demonstration;

  @override
  Widget build(BuildContext context) => Plaque(
    padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
    child: Row(
      children: [
        Icone('calendrier', taille: 22, couleur: Couleurs.discret),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t('Date de référence'), style: Textes.petit),
              Text(dateLongue(date), style: Textes.libelle),
            ],
          ),
        ),
        if (validateur && demonstration)
          BoutonVerre(
            texte: t('Jour suivant'),
            large: false,
            onTap: () async {
              final oui = await confirmer(
                context,
                titre: t('Passer au jour suivant ?'),
                texte: t('Faktu passera au {d}, puis préparera et enverra les relances de ce jour.', {'d': dateLongue(date.add(const Duration(days: 1)))}),
                action: t('Passer'),
                icone: 'calendrier',
                danger: false,
              );
              if (!oui) return;
              try {
                await Donnees.instance.avancer(1);
              } on ApiErreur catch (e) {
                if (context.mounted) bulle(context, e.message, icone: 'alerte');
              }
            },
          ),
      ],
    ),
  );
}
