// Les formulations de courriel ecrites par l IA (GET /api/redactions). L IA redige une
// introduction et une conclusion par cas et par ton ; les montants, dates et factures sont
// inseres par le code. Une personne les relit avant de les laisser partir (POST /redactions/relue).
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import '../widgets/faktu.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';

class EcranRedactions extends StatefulWidget {
  const EcranRedactions({super.key});

  @override
  State<EcranRedactions> createState() => _EcranRedactionsState();
}

class _EcranRedactionsState extends State<EcranRedactions> {
  List<Json>? _liste;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    try {
      final l = await Donnees.instance.redactions();
      if (mounted) {
        setState(() {
          _liste = l;
          _erreur = null;
        });
      }
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  Future<void> _relue(Json r) async {
    try {
      await Donnees.instance.marquerRelue('${r['cle']}');
      if (mounted) bulle(context, t('Formulation marquée comme relue.'), icone: 'coche');
      await _charger();
    } on ApiErreur catch (e) {
      if (mounted) bulle(context, e.message, icone: 'alerte');
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = _liste;
    final aRelire = l?.where((r) => r['statut'] != 'RELUE').length ?? 0;
    return PageFaktu(
      titre: t('Courriels rédigés par l’IA'),
      sousTitre: l == null ? null : accorder(aRelire, '{n} formulation à relire', '{n} formulations à relire'),
      retour: true,
      rafraichir: false,
      enfants: [
        Text(
          t(
            'L’IA écrit l’introduction et la conclusion des courriels, selon le cas du client et le ton de l’étape. Les montants, les dates et les factures sont toujours insérés par Faktu depuis les données vérifiées. WhatsApp garde les messages types.',
          ),
          style: Textes.petit,
        ),
        const SizedBox(height: 16),
        if (_erreur != null)
          EtatErreur(message: _erreur!, onReessayer: _charger)
        else if (l == null)
          const Attente()
        else if (l.isEmpty)
          EtatVide(
            icone: 'etincelle',
            titre: t('Aucun courriel rédigé pour le moment'),
            texte: t(
              'Les formulations s’afficheront ici après le premier courriel envoyé avec l’IA. Sans IA disponible, les courriels utilisent les messages types.',
            ),
          )
        else
          for (final r in l) ...[_CarteRedaction(r, onRelue: () => _relue(r)), const SizedBox(height: 12)],
      ],
    );
  }
}

class _CarteRedaction extends StatelessWidget {
  const _CarteRedaction(this.r, {required this.onRelue});

  final Json r;
  final VoidCallback onRelue;

  @override
  Widget build(BuildContext context) {
    final relue = r['statut'] == 'RELUE';
    return Plaque(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(casRedaction('${r['cas']}'), style: Textes.libelle)),
              PastilleStatut(relue ? Apparence(t('Relue'), 'coche', Couleurs.succes) : Apparence(t('À relire'), 'oeil', Couleurs.discret), petite: true),
            ],
          ),
          const SizedBox(height: 2),
          Text(
            [tonRedaction('${r['ton_applique'] ?? r['ton']}'), r['nb_factures'] == 'PLUSIEURS' ? t('plusieurs factures') : t('une facture')].join(' · '),
            style: Textes.petit,
          ),
          const SizedBox(height: 10),
          Text('${r['objet']}', style: Textes.corps.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Text('${r['introduction']}', style: Textes.corps),
          const SizedBox(height: 6),
          Text(t('[tableau des factures inséré par Faktu]'), style: Textes.petit),
          const SizedBox(height: 6),
          Text('${r['conclusion']}', style: Textes.corps),
          const SizedBox(height: 8),
          Text('${r['modele_version'] ?? ''}', style: Textes.petit),
          if (!relue) ...[const SizedBox(height: 12), BoutonVerre(texte: t('Marquer comme relue'), icone: 'coche', onTap: onRelue)],
        ],
      ),
    );
  }
}
