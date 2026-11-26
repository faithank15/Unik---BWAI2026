// Les relances (GET /api/relances) par statut, le detail d une relance (lignes, apercu du message,
// historique ; validation par le validateur), la boite d envoi simulee (GET /api/canaux/envois :
// le texte exact parti chez le client) et les relances suspendues avec leur motif
// (GET /api/relances/suspensions).
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
import '../widgets/page.dart';
import '../widgets/verre.dart';
import 'fiche_client.dart';

/// Un ecran qui lit une liste a l ouverture (les listes longues ne sont pas gardees en memoire).
abstract class _EtatListe<W extends StatefulWidget, T> extends State<W> {
  List<T>? liste;
  String? erreur;

  Future<List<T>> lire();

  @override
  void initState() {
    super.initState();
    charger();
  }

  Future<void> charger() async {
    try {
      final l = await lire();
      if (!mounted) return;
      setState(() {
        liste = l;
        erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => erreur = e.message);
    }
  }

  List<Widget> etat(List<Widget> Function(List<T>) contenu) => [
    if (liste == null && erreur != null) EtatErreur(message: erreur!, onReessayer: charger) else if (liste == null) const Attente() else ...contenu(liste!),
  ];
}

class EcranRelances extends StatefulWidget {
  const EcranRelances({super.key});

  @override
  State<EcranRelances> createState() => _EcranRelancesState();
}

class _EcranRelancesState extends _EtatListe<EcranRelances, Relance> {
  var _onglet = 0;

  static final _groupes = <(String, Set<String>)>[
    (t('À venir'), {'EN_ATTENTE_VALIDATION', 'PLANIFIEE'}),
    (t('Envoyées'), {'ENVOYEE_SIM'}),
    (t('Arrêtées'), {'ANNULEE', 'SAUTEE', 'ABSORBEE', 'REJETEE'}),
  ];

  @override
  Future<List<Relance>> lire() async => (await Donnees.instance.relances()).reversed.toList();

  @override
  Widget build(BuildContext context) => PageFaktu(
    titre: t('Relances'),
    retour: true,
    rafraichir: false,
    enfants: [
      Row(
        children: [
          for (final (i, (nom, _)) in _groupes.indexed) ...[
            if (i > 0) const SizedBox(width: 8),
            Pastille(texte: nom, retenue: _onglet == i, onTap: () => setState(() => _onglet = i)),
          ],
        ],
      ),
      const SizedBox(height: 16),
      ...etat((tout) {
        final statuts = _groupes[_onglet].$2;
        final l = tout.where((r) => statuts.contains(r.statut)).toList();
        return [
          if (l.isEmpty)
            EtatVide(icone: 'envoyer', titre: t('Aucune relance dans cette liste'))
          else
            GroupeLignes(retrait: 16, lignes: [for (final r in l.take(150)) LigneRelance(r, onTap: () => ouvrir(context, 'relance/${r.id}'))]),
          const SizedBox(height: 18),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(
              t(
                'Calendrier : un rappel 3 jours avant l’échéance, puis la 1re relance le lendemain, la 2e à 7 jours et la 3e à 15 jours. Jamais le dimanche ni un jour férié, et au moins 2 jours entre deux messages.',
              ),
              style: Textes.petit,
            ),
          ),
        ];
      }),
    ],
  );
}

class EcranRelance extends StatefulWidget {
  const EcranRelance({super.key, required this.id});

  final String id;

  @override
  State<EcranRelance> createState() => _EcranRelanceState();
}

