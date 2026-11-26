// A revoir : tout ce que le systeme ne decide pas seul. D abord les reponses « à classer » (l IA
// etait indisponible, scenario S23), puis la file de revue (GET /api/revue, la plus urgente en
// haut). Chaque type de dossier a sa vraie action dans le back-end :
//   GROS_MONTANT        -> valider ou rejeter la relance (validateur)
//   LITIGE              -> clore la contestation (validateur)
//   reponse d un client -> confirmer ou corriger la categorie (valider-categorie)
//   PAIEMENT_AMBIGU     -> affecter le paiement aux echeances
//   CANAL_INVALIDE, CONSENTEMENT_ABSENT -> corriger le contact
//   ESCALADE            -> noter la decision prise hors du systeme (validateur)
// et « Sans suite » (POST /api/revue/{id}/resoudre) quand rien d autre n est a faire.
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/faktu.dart';
import '../widgets/feuille.dart';
import '../widgets/formulaires.dart';
import '../widgets/icone.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';
import 'actions_facture.dart';
import 'fiche_client.dart';

class EcranARevoir extends StatefulWidget {
  const EcranARevoir({super.key});

  @override
  State<EcranARevoir> createState() => _EcranARevoirState();
}

class _EcranARevoirState extends State<EcranARevoir> {
  String? _type;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: Donnees.instance,
    builder: (context, _) {
      final d = Donnees.instance;
      final types = {for (final r in d.revue) r.type}.toList();
      final liste = d.revue.where((r) => _type == null || r.type == _type).toList();
      final total = d.revue.length + d.messagesAClasser.length;
      return PageFaktu(
        titre: t('À revoir'),
        sousTitre: total == 0 ? null : accorder(total, '{n} dossier attend une personne', '{n} dossiers attendent une personne'),
        enfants: [
          if (d.tableau == null && d.erreur != null)
            EtatErreur(message: d.erreur!, onReessayer: () => d.rafraichir(force: true))
          else if (d.tableau == null)
            const Attente()
          else if (total == 0)
            EtatVide(icone: 'coche', titre: t('Rien à revoir'), texte: t('Les dossiers qui demandent une décision arriveront ici.'))
          else ...[
            if (d.messagesAClasser.isNotEmpty) ...[
              TitreSection(accorder(d.messagesAClasser.length, '{n} réponse à classer', '{n} réponses à classer')),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 10),
                child: Text(t('L’IA n’a pas pu les classer. Leurs relances sont suspendues en attendant.'), style: Textes.petit),
              ),
              for (final m in d.messagesAClasser) ...[_CarteAClasser(m), const SizedBox(height: 12)],
              const SizedBox(height: 10),
            ],
            if (d.revue.isNotEmpty) ...[
              if (d.messagesAClasser.isNotEmpty) TitreSection(t('File de revue')),
              if (types.length > 1) ...[
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  clipBehavior: Clip.none,
                  child: Row(
                    children: [
                      Pastille(texte: t('Tous'), retenue: _type == null, onTap: () => setState(() => _type = null)),
                      for (final ty in types) ...[
                        const SizedBox(width: 8),
                        Pastille(texte: typeRevue(ty), retenue: _type == ty, onTap: () => setState(() => _type = ty)),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 14),
              ],
              for (final r in liste) ...[CarteRevue(r, key: ValueKey(r.id)), const SizedBox(height: 12)],
            ],
          ],
        ],
      );
    },
  );
}

/// Une reponse que l IA n a pas classee : relancer l IA, ou la classer a la main.
class _CarteAClasser extends StatelessWidget {
  const _CarteAClasser(this.m);

  final Message m;

  @override
  Widget build(BuildContext context) => Plaque(
    rayon: Mesures.rayonCarte,
    padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        GestureDetector(
          onTap: () => ouvrir(context, 'client/${m.clientId}'),
          child: Text(Donnees.instance.nomClient(m.clientId), style: Textes.lien),
        ),
        const SizedBox(height: 8),
        CarteMessage(m),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: BoutonVerre(
                texte: t('Relancer l’IA'),
                icone: 'etincelle',
                onTap: () async {
                  try {
                    await Donnees.instance.reclasser(m.id);
                    if (context.mounted) bulle(context, t('Classement demandé. Le résultat arrivera dans un instant.'), icone: 'etincelle');
                  } on ApiErreur catch (e) {
                    if (context.mounted) bulle(context, e.message, icone: 'alerte');
                  }
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: BoutonVerre(texte: t('Classer'), plein: true, onTap: () => classerMessage(context, m)),
            ),
          ],
        ),
      ],
    ),
  );
}

