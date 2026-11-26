// Les pieces des formulaires de saisie (paiement, avoir, message, promesse, echeancier…) : un
// choix de client, de facture, une date, un montant, des pastilles. Tout ce que le back-end
// attend se saisit a la main, avec les memes composants de verre que Discover.
import 'package:flutter/cupertino.dart' show CupertinoDatePicker, CupertinoDatePickerMode, CupertinoTheme, CupertinoThemeData, CupertinoTextThemeData;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import 'champ.dart';
import 'feuille.dart';
import 'icone.dart';
import 'verre.dart';

/// « 1 250 000 », « 1250000 » ou « 1.250.000 » : l entier saisi, sinon nul.
int? lireMontant(String texte) {
  final chiffres = texte.replaceAll(RegExp(r'[\s.  ]'), '');
  final n = int.tryParse(chiffres);
  return n == null || n <= 0 ? null : n;
}

/// Le libelle d un champ, au-dessus de lui (comme ChampVerre).
class Libelle extends StatelessWidget {
  const Libelle(this.texte, {super.key, this.facultatif = false});

  final String texte;
  final bool facultatif;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Text.rich(
      TextSpan(
        text: texte,
        style: Textes.libelle,
        children: [
          if (facultatif)
            TextSpan(
              text: '  ${t('facultatif')}',
              style: Textes.petit.copyWith(fontWeight: FontWeight.w400),
            ),
        ],
      ),
    ),
  );
}

/// Un champ qui ouvre un choix (client, facture, date) : la valeur, ou l invitation a choisir.
class ChampChoix extends StatelessWidget {
  const ChampChoix({super.key, required this.icone, required this.valeur, required this.indice, required this.onTap, this.erreur = false});

  final String icone;
  final String? valeur;
  final String indice;
  final VoidCallback onTap;
  final bool erreur;

  @override
  Widget build(BuildContext context) => Appuyable(
    semantique: valeur ?? indice,
    onTap: onTap,
    child: Container(
      decoration: BoxDecoration(
        color: Couleurs.plaque,
        borderRadius: BorderRadius.circular(Mesures.rayonBouton + 2),
        border: Border.all(color: erreur ? Couleurs.erreur : Colors.transparent, width: 2),
      ),
      padding: const EdgeInsets.fromLTRB(14, 13, 12, 13),
      child: Row(
        children: [
          Icone(icone, taille: 20, couleur: Couleurs.discret),
          const SizedBox(width: 12),
          Expanded(child: Text(valeur ?? indice, style: valeur == null ? Textes.discret : Textes.libelle)),
          Icone('chevron-bas', taille: 18, couleur: Couleurs.chevron),
        ],
      ),
    ),
  );
}

/// Choisir une date dans une feuille (la roue d iOS, comme le reste de l application). Par
/// defaut : la date de reference.
Future<DateTime?> choisirDate(BuildContext context, {DateTime? initiale, DateTime? min}) async {
  var choisie = initiale ?? Donnees.instance.dateReference;
  final ok = await montrerFeuille<bool>(
    context,
    titre: t('Choisir une date'),
    contenu: (f) => CorpsFeuille(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            height: 190,
            child: CupertinoTheme(
              data: CupertinoThemeData(
                brightness: Couleurs.sombre ? Brightness.dark : Brightness.light,
                textTheme: CupertinoTextThemeData(dateTimePickerTextStyle: Textes.corps.copyWith(fontSize: 20)),
              ),
              child: CupertinoDatePicker(
                mode: CupertinoDatePickerMode.date,
                initialDateTime: choisie,
                minimumDate: min,
                maximumDate: DateTime(2028, 12, 31),
                onDateTimeChanged: (d) => choisie = DateTime(d.year, d.month, d.day),
              ),
            ),
          ),
          const SizedBox(height: 12),
          BoutonVerre(texte: t('Choisir'), plein: true, onTap: () => Navigator.pop(f, true)),
        ],
      ),
    ),
  );
  return ok == true ? choisie : null;
}

