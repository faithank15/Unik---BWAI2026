// Le bouton du milieu : faire entrer quelque chose dans Faktu, a la main. Un paiement
// (POST /api/paiements), la reponse d un client (POST /api/messages), un lot de factures
// (POST /api/imports). Tout est simule (cahier, section 2) : l interface le dit.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
import '../widgets/page.dart';
import '../widgets/verre.dart';

Future<void> ouvrirAjouter(BuildContext context) => montrerFeuille<void>(
  context,
  titre: t('Ajouter'),
  contenu: (f) => CorpsFeuille(
    padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        LigneFeuille(
          icone: 'piece',
          texte: t('Enregistrer un paiement'),
          onTap: () {
            Navigator.pop(f);
            formulairePaiement(context);
          },
        ),
        LigneFeuille(
          icone: 'commentaire',
          texte: t('Ajouter la réponse d’un client'),
          onTap: () {
            Navigator.pop(f);
            formulaireMessage(context);
          },
        ),
        LigneFeuille(
          icone: 'telecharger',
          texte: t('Importer un portefeuille'),
          onTap: () {
            Navigator.pop(f);
            presenterImport(context);
          },
        ),
      ],
    ),
  ),
);

/// Un paiement simule. Sans client, il est enregistre sans affectation et part en revue
/// (scenario S05). La reference reste la meme tant que le formulaire est ouvert : un second envoi
/// est reconnu comme un rejeu, rien n est compte deux fois (S06).
Future<bool> formulairePaiement(BuildContext context, {String? clientId, Facture? facture}) async {
  final d = Donnees.instance;
  var client = clientId == null ? null : d.clients[clientId];
  var mode = 'MOBILE_MONEY';
  var quand = d.dateReference;
  final montant = TextEditingController(text: facture == null ? '' : nombre(facture.solde));
  final reference = TextEditingController(text: referenceFictive(mode));
  var referenceTouchee = false;
  String? erreur;
  var enCours = false;
  final r = await montrerFeuille<Paiement>(
    context,
    titre: t('Enregistrer un paiement'),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => CorpsFeuille(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (clientId == null) ...[
              Libelle(t('Client'), facultatif: true),
              ChampChoix(
                icone: 'profil',
                valeur: client?.nom,
                indice: t('Client non identifié'),
                onTap: () async {
                  final c = await choisirClient(f);
                  if (c != null) maj(() => client = c);
                },
              ),
              const SizedBox(height: 12),
            ],
            if (facture != null) ...[
              Text(t('Pour la facture {n}', {'n': facture.numero}), style: Textes.discret.copyWith(fontSize: 14.5)),
              const SizedBox(height: 12),
            ],
            ChampVerre(
              libelle: t('Montant (FCFA)'),
              icone: 'piece',
              controleur: montant,
              clavier: clavierMontant,
              autofocus: facture == null && clientId != null,
            ),
            const SizedBox(height: 12),
            Libelle(t('Mode de paiement')),
            ChoixPastilles(
              valeurs: modesPaiement,
              choisie: mode,
              nom: modePaiement,
              onChoisi: (v) => maj(() {
                mode = v;
                if (!referenceTouchee) reference.text = referenceFictive(v);
              }),
            ),
            const SizedBox(height: 12),
            Libelle(t('Date du paiement')),
            ChampChoix(
              icone: 'calendrier',
              valeur: dateLongue(quand),
              indice: '',
              onTap: () async {
                final x = await choisirDate(f, initiale: quand);
                if (x != null) maj(() => quand = x);
              },
            ),
            const SizedBox(height: 12),
            ChampVerre(libelle: t('Référence'), icone: 'document', controleur: reference, onChanged: (_) => referenceTouchee = true),
            const SizedBox(height: 8),
            Text(
              client == null
                  ? t('Sans client, le paiement est enregistré sans affectation et part en revue.')
                  : t('Paiement simulé. Sans facture indiquée, il est affecté aux échéances les plus anciennes.'),
              style: Textes.petit,
            ),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Enregistrer'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                final n = lireMontant(montant.text);
                if (n == null) return maj(() => erreur = t('Saisissez un montant entier en FCFA.'));
                if (reference.text.trim().isEmpty) return maj(() => erreur = t('Saisissez la référence du paiement.'));
                maj(() => (enCours, erreur) = (true, null));
                try {
                  final p = await d.ajouterPaiement(
                    clientId: client?.id,
                    date: quand,
                    montant: n,
                    mode: mode,
                    reference: reference.text.trim(),
                    factures: facture == null ? const [] : [facture.numero],
                  );
                  if (f.mounted) Navigator.pop(f, p);
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
  if (r == null) return false;
  if (context.mounted) {
    bulle(
      context,
      [
        r.dejaEnregistre ? t('Ce paiement était déjà enregistré : rien n’a été compté deux fois.') : t('Paiement de {m} enregistré.', {'m': fcfa(r.montant)}),
        if (r.resteNonAffecte > 0) t('{m} restent à affecter : retrouvez ce paiement dans À revoir.', {'m': fcfa(r.resteNonAffecte)}),
        if (r.relancesAnnulees.isNotEmpty) accorder(r.relancesAnnulees.length, '{n} relance annulée.', '{n} relances annulées.'),
      ].join(' '),
      icone: 'piece',
    );
  }
  return true;
}

/// La reponse d un client, simulee : le back-end la classe avec l IA (ou la laisse « à classer »
/// si l IA est indisponible, scenario S23).
Future<bool> formulaireMessage(BuildContext context, {String? clientId}) async {
  final d = Donnees.instance;
  var client = clientId == null ? null : d.clients[clientId];
  var canalChoisi = client?.canalPrefere ?? 'WHATSAPP';
  Facture? citee;
  final texte = TextEditingController();
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: t('Réponse d’un client'),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => CorpsFeuille(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (clientId == null) ...[
              Libelle(t('Client')),
              ChampChoix(
                icone: 'profil',
                valeur: client?.nom,
                indice: t('Choisir un client'),
                onTap: () async {
                  final c = await choisirClient(f);
                  if (c != null) maj(() => (client, canalChoisi, citee) = (c, c.canalPrefere, null));
                },
              ),
              const SizedBox(height: 12),
            ],
            Libelle(t('Canal de réception')),
            ChoixPastilles(
              valeurs: const ['WHATSAPP', 'EMAIL'],
              choisie: canalChoisi,
              nom: canal,
              icone: iconeCanal,
              onChoisi: (v) => maj(() => canalChoisi = v),
            ),
            const SizedBox(height: 12),
            ChampVerre(libelle: t('Texte du message'), icone: 'commentaire', controleur: texte, lignes: 3, lignesMax: 6),
            const SizedBox(height: 12),
            Libelle(t('Facture citée'), facultatif: true),
            ChampChoix(
              icone: 'facture',
              valeur: citee?.numero,
              indice: t('Aucune facture citée'),
              onTap: () async {
                if (client == null) return maj(() => erreur = t('Choisissez d’abord le client pour voir ses factures.'));
                final x = await choisirFacture(f, client!.id);
                if (x != null) maj(() => citee = x);
              },
            ),
            const SizedBox(height: 8),
            Text(t('L’IA propose une catégorie. Sous le seuil de confiance, ou pour un cas sensible, une personne décide.'), style: Textes.petit),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Ajouter la réponse'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                if (client == null) return maj(() => erreur = t('Choisissez un client.'));
                if (texte.text.trim().isEmpty) return maj(() => erreur = t('Écrivez ou collez le message du client.'));
                maj(() => (enCours, erreur) = (true, null));
                try {
                  await d.ajouterMessage(clientId: client!.id, canal: canalChoisi, contenu: texte.text.trim(), factureCitee: citee?.numero);
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
  if (ok == true && context.mounted) bulle(context, t('Réponse ajoutée. Si elle demande une décision, elle s’affichera dans À revoir.'), icone: 'commentaire');
  return ok == true;
}

const _fichiers = MethodChannel('bj.faktu/fichiers');

/// Les fichiers d un lot (document de donnees) : trois obligatoires, deux facultatifs.
const _champsLot = ['clients', 'factures', 'echeances', 'preferences_contact', 'accords_echeancier'];
const _obligatoires = {'clients', 'factures', 'echeances'};

/// Avant le selecteur de fichiers : ce qu un portefeuille contient, pour choisir les bons fichiers.
Future<void> presenterImport(BuildContext context) => montrerFeuille<void>(
  context,
  titre: t('Importer un portefeuille'),
  contenu: (f) => CorpsFeuille(
    padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          t(
            'Ajoutez vos clients et ce qu’ils vous doivent à partir de fichiers CSV, exportés de votre logiciel de gestion ou d’un tableur. Faktu calcule ensuite les retards et prépare les relances.',
          ),
          style: Textes.corps,
        ),
        const SizedBox(height: 14),
        Libelle(t('Sélectionnez ensemble')),
        LigneInfo('clients.csv', t('Obligatoire')),
        LigneInfo('factures.csv', t('Obligatoire')),
        LigneInfo('echeances.csv', t('Obligatoire')),
        LigneInfo('preferences_contact.csv', t('Facultatif')),
        LigneInfo('accords_echeancier.csv', t('Facultatif')),
        const SizedBox(height: 8),
        Text(
          t(
            'Les lignes valides sont ajoutées. Les lignes en erreur sont listées avec leur motif, pour les corriger. Importer deux fois les mêmes fichiers n’ajoute rien en double.',
          ),
          style: Textes.petit,
        ),
        const SizedBox(height: 16),
        BoutonVerre(
          texte: t('Choisir les fichiers'),
          icone: 'telecharger',
          plein: true,
          onTap: () {
            Navigator.pop(f);
            importer(context);
          },
        ),
      ],
    ),
  ),
);

/// Importer un lot : on choisit ses fichiers CSV d un coup ; chacun est reconnu a son nom
/// (clients.csv, factures.csv, echeances.csv…). Rejouer le meme lot ne cree aucun doublon (S01).
Future<void> importer(BuildContext context) async {
  List<Object?>? choix;
  try {
    choix = await _fichiers.invokeListMethod<Object?>('choisirCsv');
  } on PlatformException {
    if (context.mounted) bulle(context, t('Impossible d’ouvrir les fichiers du téléphone. Réessayez.'), icone: 'alerte');
    return;
  } on MissingPluginException {
    return;
  }
  if (choix == null || choix.isEmpty || !context.mounted) return;
  final lot = <String, (String, List<int>)>{};
  for (final x in choix) {
    final m = json(x);
    final nom = '${m['nom']}';
    final octets = m['octets'];
    final champ = _champsLot.where((c) => nom.toLowerCase().replaceAll('é', 'e').startsWith(c)).firstOrNull;
    if (champ != null && octets is List<int>) lot[champ] = (nom, octets);
  }
  final manquants = _obligatoires.where((c) => !lot.containsKey(c)).toList();
  if (manquants.isNotEmpty) {
    bulle(
      context,
      t('Il manque {f}. Sélectionnez clients.csv, factures.csv et echeances.csv ensemble.', {'f': manquants.map((m) => '$m.csv').join(', ')}),
      icone: 'alerte',
    );
    return;
  }
  try {
    final r = await Donnees.instance.importer(lot);
    if (context.mounted) await _montrerRapport(context, r);
  } on ApiErreur catch (e) {
    if (context.mounted) bulle(context, e.message, icone: 'alerte');
  }
}

/// Le rapport d import : ce qui est entre, et chaque rejet avec son fichier, sa ligne et son motif.
Future<void> _montrerRapport(BuildContext context, Json r) {
  final rejets = jsons(r['rejets']);
  final acceptees = entier(r['nb_acceptees']);
  final deja = r['deja_importe'] == true || r['statut'] == 'DEJA_IMPORTE';
  return montrerFeuille<void>(
    context,
    titre: deja ? t('Portefeuille déjà importé') : t('Portefeuille importé'),
    contenu: (f) => ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(f).height * 0.65),
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        children: [
          if (deja)
            Text(t('Ces fichiers ont déjà été importés. Rien n’a été ajouté en double.'), style: Textes.corps)
          else
            Row(
              children: [
                Expanded(
                  child: CarteChiffre(
                    valeur: nombre(acceptees),
                    libelle: accorder(acceptees, 'ligne acceptée', 'lignes acceptées'),
                    icone: 'coche',
                    couleur: Couleurs.succes,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: CarteChiffre(
                    valeur: nombre(rejets.length),
                    libelle: accorder(rejets.length, 'ligne rejetée', 'lignes rejetées'),
                    icone: 'alerte',
                    couleur: rejets.isEmpty ? null : Couleurs.erreur,
                  ),
                ),
              ],
            ),
          if (rejets.isNotEmpty) ...[
            const SizedBox(height: 14),
            GroupeLignes(
              retrait: 16,
              lignes: [
                for (final x in rejets)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(t('{f}, ligne {n}', {'f': x['fichier'], 'n': x['ligne']}), style: Textes.libelle),
                        Text(motifRejet('${x['motif_code']}'), style: Textes.petit.copyWith(color: Couleurs.texte)),
                        if (x['detail'] != null) Text('${x['detail']}', style: Textes.petit),
                      ],
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    ),
  );
}