/// Un dossier de la file de revue. Son detail (l objet concerne) est lu une fois, a l affichage.
class CarteRevue extends StatefulWidget {
  const CarteRevue(this.r, {super.key});

  final ElementRevue r;

  @override
  State<CarteRevue> createState() => _CarteRevueState();
}

class _CarteRevueState extends State<CarteRevue> {
  Message? _message;
  Relance? _relance;
  Paiement? _paiement;

  ElementRevue get r => widget.r;

  @override
  void initState() {
    super.initState();
    _charger();
  }

  Future<void> _charger() async {
    final d = Donnees.instance;
    try {
      switch (r.objetType) {
        case 'MESSAGE':
          final m = await d.message(r.objetId);
          if (mounted) setState(() => _message = m);
        case 'RELANCE':
          final x = await d.relance(r.objetId);
          if (mounted) setState(() => _relance = x);
        case 'PAIEMENT':
          final p = await d.paiement(r.objetId);
          if (mounted) setState(() => _paiement = p);
      }
    } on ApiErreur {
      // Le detail manque : la carte garde le motif et les actions.
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = Donnees.instance;
    final peut = !r.reserveAuValidateur || d.validateur;
    final client = r.clientId ?? _paiement?.clientId ?? _relance?.clientId;
    return Plaque(
      rayon: Mesures.rayonCarte,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icone(iconeRevue(r.type), taille: 18, couleur: Couleurs.discret),
              const SizedBox(width: 8),
              Expanded(
                child: Text(typeRevue(r.type), style: Textes.petit.copyWith(fontWeight: FontWeight.w600)),
              ),
              if (r.creeLe != null) Text(dateCourte(r.creeLe!), style: Textes.petit),
            ],
          ),
          const SizedBox(height: 8),
          if (client != null && client.isNotEmpty)
            GestureDetector(
              onTap: () => ouvrir(context, 'client/$client'),
              child: Text(d.nomClient(client), style: Textes.sousTitre.copyWith(fontSize: 17.5)),
            )
          else
            Text(t('Client non identifié'), style: Textes.sousTitre.copyWith(fontSize: 17.5)),
          if (r.motif != null) ...[const SizedBox(height: 4), Text(_motifLisible(r), style: Textes.discret.copyWith(fontSize: 14.5))],
          ..._detail(context),
          const SizedBox(height: 14),
          if (!peut)
            Row(
              children: [
                Icone('cadenas', taille: 16, couleur: Couleurs.discret),
                const SizedBox(width: 8),
                Expanded(child: Text(t('Seul un validateur peut décider de ce dossier.'), style: Textes.petit)),
              ],
            )
          else
            ..._actions(context),
        ],
      ),
    );
  }

  String _motifLisible(ElementRevue r) {
    final m = r.motif!;
    if (r.type == 'GROS_MONTANT') return t('Plus de 500 000 FCFA dans un même message : validation avant l’envoi.');
    if (r.type == 'ESCALADE') return t('5 jours après la 3e relance, sans paiement ni réponse. Le système n’envoie plus rien.');
    return m;
  }

  List<Widget> _detail(BuildContext context) {
    if (_message != null) return [const SizedBox(height: 12), CarteMessage(_message!)];
    if (_relance != null) {
      final x = _relance!;
      return [
        const SizedBox(height: 10),
        LigneInfo(t('Relance'), '${etape(x.etape)} · ${canal(x.canal)}'),
        for (final l in x.lignes) LigneInfo('${l['facture_numero'] ?? l['echeance_id']}', fcfa(entier(l['solde']))),
        if (x.totalSolde > 0) LigneInfo(t('Total du message'), fcfa(x.totalSolde), fort: true),
      ];
    }
    if (_paiement != null) {
      final p = _paiement!;
      return [
        const SizedBox(height: 10),
        LigneInfo(t('Paiement'), '${modePaiement(p.mode)} · ${fcfa(p.montant)}'),
        if (p.reference != null) LigneInfo(t('Référence'), p.reference!),
        LigneInfo(t('À affecter'), fcfa(p.resteNonAffecte), fort: true),
      ];
    }
    if (r.objetType == 'FACTURE' || r.objetType == 'ECHEANCE') {
      return [
        const SizedBox(height: 6),
        Align(
          alignment: Alignment.centerLeft,
          child: Lien(t('Ouvrir la facture'), onTap: () => _ouvrirFacture(context)),
        ),
      ];
    }
    return const [];
  }

  Future<void> _ouvrirFacture(BuildContext context) async {
    final id = r.objetType == 'FACTURE' ? r.objetId : '${(await Donnees.instance.elementRevue(r.id)).objet['facture_id'] ?? ''}';
    if (id.isNotEmpty && context.mounted) ouvrir(context, 'facture/$id');
  }

  Future<void> _essayer(Future<void> Function() action, String succes) async {
    try {
      await action();
      if (mounted) bulle(context, succes, icone: 'coche');
    } on ApiErreur catch (e) {
      if (mounted) bulle(context, e.message, icone: 'alerte');
    }
  }

  List<Widget> _actions(BuildContext context) {
    final d = Donnees.instance;
    Widget deux(Widget a, Widget b) => Row(
      children: [
        Expanded(child: a),
        const SizedBox(width: 10),
        Expanded(child: b),
      ],
    );
    final sansSuite = BoutonVerre(texte: t('Sans suite'), onTap: () => resoudre(context, r));
    switch (r.type) {
      case 'GROS_MONTANT':
        return [
          deux(
            BoutonVerre(
              texte: t('Ne pas envoyer'),
              onTap: () async {
                if (await confirmer(
                  context,
                  titre: t('Ne pas envoyer cette relance ?'),
                  texte: t('Elle sera rejetée et inscrite au journal.'),
                  action: t('Rejeter'),
                  icone: 'fermer',
                )) {
                  await _essayer(() => d.rejeterRelance(r.objetId), t('Relance rejetée.'));
                }
              },
            ),
            BoutonVerre(
              texte: t('Envoyer'),
              plein: true,
              onTap: () => _essayer(() => d.validerRelance(r.objetId), t('Relance validée, revérifiée puis envoyée.')),
            ),
          ),
        ];
      case 'LITIGE':
        return [
          deux(
            sansSuite,
            BoutonVerre(
              texte: t('Clore'),
              plein: true,
              onTap: () async {
                final id = _message?.contestationId ?? await _contestationOuverte();
                if (id == null) {
                  if (context.mounted) bulle(context, t('Aucune contestation ouverte n’a été trouvée pour ce dossier.'), icone: 'alerte');
                  return;
                }
                if (context.mounted) await formulaireCloture(context, id);
              },
            ),
          ),
        ];
      case 'PAIEMENT_AMBIGU':
        return [deux(sansSuite, BoutonVerre(texte: t('Affecter'), plein: true, onTap: _paiement == null ? null : () => affecterPaiement(context, _paiement!)))];
      case 'CANAL_INVALIDE' || 'CONSENTEMENT_ABSENT':
        return [
          deux(
            BoutonVerre(
              texte: t('C’est corrigé'),
              onTap: () => resoudre(context, r, decision: 'CONTACT_CORRIGE'),
            ),
            BoutonVerre(
              texte: t('Modifier le contact'),
              plein: true,
              onTap: r.clientId == null
                  ? null
                  : () async {
                      final c = await d.client(r.clientId!);
                      if (context.mounted) await modifierContact(context, c);
                    },
            ),
          ),
        ];
      case 'ESCALADE':
        return [BoutonVerre(texte: t('Noter la décision'), plein: true, onTap: () => resoudre(context, r, escalade: true))];
      default:
        if (_message != null && !_message!.traite) {
          return [deux(sansSuite, BoutonVerre(texte: t('Classer'), plein: true, onTap: () => classerMessage(context, _message!)))];
        }
        return [sansSuite];
    }
  }

  Future<String?> _contestationOuverte() async {
    final detail = await Donnees.instance.elementRevue(r.id);
    final factureId = r.objetType == 'FACTURE' ? r.objetId : '${detail.objet['facture_id'] ?? detail.objet['facture_citee_id'] ?? ''}';
    if (factureId.isEmpty) return null;
    final ouvertes = await Donnees.instance.contestations(factureId: factureId, statut: 'OUVERTE');
    return ouvertes.isEmpty ? null : '${ouvertes.first['id']}';
  }
}