/// Choisir dans une liste longue (clients, factures), avec une recherche en haut.
Future<T?> choisirDansListe<T>(
  BuildContext context, {
  required String titre,
  required List<T> elements,
  required String Function(T) nom,
  String Function(T)? detail,
}) => montrerFeuille<T>(
  context,
  titre: titre,
  contenu: (f) {
    var filtre = '';
    return StatefulBuilder(
      builder: (f, maj) {
        final liste = elements.where((e) => filtre.isEmpty || nom(e).toLowerCase().contains(filtre.toLowerCase())).toList();
        return ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(f).height * 0.62),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (elements.length > 8) ...[
                  ChampVerre(icone: 'loupe', indice: t('Rechercher'), onChanged: (v) => maj(() => filtre = v)),
                  const SizedBox(height: 10),
                ],
                Flexible(
                  child: Plaque(
                    child: ListView.separated(
                      shrinkWrap: true,
                      padding: EdgeInsets.zero,
                      itemCount: liste.length,
                      separatorBuilder: (_, _) => Divider(height: 1, thickness: 0.7, indent: 16, color: Couleurs.filet),
                      itemBuilder: (_, i) => InkWell(
                        onTap: () => Navigator.pop(f, liste[i]),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                          child: Row(
                            children: [
                              Expanded(child: Text(nom(liste[i]), style: Textes.libelle)),
                              if (detail != null) ...[const SizedBox(width: 8), Text(detail(liste[i]), style: Textes.petit)],
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  },
);

Future<Client?> choisirClient(BuildContext context) {
  final clients = Donnees.instance.clients.values.toList()..sort((a, b) => a.nom.compareTo(b.nom));
  return choisirDansListe<Client>(
    context,
    titre: t('Choisir un client'),
    elements: clients,
    nom: (c) => c.nom,
    detail: (c) => c.encours > 0 ? fcfa(c.encours) : '',
  );
}

/// Les factures ouvertes d un client, pour une promesse, une contestation, un avoir…
Future<Facture?> choisirFacture(BuildContext context, String clientId) async {
  final factures = (await Donnees.instance.factures(clientId: clientId)).where((f) => f.ouverte).toList();
  if (!context.mounted) return null;
  return choisirDansListe<Facture>(context, titre: t('Choisir une facture'), elements: factures, nom: (f) => f.numero, detail: (f) => fcfa(f.solde));
}

/// Un choix parmi quelques valeurs, en pastilles (mode de paiement, canal, resolution).
class ChoixPastilles extends StatelessWidget {
  const ChoixPastilles({super.key, required this.valeurs, required this.choisie, required this.nom, required this.onChoisi, this.icone});

  final List<String> valeurs;
  final String? choisie;
  final String Function(String) nom;
  final String Function(String)? icone;
  final ValueChanged<String> onChoisi;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [for (final v in valeurs) Pastille(texte: nom(v), icone: icone?.call(v), retenue: choisie == v, onTap: () => onChoisi(v))],
  );
}

/// Le message d erreur d un formulaire, sous ses champs.
class ErreurFormulaire extends StatelessWidget {
  const ErreurFormulaire(this.texte, {super.key});

  final String? texte;

  @override
  Widget build(BuildContext context) => texte == null
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icone('alerte', taille: 16, couleur: Couleurs.erreur),
              const SizedBox(width: 8),
              Expanded(
                child: Text(texte!, style: Textes.petit.copyWith(color: Couleurs.erreur)),
              ),
            ],
          ),
        );
}

/// Le clavier numerique pour un montant (entier, FCFA).
const clavierMontant = TextInputType.numberWithOptions(signed: false, decimal: false);
final filtreMontant = [FilteringTextInputFormatter.allow(RegExp(r'[0-9 ]'))];

/// Une reference fictive pour un paiement simule : MM-SIM-20261215-4821. Elle reste la meme tant
/// que le formulaire est ouvert, pour qu un second envoi soit reconnu comme un rejeu.
String referenceFictive(String mode) {
  final d = Donnees.instance.dateReference;
  final n = DateTime.now().millisecondsSinceEpoch % 10000;
  return '${prefixeReference(mode)}-${iso(d).replaceAll('-', '')}-${n.toString().padLeft(4, '0')}';
}