class _EcranRelanceState extends State<EcranRelance> {
  Relance? _r;
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    try {
      final r = await Donnees.instance.relance(widget.id);
      if (!mounted) return;
      setState(() {
        _r = r;
        _erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  Future<void> _decider(bool envoyer) async {
    if (!envoyer &&
        !await confirmer(
          context,
          titre: t('Ne pas envoyer cette relance ?'),
          texte: t('Le client ne la recevra pas. Ce choix est inscrit au journal.'),
          action: t('Ne pas envoyer'),
          icone: 'fermer',
        )) {
      return;
    }
    try {
      envoyer ? await Donnees.instance.validerRelance(widget.id) : await Donnees.instance.rejeterRelance(widget.id);
      if (mounted) bulle(context, envoyer ? t('Relance validée et envoyée au client.') : t('Relance annulée : elle ne sera pas envoyée.'), icone: 'coche');
      await _charger();
    } on ApiErreur catch (e) {
      if (mounted) bulle(context, e.message, icone: 'alerte');
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _r;
    return PageFaktu(
      titre: r == null ? t('Relance') : etape(r.etape),
      sousTitre: r == null ? null : Donnees.instance.nomClient(r.clientId),
      retour: true,
      rafraichir: false,
      enfants: [
        if (r == null && _erreur != null)
          EtatErreur(message: _erreur!, onReessayer: _charger)
        else if (r == null)
          const Attente()
        else ...[
          Plaque(
            rayon: Mesures.rayonCarte,
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [PastilleStatut(apparenceRelance(r.statut)), const Spacer(), if (r.statut == 'ENVOYEE_SIM') const MentionSimulation()]),
                const SizedBox(height: 10),
                LigneInfo(t('Canal'), canal(r.canal)),
                LigneInfo(t('Origine'), r.manuelle ? t('Relance manuelle, hors calendrier') : t('Calendrier des relances')),
                if (r.datePrevue != null) LigneInfo(t('Prévue le'), dateLongue(r.datePrevue!)),
                if (r.dateEnvoi != null) LigneInfo(t('Envoyée le'), dateLongue(r.dateEnvoi!)),
                if (r.motif != null) LigneInfo(t('Motif'), motif(r.motif)),
                if (r.totalSolde > 0) LigneInfo(t('Total du message'), fcfa(r.totalSolde), fort: true),
              ],
            ),
          ),
          if (r.lignes.isNotEmpty) ...[
            const SizedBox(height: 22),
            TitreSection(accorder(r.lignes.length, 'Facture relancée', 'Factures relancées')),
            GroupeLignes(
              retrait: 16,
              lignes: [
                for (final l in r.lignes)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('${l['facture_numero'] ?? l['echeance_id']}', style: Textes.libelle),
                              Text([etape('${l['etape_echeance']}'), if (l['decision'] != null) lisible('${l['decision']}')].join(' · '), style: Textes.petit),
                            ],
                          ),
                        ),
                        Text(fcfa(entier(l['solde'])), style: Textes.libelle),
                      ],
                    ),
                  ),
              ],
            ),
          ],
          if (r.apercu != null) ...[const SizedBox(height: 22), TitreSection(t('Texte envoyé au client')), _Bulle(r.apercu!)],
          if (r.statut == 'EN_ATTENTE_VALIDATION') ...[
            const SizedBox(height: 18),
            if (Donnees.instance.validateur)
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  BoutonVerre(texte: t('Valider et envoyer'), plein: true, onTap: () => _decider(true)),
                  const SizedBox(height: 8),
                  BoutonVerre(texte: t('Ne pas envoyer'), teinte: TeinteVerre.rouge, onTap: () => _decider(false)),
                ],
              )
            else
              Text(t('Seul un validateur peut envoyer cette relance.'), style: Textes.petit),
          ],
          if (r.historique.isNotEmpty) ...[
            const SizedBox(height: 22),
            TitreSection(t('Historique')),
            GroupeLignes(
              retrait: 16,
              lignes: [
                for (final h in r.historique)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
                    child: Row(
                      children: [
                        Expanded(child: Text(evenement('${h['type_evenement']}'), style: Textes.libelle)),
                        Text(acteur('${h['acteur_type']}'), style: Textes.petit),
                      ],
                    ),
                  ),
              ],
            ),
          ],
          const SizedBox(height: 22),
          BoutonVerre(texte: t('Ouvrir le client'), icone: 'profil', onTap: () => ouvrir(context, 'client/${r.clientId}')),
        ],
      ],
    );
  }
}

/// Le texte d un message, comme une bulle : ce que le client recoit.
class _Bulle extends StatelessWidget {
  const _Bulle(this.texte);

