// Les formulaires d une facture, chacun branche sur sa route : avoir (POST /api/avoirs),
// contestation (POST /api/contestations, cloture par le validateur), promesse (POST /api/promesses,
// annulation), echeancier (POST /api/accords, acceptation ou refus par le validateur). Chaque
// formulaire rend vrai si l action a eu lieu, pour que l ecran se relise.
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/feuille.dart';
import '../widgets/formulaires.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';

/// Le squelette commun : un titre, des champs, une erreur, un bouton qui envoie.
Future<bool> _formulaire(
  BuildContext context, {
  required String titre,
  required String bouton,
  required List<Widget> Function(void Function(void Function()) maj) champs,
  required Future<String?> Function() envoyer,
  String? succes,
  bool danger = false,
}) async {
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: titre,
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ...champs(maj),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: bouton,
              plein: !danger,
              teinte: danger ? TeinteVerre.rouge : null,
              enCours: enCours,
              onTap: () async {
                maj(() => (enCours, erreur) = (true, null));
                try {
                  final probleme = await envoyer();
                  if (probleme != null) return maj(() => (erreur, enCours) = (probleme, false));
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
  if (ok == true && succes != null && context.mounted) bulle(context, succes, icone: 'coche');
  return ok == true;
}

Future<bool> formulaireAvoir(BuildContext context, Facture f) {
  final montant = TextEditingController();
  final raison = TextEditingController();
  var quand = Donnees.instance.dateReference;
  return _formulaire(
    context,
    titre: t('Avoir sur {n}', {'n': f.numero}),
    bouton: t('Enregistrer l’avoir'),
    succes: t('Avoir enregistré.'),
    champs: (maj) => [
      ChampVerre(libelle: t('Montant (FCFA)'), icone: 'piece', controleur: montant, clavier: clavierMontant, indice: nombre(f.solde)),
      const SizedBox(height: 12),
      Libelle(t('Date')),
      ChampChoix(
        icone: 'calendrier',
        valeur: dateLongue(quand),
        indice: '',
        onTap: () async {
          final d = await choisirDate(context, initiale: quand);
          if (d != null) maj(() => quand = d);
        },
      ),
      const SizedBox(height: 12),
      ChampVerre(libelle: t('Motif'), icone: 'crayon', controleur: raison, indice: t('Remise commerciale, retour de marchandise…')),
      const SizedBox(height: 8),
      Text(t('Un avoir réduit ce que le client doit. S’il couvre le solde, les relances s’arrêtent.'), style: Textes.petit),
    ],
    envoyer: () async {
      final n = lireMontant(montant.text);
      if (n == null) return t('Saisissez un montant entier en FCFA.');
      if (raison.text.trim().isEmpty) return t('Indiquez le motif de l’avoir.');
      await Donnees.instance.ajouterAvoir(factureId: f.id, date: quand, montant: n, motif: raison.text.trim());
      return null;
    },
  );
}

Future<bool> formulaireContestation(BuildContext context, Facture f) {
  final raison = TextEditingController();
  return _formulaire(
    context,
    titre: t('Contester {n}', {'n': f.numero}),
    bouton: t('Ouvrir la contestation'),
    succes: t('Contestation ouverte : les relances de cette facture sont suspendues.'),
    champs: (maj) => [
      ChampVerre(libelle: t('Ce que le client conteste'), icone: 'drapeau', controleur: raison, lignes: 2, lignesMax: 4),
      const SizedBox(height: 8),
      Text(t('Les relances de la facture s’arrêtent jusqu’à la clôture par un validateur.'), style: Textes.petit),
    ],
    envoyer: () async {
      if (raison.text.trim().isEmpty) return t('Décrivez ce que le client conteste.');
      await Donnees.instance.ouvrirContestation(f.id, raison.text.trim());
      return null;
    },
  );
}

Future<bool> formulaireCloture(BuildContext context, String contestationId) {
  String? choix;
  final commentaire = TextEditingController();
  return _formulaire(
    context,
    titre: t('Clore la contestation'),
    bouton: t('Clore'),
    succes: t('Contestation close.'),
    champs: (maj) => [
      Libelle(t('Décision')),
      ChoixPastilles(valeurs: resolutionsContestation, choisie: choix, nom: resolution, onChoisi: (v) => maj(() => choix = v)),
      const SizedBox(height: 12),
      ChampVerre(libelle: t('Commentaire'), icone: 'crayon', controleur: commentaire, lignes: 2, lignesMax: 4),
      const SizedBox(height: 8),
      Text(t('Si la facture reste due, les relances reprennent.'), style: Textes.petit),
    ],
    envoyer: () async {
      if (choix == null) return t('Choisissez une décision.');
      if (commentaire.text.trim().isEmpty) return t('Le commentaire est obligatoire.');
      await Donnees.instance.cloturerContestation(contestationId, resolution: choix!, commentaire: commentaire.text.trim());
      return null;
    },
  );
}

Future<bool> formulairePromesse(BuildContext context, Facture f) {
  DateTime? quand;
  final montant = TextEditingController();
  return _formulaire(
    context,
    titre: t('Promesse sur {n}', {'n': f.numero}),
    bouton: t('Enregistrer la promesse'),
    succes: t('Promesse enregistrée : les relances attendent la date promise.'),
    champs: (maj) => [
      Libelle(t('Date promise')),
      ChampChoix(
        icone: 'calendrier',
        valeur: quand == null ? null : dateLongue(quand!),
        indice: t('Choisir la date'),
        onTap: () async {
          final d = await choisirDate(context, initiale: quand, min: Donnees.instance.dateReference);
          if (d != null) maj(() => quand = d);
        },
      ),
      const SizedBox(height: 12),
      ChampVerre(libelle: t('Montant promis (FCFA)'), icone: 'piece', controleur: montant, clavier: clavierMontant, facultatif: true),
      const SizedBox(height: 8),
      Text(t('Au-delà de 30 jours, seul un validateur peut l’enregistrer.'), style: Textes.petit),
    ],
    envoyer: () async {
      if (quand == null) return t('Choisissez la date promise.');
      await Donnees.instance.creerPromesse(f.id, quand!, montant.text.trim().isEmpty ? null : lireMontant(montant.text));
      return null;
    },
  );
}

Future<bool> annulerPromesse(BuildContext context, String id) async {
  final oui = await confirmer(
    context,
    titre: t('Annuler la promesse ?'),
    texte: t('Les relances reprendront pour cette facture.'),
    action: t('Annuler la promesse'),
    icone: 'calendrier',
  );
  if (!oui) return false;
  try {
    await Donnees.instance.annulerPromesse(id);
    return true;
  } on ApiErreur catch (e) {
    if (context.mounted) bulle(context, e.message, icone: 'alerte');
    return false;
  }
}

/// Un echeancier : au moins deux tranches, dont la somme fait le montant TTC, a des dates
/// croissantes (regles du back-end). On part de deux tranches egales, un mois d ecart.
Future<bool> formulaireAccord(BuildContext context, Facture f) {
  final ref = Donnees.instance.dateReference;
  final moitie = f.montantTtc ~/ 2;
  final tranches = <(DateTime, TextEditingController)>[
    (DateTime(ref.year, ref.month + 1, ref.day), TextEditingController(text: nombre(moitie))),
    (DateTime(ref.year, ref.month + 2, ref.day), TextEditingController(text: nombre(f.montantTtc - moitie))),
  ];
  return _formulaire(
    context,
    titre: t('Échéancier pour {n}', {'n': f.numero}),
    bouton: t('Proposer l’échéancier'),
    succes: t('Échéancier proposé : un validateur doit l’accepter.'),
    champs: (maj) => [
      Text(t('Total à répartir : {m}', {'m': fcfa(f.montantTtc)}), style: Textes.libelle),
      const SizedBox(height: 10),
      for (var i = 0; i < tranches.length; i++) ...[
        Row(
          children: [
            Expanded(
              child: ChampChoix(
                icone: 'calendrier',
                valeur: dateCourte(tranches[i].$1),
                indice: '',
                onTap: () async {
                  final d = await choisirDate(context, initiale: tranches[i].$1, min: ref);
                  if (d != null) maj(() => tranches[i] = (d, tranches[i].$2));
                },
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: ChampVerre(icone: 'piece', controleur: tranches[i].$2, clavier: clavierMontant),
            ),
          ],
        ),
        const SizedBox(height: 8),
      ],
      Row(
        children: [
          if (tranches.length < 12)
            Lien(
              t('Ajouter une tranche'),
              onTap: () => maj(() {
                final derniere = tranches.last.$1;
                tranches.add((DateTime(derniere.year, derniere.month + 1, derniere.day), TextEditingController()));
              }),
            ),
          const Spacer(),
          if (tranches.length > 2) Lien(t('Retirer la dernière'), discret: true, onTap: () => maj(tranches.removeLast)),
        ],
      ),
    ],
    envoyer: () async {
      final liste = [for (final (d, c) in tranches) (d, lireMontant(c.text) ?? 0)];
      if (liste.any((x) => x.$2 <= 0)) return t('Chaque tranche a besoin d’un montant.');
      final somme = liste.fold(0, (s, x) => s + x.$2);
      if (somme != f.montantTtc) return t('La somme des tranches ({s}) doit faire {m}.', {'s': fcfa(somme), 'm': fcfa(f.montantTtc)});
      await Donnees.instance.proposerAccord(f.id, liste);
      return null;
    },
  );
}

/// Le validateur accepte (les echeances sont remplacees) ou refuse un echeancier propose.
Future<bool> deciderAccord(BuildContext context, String id) async {
  final choix = await montrerFeuille<bool>(
    context,
    titre: t('Échéancier proposé'),
    contenu: (f) => Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            t('Accepté, il remplace les échéances de la facture (les anciennes restent dans l’historique).'),
            style: Textes.discret.copyWith(fontSize: 14.5),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: BoutonVerre(texte: t('Refuser'), onTap: () => Navigator.pop(f, false)),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: BoutonVerre(texte: t('Accepter'), plein: true, onTap: () => Navigator.pop(f, true)),
              ),
            ],
          ),
        ],
      ),
    ),
  );
  if (choix == null) return false;
  try {
    choix ? await Donnees.instance.accepterAccord(id) : await Donnees.instance.refuserAccord(id);
    if (context.mounted) bulle(context, choix ? t('Échéancier accepté.') : t('Échéancier refusé.'), icone: 'coche');
    return true;
  } on ApiErreur catch (e) {
    if (context.mounted) bulle(context, e.message, icone: 'alerte');
    return false;
  }
}
