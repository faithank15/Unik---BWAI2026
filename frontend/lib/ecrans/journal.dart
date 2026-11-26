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
      sousTitre: widget.objetId ?? (widget.correlationId != null ? t('Tous les événements liés') : t('Les entrées ne peuvent être ni modifiées ni supprimées')),
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
          EtatVide(icone: 'journal', titre: t('Aucune entrée dans le journal'))
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
// Les cles des details du journal, dites en clair. Une cle absente : lisible().
const _cles = {
  'facture_id': 'Facture',
  'facture_citee_id': 'Facture citée',
  'client_id': 'Client',
  'echeance_id': 'Échéance',
  'paiement_id': 'Paiement',
  'promesse_id': 'Promesse',
  'effet': 'Effet',
  'contestation_id': 'Contestation',
  'accord_id': 'Échéancier',
  'relance_id': 'Relance',
  'message_id': 'Réponse',
  'date_promise': 'Date promise',
  'date_paiement': 'Date du paiement',
  'date_prevue': 'Prévue le',
  'date_envoi': 'Envoyée le',
  'montant': 'Montant',
  'montant_promis': 'Montant promis',
  'montant_affecte': 'Montant affecté',
  'non_affecte': 'Reste à affecter',
  'solde': 'Solde',
  'categorie': 'Catégorie',
  'categorie_ia': 'Catégorie proposée par l’IA',
  'categorie_validee': 'Catégorie retenue',
  'statut': 'Statut',
  'statut_traitement': 'Statut',
  'origine': 'Origine',
  'motif': 'Motif',
  'decision': 'Décision',
  'commentaire': 'Commentaire',
  'canal': 'Canal',
  'etape': 'Étape',
  'confiance': 'Confiance',
  'resolution': 'Décision',
};

final _dateIso = RegExp(r'^\d{4}-\d{2}-\d{2}');
final _code = RegExp(r'^[A-Z][A-Z0-9_]+$');

/// Une valeur du journal en clair : une date, un montant, un code, ou tel quel.
String _valeur(String cle, Object? v) {
  if (v is List) return v.map((x) => _valeur(cle, x)).join(', ');
  if (v is Map) return _lisible(v);
  if (v is num && (cle.contains('montant') || cle.contains('solde') || cle.contains('affecte') || cle.contains('total'))) return fcfa(v.round());
  if (v is num && cle == 'confiance') return confiance(v.toDouble());
  final texte = '$v';
  if (_dateIso.hasMatch(texte)) {
    final d = DateTime.tryParse(texte);
    if (d != null) return texte.length > 10 ? horodatage(d.toLocal()) : dateCourte(d);
  }
  if (_code.hasMatch(texte)) {
    if (cle.contains('categorie')) return categorie(texte);
    if (cle == 'statut_traitement' || const {'A_CLASSER', 'CLASSE', 'EN_REVUE', 'TRAITE'}.contains(texte)) return statutMessage(texte);
    if (cle == 'canal') return canal(texte);
    if (cle == 'etape') return etape(texte);
    if (cle == 'motif') return motif(texte);
    return lisible(texte);
  }
  return texte;
}

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
        .where((e) => e.value != null && '${e.value}'.isNotEmpty)
        .map((e) => '${t(_cles['${e.key}'] ?? lisible('${e.key}'))} : ${_valeur('${e.key}', e.value)}')
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
                    avant.isEmpty ? apres : (apres.isEmpty ? t('{a} (retiré)', {'a': avant}) : '$avant  →  $apres'),
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