  final String texte;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
    decoration: BoxDecoration(color: Couleurs.secondaire, borderRadius: BorderRadius.circular(Mesures.rayonCarte)),
    child: Text(texte.replaceAll('\r\n', '\n'), style: Textes.corps.copyWith(fontSize: 14.5)),
  );
}

class EcranEnvois extends StatefulWidget {
  const EcranEnvois({super.key});

  @override
  State<EcranEnvois> createState() => _EcranEnvoisState();
}

class _EcranEnvoisState extends _EtatListe<EcranEnvois, Envoi> {
  @override
  Future<List<Envoi>> lire() => Donnees.instance.envois();

  @override
  Widget build(BuildContext context) => PageFaktu(
    titre: t('Messages envoyés'),
    sousTitre: t('Envois simulés : aucun message n’a réellement été envoyé'),
    retour: true,
    rafraichir: false,
    enfants: etat(
      (l) => [
        if (l.isEmpty)
          EtatVide(icone: 'enveloppe', titre: t('Aucun message envoyé pour le moment'))
        else
          for (final e in l.take(80)) ...[
            Plaque(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icone(iconeCanal(e.canal), taille: 18, couleur: Couleurs.discret),
                      const SizedBox(width: 8),
                      Expanded(
                        child: GestureDetector(
                          onTap: () => ouvrir(context, 'relance/${e.relanceId}'),
                          child: Text(Donnees.instance.nomClient(e.clientId), maxLines: 1, overflow: TextOverflow.ellipsis, style: Textes.libelle),
                        ),
                      ),
                      if (e.dateEnvoi != null) Text(dateCourte(e.dateEnvoi!), style: Textes.petit),
                    ],
                  ),
                  Text(e.destinataire, style: Textes.petit),
                  if (e.objet != null) ...[const SizedBox(height: 6), Text(e.objet!, style: Textes.libelle)],
                  const SizedBox(height: 8),
                  _Bulle(e.contenu),
                ],
              ),
            ),
            const SizedBox(height: 10),
          ],
      ],
    ),
  );
}

class EcranSuspensions extends StatefulWidget {
  const EcranSuspensions({super.key});

  @override
  State<EcranSuspensions> createState() => _EcranSuspensionsState();
}

class _EcranSuspensionsState extends _EtatListe<EcranSuspensions, Json> {
  @override
  Future<List<Json>> lire() => Donnees.instance.suspensions();

  @override
  Widget build(BuildContext context) {
    final gain = json(Donnees.instance.comparaison?['gain']);
    final ref = json(Donnees.instance.comparaison?['reference']);
    return PageFaktu(
      titre: t('Relances suspendues'),
      retour: true,
      rafraichir: false,
      enfants: [
        Plaque(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t('Comparé à une relance de toutes les factures échues'), style: Textes.libelle),
              const SizedBox(height: 6),
              LigneInfo(t('Relances avec la règle simple'), nombre(entier(ref['nb_relances_naives']))),
              LigneInfo(t('Dont injustifiées'), nombre(entier(ref['nb_relances_injustifiees'])), couleur: Couleurs.erreur),
              LigneInfo(t('Évitées par Faktu'), nombre(entier(gain['relances_injustifiees_evitees'])), couleur: Couleurs.succes, fort: true),
              if (entier(gain['messages_economises_par_le_regroupement']) > 0)
                LigneInfo(t('Messages économisés en regroupant'), nombre(entier(gain['messages_economises_par_le_regroupement']))),
            ],
          ),
        ),
        const SizedBox(height: 22),
        ...etat(
          (l) => [
            if (l.isEmpty)
              EtatVide(icone: 'coche', titre: t('Aucune relance suspendue'))
            else
              GroupeLignes(
                retrait: 16,
                lignes: [
                  for (final s in l)
                    InkWell(
                      onTap: () => ouvrir(context, 'facture/${s['facture_id']}'),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(Donnees.instance.nomClient('${s['client_id']}'), maxLines: 1, overflow: TextOverflow.ellipsis, style: Textes.libelle),
                                  Text('${s['facture_numero']} · ${motif('${s['motif']}')}', style: Textes.petit),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(fcfa(entier(s['solde'])), style: Textes.libelle),
                            const SizedBox(width: 4),
                            Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
          ],
        ),
      ],
    );
  }
}