/// Classer un message a la main (POST /api/messages/{id}/valider-categorie) : la categorie, et
/// pour une promesse ou un delai, la date, le montant et la facture.
Future<void> classerMessage(BuildContext context, Message m) async {
  var choisie = m.categorieValidee ?? m.categorieIa;
  DateTime? quand = m.datePromise;
  final montant = TextEditingController(text: m.montantPromis == null ? '' : nombre(m.montantPromis!));
  final commentaire = TextEditingController();
  Facture? facture;
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: t('Que dit ce message ?'),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('« ${m.contenu} »', style: Textes.corps, maxLines: 4, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 12),
            ChoixPastilles(valeurs: categories, choisie: choisie, nom: categorie, onChoisi: (v) => maj(() => choisie = v)),
            if (choisie != null) ...[const SizedBox(height: 8), Text(suiteCategorie(choisie!), style: Textes.petit)],
            if (categoriesAvecDate.contains(choisie)) ...[
              const SizedBox(height: 12),
              Libelle(t('Date promise')),
              ChampChoix(
                icone: 'calendrier',
                valeur: quand == null ? null : dateLongue(quand!),
                indice: t('Choisir la date'),
                onTap: () async {
                  final x = await choisirDate(f, initiale: quand, min: Donnees.instance.dateReference);
                  if (x != null) maj(() => quand = x);
                },
              ),
              const SizedBox(height: 12),
              ChampVerre(libelle: t('Montant promis (FCFA)'), icone: 'piece', controleur: montant, clavier: clavierMontant, facultatif: true),
            ],
            if (categoriesAvecDate.contains(choisie) || choisie == 'CONTESTATION') ...[
              const SizedBox(height: 12),
              Libelle(t('Facture concernée'), facultatif: true),
              ChampChoix(
                icone: 'facture',
                valeur: facture?.numero ?? m.factureCitee,
                indice: t('Celle du message, ou la seule ouverte'),
                onTap: () async {
                  final x = await choisirFacture(f, m.clientId);
                  if (x != null) maj(() => facture = x);
                },
              ),
            ],
            const SizedBox(height: 12),
            ChampVerre(libelle: t('Commentaire'), icone: 'crayon', controleur: commentaire, facultatif: true),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Valider'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                if (choisie == null) return maj(() => erreur = t('Choisissez une catégorie.'));
                maj(() => (enCours, erreur) = (true, null));
                try {
                  await Donnees.instance.validerCategorie(
                    m.id,
                    categorie: choisie!,
                    datePromise: categoriesAvecDate.contains(choisie) ? quand : null,
                    montant: categoriesAvecDate.contains(choisie) && montant.text.trim().isNotEmpty ? lireMontant(montant.text) : null,
                    factureId: facture?.id,
                    commentaire: commentaire.text.trim().isEmpty ? null : commentaire.text.trim(),
                  );
                  if (f.mounted) Navigator.pop(f, true);
                } on ApiErreur catch (e) {
                  maj(() => (erreur, enCours) = (e.message, false));
                }
              },
            ),
          ],
        ),
      ),
    ),
  );
  if (ok == true && context.mounted) bulle(context, t('Classement enregistré dans le journal.'), icone: 'coche');
}

