// Une facture (GET /api/factures/{id}) et ce qui explique son resultat (GET /api/factures/{id}/
// explication) : la regle de statut retenue et celles ecartees, les echeances (du, affecte, reste),
// les paiements et avoirs affectes, et le dossier (contestations, promesses, echeanciers,
// relances, messages). Les actions de la facture sont ici : paiement, avoir, contestation,
// promesse, echeancier ; et pour le validateur, clore une contestation ou accepter un echeancier.
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
import '../widgets/feuille.dart';
import '../widgets/icone.dart';
import '../widgets/verre.dart';
import 'actions_facture.dart';
import 'ajouter.dart';
import 'fiche_client.dart';

class EcranFacture extends StatefulWidget {
  const EcranFacture({super.key, required this.id});

  final String id;

  @override
  State<EcranFacture> createState() => _EcranFactureState();
}

class _EcranFactureState extends State<EcranFacture> {
  Facture? _facture;
  Json? _explication;
  Priorite? _priorite;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    final d = Donnees.instance;
    try {
      final r = await Future.wait([d.facture(widget.id), d.explication(widget.id)]);
      if (!mounted) return;
      setState(() {
        _facture = r[0] as Facture;
        _explication = r[1] as Json;
        _priorite = d.priorisation.where((p) => p.factureId == widget.id).firstOrNull;
        _erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  /// Une action, puis la facture relue.
  Future<void> _faire(Future<bool> Function() action) async {
    if (await action()) await _charger();
  }

  @override
  Widget build(BuildContext context) {
    final f = _facture;
    return PageFaktu(
      titre: f?.numero ?? widget.id,
      sousTitre: f == null ? null : Donnees.instance.nomClient(f.clientId),
      retour: true,
      rafraichir: false,
      enfants: [
        if (f == null && _erreur != null)
          EtatErreur(message: _erreur!, onReessayer: _charger)
        else if (f == null || _explication == null)
          const Attente()
        else
          ..._contenu(context, f, _explication!),
      ],
    );
  }

  List<Widget> _contenu(BuildContext context, Facture f, Json ex) {
    final a = apparenceFacture(f.statut, retard: f.retard);
    final regle = json(json(ex['calcul'])['regle_statut']);
    final contestations = jsons(ex['contestations']);
    final promesses = jsons(ex['promesses']);
    final accords = jsons(ex['accords']);
    final ouverte = contestations.where((c) => c['statut'] == 'OUVERTE').firstOrNull;
    final validateur = Donnees.instance.validateur;
    return [
      Plaque(
        rayon: Mesures.rayonCarte,
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [PastilleStatut(a), if (f.partiellementPayee) PastilleStatut(Apparence(t('Payée en partie'), 'piece', Couleurs.ocean))],
            ),
            const SizedBox(height: 14),
            Text(t('Reste à payer'), style: Textes.petit),
            Text(fcfa(f.solde), style: Textes.titre.copyWith(fontSize: 30, decoration: a.barre ? TextDecoration.lineThrough : null)),
            const SizedBox(height: 12),
            LigneInfo(t('Montant TTC'), fcfa(f.montantTtc)),
            LigneInfo(t('Déjà payé'), fcfa(f.affecte)),
            if (f.dateEmission != null) LigneInfo(t('Émise le'), dateLongue(f.dateEmission!)),
            if (f.conditions != null) LigneInfo(t('Conditions'), lisible(f.conditions!)),
            if (f.tauxPenalite != null)
              LigneInfo(t('Pénalité prévue'), t('{n} %, jamais ajoutée au solde', {'n': f.tauxPenalite!.toString().replaceAll('.', ',')})),
            if (f.suspension != null) LigneInfo(t('Relances'), motif(f.suspension), couleur: Couleurs.ocean),
          ],
        ),
      ),
      const SizedBox(height: 12),
      // Pourquoi ce statut : la regle retenue (cahier 6.2, la premiere qui correspond l emporte).
      Plaque(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icone('aide', taille: 20, couleur: Couleurs.discret),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('Pourquoi ce statut'), style: Textes.libelle),
                  const SizedBox(height: 2),
                  Text('${regle['motif'] ?? ''}', style: Textes.corps.copyWith(fontSize: 14.5)),
                  for (final m in jsons(regle['motifs_exclusion'])) Text('${apparenceFacture('${m['regle']}').texte} : ${m['motif']}', style: Textes.petit),
                ],
              ),
            ),
          ],
        ),
      ),
      if (_priorite != null) ...[
        const SizedBox(height: 12),
        Plaque(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  RondScore(_priorite!.score),
                  const SizedBox(width: 12),
                  Expanded(child: Text(t('Priorité n° {r} sur {n}', {'r': _priorite!.rang, 'n': Donnees.instance.priorisation.length}), style: Textes.libelle)),
                ],
              ),
              const SizedBox(height: 12),
              DetailScore(_priorite!),
            ],
          ),
        ),
      ],
      const SizedBox(height: 22),
      TitreSection(accorder(f.echeances.length, 'Échéance', 'Échéances')),
      for (final e in f.echeances) ...[_CarteEcheance(e), const SizedBox(height: 10)],
      if (jsons(ex['affectations']).isNotEmpty || jsons(ex['avoirs']).isNotEmpty) ...[
        const SizedBox(height: 12),
        TitreSection(t('Ce qui a été payé')),
        GroupeLignes(
          retrait: 54,
          lignes: [
            for (final af in jsons(ex['affectations']))
              _LigneSimple(
                icone: af['avoir_id'] != null ? 'document' : 'piece',
                texte: af['avoir_id'] != null ? t('Avoir {id}', {'id': af['avoir_id']}) : t('Paiement {id}', {'id': af['paiement_id']}),
                detail: [
                  if (af['date_affectation'] != null) dateCourte(date(af['date_affectation'])!),
                  if (af['mode'] == 'AUTO_ANCIENNETE') t('affecté par ancienneté'),
                ].join(' · '),
                montant: entier(af['montant_affecte']),
              ),
          ],
        ),
      ],
      if (contestations.isNotEmpty || promesses.isNotEmpty || accords.isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Dossier')),
        GroupeLignes(
          retrait: 54,
          lignes: [
            for (final c in contestations)
              _LigneSimple(
                icone: 'drapeau',
                texte: c['statut'] == 'OUVERTE' ? t('Contestation ouverte') : t('Contestation close : {r}', {'r': resolution('${c['resolution']}')}),
                detail: '${c['motif'] ?? ''}',
              ),
            for (final p in promesses)
              _LigneSimple(
                icone: 'calendrier',
                texte: t('Promesse pour le {d}', {'d': dateCourte(date(p['date_promise']) ?? DateTime(2026))}),
                detail: [statutPromesse('${p['statut']}'), if (p['montant_promis'] != null) fcfa(entier(p['montant_promis']))].join(' · '),
                action: p['statut'] == 'EN_COURS' ? (t('Annuler'), () => _faire(() => annulerPromesse(context, '${p['id']}'))) : null,
              ),
            for (final ac in accords)
              _LigneSimple(
                icone: 'collection',
                texte: t('Échéancier en {n} tranches', {'n': ac['nb_tranches']}),
                detail: statutAccord('${ac['statut']}'),
                action: ac['statut'] == 'PROPOSE' && validateur ? (t('Décider'), () => _faire(() => deciderAccord(context, '${ac['id']}'))) : null,
              ),
          ],
        ),
      ],
      if (jsons(ex['relances']).isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Relances')),
        GroupeLignes(
          retrait: 16,
          lignes: [for (final r in jsons(ex['relances'])) LigneRelance(Relance(r), nomClient: false, onTap: () => ouvrir(context, 'relance/${r['id']}'))],
        ),
      ],
      if (jsons(ex['messages']).isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Réponses du client')),
        for (final m in jsons(ex['messages'])) ...[CarteMessage(Message(m)), const SizedBox(height: 10)],
      ],
      const SizedBox(height: 22),
      if (f.ouverte) ...[
        TitreSection(t('Actions')),
        GroupeLignes(
          retrait: 54,
          lignes: [
            LigneFeuille(
              icone: 'piece',
              texte: t('Enregistrer un paiement'),
              onTap: () => _faire(() => formulairePaiement(context, clientId: f.clientId, facture: f)),
            ),
            LigneFeuille(icone: 'document', texte: t('Enregistrer un avoir'), onTap: () => _faire(() => formulaireAvoir(context, f))),
            if (ouverte == null)
              LigneFeuille(icone: 'drapeau', texte: t('Ouvrir une contestation'), onTap: () => _faire(() => formulaireContestation(context, f))),
            if (ouverte != null && validateur)
              LigneFeuille(icone: 'drapeau', texte: t('Clore la contestation'), onTap: () => _faire(() => formulaireCloture(context, '${ouverte['id']}'))),
            LigneFeuille(icone: 'calendrier', texte: t('Noter une promesse de paiement'), onTap: () => _faire(() => formulairePromesse(context, f))),
            if (f.affecte == 0) LigneFeuille(icone: 'collection', texte: t('Proposer un échéancier'), onTap: () => _faire(() => formulaireAccord(context, f))),
          ],
        ),
        const SizedBox(height: 12),
      ],
      BoutonVerre(texte: t('Ouvrir le client'), icone: 'profil', onTap: () => ouvrir(context, 'client/${f.clientId}')),
      const SizedBox(height: 10),
      BoutonVerre(texte: t('Voir le journal de cette facture'), icone: 'journal', onTap: () => ouvrir(context, 'journal?objet=${f.id}')),
    ];
  }
}

