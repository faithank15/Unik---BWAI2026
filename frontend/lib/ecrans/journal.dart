// Le journal (GET /api/journal) : ce qui s est passe, qui l a fait (systeme, IA, personne), l etat
// avant et apres, et le fil d une decision (correlation_id). Lecture seule : rien ne s y modifie.
import 'dart:convert';

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
import '../widgets/icone.dart';
import '../widgets/verre.dart';

class EcranJournal extends StatefulWidget {
  const EcranJournal({super.key, this.objetId, this.correlationId});

  final String? objetId;
  final String? correlationId;

  @override
  State<EcranJournal> createState() => _EcranJournalState();
}

class _EcranJournalState extends State<EcranJournal> {
  List<Evenement>? _liste;
  String? _erreur;
  String? _acteur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    try {
      final l = await Donnees.instance.journal(objetId: widget.objetId, correlationId: widget.correlationId);
      if (!mounted) return;
      setState(() {
        _liste = l;
        _erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final liste = _liste?.where((e) => _acteur == null || e.acteur == _acteur).toList();
    return PageFaktu(
      titre: widget.correlationId != null ? t('Une décision') : t('Journal'),
      sousTitre: widget.objetId ?? (widget.correlationId != null ? t('Tous les événements liés') : t('Ajout seulement : rien ne s’y efface')),
      retour: true,
      rafraichir: false,
      enfants: [
        Row(
          children: [
            Pastille(texte: t('Tous'), retenue: _acteur == null, onTap: () => setState(() => _acteur = null)),
            for (final a in const ['SYSTEME', 'IA', 'UTILISATEUR']) ...[
              const SizedBox(width: 8),
              Pastille(texte: acteur(a), retenue: _acteur == a, onTap: () => setState(() => _acteur = a)),
            ],
          ],
        ),
        const SizedBox(height: 16),
        if (liste == null && _erreur != null)
          EtatErreur(message: _erreur!, onReessayer: _charger)
        else if (liste == null)
          const Attente()
        else if (liste.isEmpty)
          EtatVide(icone: 'journal', titre: t('Aucun événement'))
        else
          GroupeLignes(
            retrait: 52,
            lignes: [
              for (final e in liste)
                _LigneEvenement(
                  e,
                  onTap: widget.correlationId == null && e.correlationId != null ? () => ouvrir(context, 'journal?correlation=${e.correlationId}') : null,
                ),
            ],
          ),
      ],
    );
  }
}

/// Un champ du journal (texte JSON ou objet) en « cle : valeur », lisible.
String _lisible(Object? v) {
  if (v == null) return '';
  Object? o = v;
  if (v is String) {
    try {
      o = jsonDecode(v);
    } catch (_) {
      return v;
    }
  }
  if (o is Map) {
    return o.entries
        .where((e) => e.value != null)
        .map((e) => '${lisible('${e.key}')} : ${e.value is List ? (e.value as List).join(', ') : e.value}')
        .join(' · ');
  }
  return '$o';
}

class _LigneEvenement extends StatelessWidget {
  const _LigneEvenement(this.e, {this.onTap});

  final Evenement e;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final icone = switch (e.acteur) {
      'IA' => 'etincelle',
      'UTILISATEUR' => 'profil',
      _ => 'reglages',
    };
    final details = _lisible(e.details);
    final avant = _lisible(e.avant);
    final apres = _lisible(e.apres);
    final ligne = Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 14, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icone(icone, taille: 20, couleur: Couleurs.discret),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(evenement(e.type), style: Textes.libelle),
                const SizedBox(height: 2),
                Text(
                  [acteur(e.acteur), if (e.horodatage != null) horodatage(e.horodatage!.toLocal()), e.objetId].where((x) => x.isNotEmpty).join(' · '),
                  style: Textes.petit,
                ),
                if (details.isNotEmpty) ...[const SizedBox(height: 4), Text(details, style: Textes.petit.copyWith(color: Couleurs.texte))],
                if (avant.isNotEmpty || apres.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    '${avant.isEmpty ? t('rien') : avant}  →  ${apres.isEmpty ? t('rien') : apres}',
                    style: Textes.petit.copyWith(color: Couleurs.texte, fontWeight: FontWeight.w600),
                  ),
                ],
                if (e.dateReference != null) Text(t('Date de référence : {d}', {'d': dateCourte(e.dateReference!)}), style: Textes.petit),
              ],
            ),
          ),
        ],
      ),
    );
    return onTap == null ? ligne : InkWell(onTap: onTap, child: ligne);
  }
}