/// Affecter un paiement ambigu (POST /api/paiements/{id}/affecter) : le client s il manque, puis
/// le montant de chaque echeance ouverte (la plus ancienne d abord, jamais au-dela du reste).
Future<void> affecterPaiement(BuildContext context, Paiement p) async {
  final d = Donnees.instance;
  var clientId = p.clientId;
  if (clientId == null) {
    final c = await choisirClient(context);
    if (c == null) return;
    clientId = c.id;
  }
  final echeances = (await d.echeancesOuvertes(clientId))..sort((a, b) => a.dateEcheance.compareTo(b.dateEcheance));
  if (!context.mounted) return;
  if (echeances.isEmpty) {
    bulle(context, t('Ce client n’a aucune échéance ouverte.'), icone: 'alerte');
    return;
  }
  var reste = p.resteNonAffecte;
  final champs = <String, TextEditingController>{};
  for (final e in echeances) {
    final part = reste < e.solde ? reste : e.solde;
    reste -= part;
    champs[e.id] = TextEditingController(text: part > 0 ? nombre(part) : '');
  }
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: t('Affecter {m}', {'m': fcfa(p.resteNonAffecte)}),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(f).height * 0.7),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
          children: [
            Text(d.nomClient(clientId), style: Textes.libelle),
            const SizedBox(height: 10),
            for (final e in echeances) ...[
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('Échéance du {d}', {'d': dateCourte(e.dateEcheance)}), style: Textes.libelle),
                        Text(t('Reste {m}', {'m': fcfa(e.solde)}), style: Textes.petit),
                      ],
                    ),
                  ),
                  SizedBox(
                    width: 140,
                    child: ChampVerre(icone: 'piece', controleur: champs[e.id], clavier: clavierMontant),
                  ),
                ],
              ),
              const SizedBox(height: 8),
            ],
            ErreurFormulaire(erreur),
            const SizedBox(height: 12),
            BoutonVerre(
              texte: t('Affecter'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                final parts = {for (final e in champs.entries) e.key: lireMontant(e.value.text) ?? 0};
                if (parts.values.every((v) => v == 0)) return maj(() => erreur = t('Indiquez au moins un montant.'));
                maj(() => (enCours, erreur) = (true, null));
                try {
                  await d.affecterPaiement(p.id, parts);
                  if (f.mounted) Navigator.pop(f, true);
                } on ApiErreur catch (e) {
                  maj(() => (erreur, enCours) = (e.message, false));
                }
              },
            ),
          ],
        ),
      ),
    ),
  );
  if (ok == true && context.mounted) bulle(context, t('Paiement affecté.'), icone: 'piece');
}