class _CarteEcheance extends StatelessWidget {
  const _CarteEcheance(this.e);

  final Echeance e;

  @override
  Widget build(BuildContext context) => Plaque(
    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(t('Échéance {n} · {d}', {'n': e.rang, 'd': dateCourte(e.dateEcheance)}), style: Textes.libelle)),
            if (e.remplacee)
              PastilleStatut(Apparence(t('Remplacée'), 'retourner', Couleurs.discret), petite: true)
            else if (e.solde == 0)
              PastilleStatut(apparenceFacture('SOLDEE'), petite: true)
            else if (e.retard > 0)
              PastilleStatut(apparenceFacture('ECHUE', retard: e.retard), petite: true)
            else
              PastilleStatut(apparenceFacture('NON_ECHUE'), petite: true),
          ],
        ),
        const SizedBox(height: 6),
        LigneInfo(t('Dû'), fcfa(e.montantDu)),
        LigneInfo(t('Payé'), fcfa(e.affecte)),
        LigneInfo(t('Reste'), fcfa(e.solde), fort: true, couleur: e.solde > 0 ? null : Couleurs.succes),
      ],
    ),
  );
}

class _LigneSimple extends StatelessWidget {
  const _LigneSimple({required this.icone, required this.texte, this.detail, this.montant, this.action});

  final String icone;
  final String texte;
  final String? detail;
  final int? montant;
  final (String, VoidCallback)? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 12, 14, 12),
    child: Row(
      children: [
        Icone(icone, taille: 22, couleur: Couleurs.discret),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(texte, style: Textes.libelle),
              if (detail != null && detail!.isNotEmpty) Text(detail!, style: Textes.petit),
            ],
          ),
        ),
        if (montant != null)
          Text(
            fcfa(montant!),
            style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: Couleurs.texte),
          ),
        if (action != null)
          GestureDetector(
            onTap: action!.$2,
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.all(6),
              child: Text(action!.$1, style: Textes.lien),
            ),
          ),
      ],
    ),
  );
}