/// Clore un dossier sans autre action (POST /api/revue/{id}/resoudre) : une decision et un
/// commentaire, gardes au journal. Pour une escalade : ce qui a ete decide hors du systeme.
Future<void> resoudre(BuildContext context, ElementRevue r, {String? decision, bool escalade = false}) async {
  final decisions = escalade
      ? const [
          ('APPEL_CLIENT', 'Appeler le client'),
          ('MISE_EN_DEMEURE', 'Mise en demeure'),
          ('ABANDON', 'Abandonner la créance'),
          ('SANS_SUITE', 'Sans suite'),
        ]
      : const [('SANS_SUITE', 'Sans suite')];
  var choisie = decision ?? decisions.first.$1;
  final commentaire = TextEditingController();
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: escalade ? t('Décision sur l’escalade') : t('Clore le dossier'),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (escalade) ...[
              ChoixPastilles(
                valeurs: [for (final x in decisions) x.$1],
                choisie: choisie,
                nom: (v) => t(decisions.firstWhere((x) => x.$1 == v).$2),
                onChoisi: (v) => maj(() => choisie = v),
              ),
              const SizedBox(height: 12),
            ],
            ChampVerre(libelle: t('Commentaire'), icone: 'crayon', controleur: commentaire, lignes: 2, lignesMax: 4, facultatif: !escalade),
            const SizedBox(height: 8),
            Text(t('La décision et le commentaire sont gardés dans le journal.'), style: Textes.petit),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Enregistrer'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                if (escalade && commentaire.text.trim().isEmpty) return maj(() => erreur = t('Expliquez la décision en quelques mots.'));
                maj(() => (enCours, erreur) = (true, null));
                try {
                  await Donnees.instance.resoudreRevue(r.id, choisie, commentaire: commentaire.text.trim().isEmpty ? null : commentaire.text.trim());
                  if (f.mounted) Navigator.pop(f, true);
                } on ApiErreur catch (e) {
                  maj(() => (erreur, enCours) = (e.message, false));
                }
              },
            ),
          ],
        ),
      ),
    ),
  );
  if (ok == true && context.mounted) bulle(context, t('Dossier clos.'), icone: 'coche');
}
