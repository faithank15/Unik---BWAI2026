// Relancer un client tout de suite, sans attendre le calendrier (POST /api/relances/manuelle).
// Le serveur garde toutes ses protections : solde reverifie, contestation, promesse, echeancier,
// consentement, jour ouvre et jours a eviter ; au-dela du seuil, un validateur decide.
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/api.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/faktu.dart';
import '../widgets/feuille.dart';
import '../widgets/formulaires.dart';
import '../widgets/page.dart';
import '../widgets/verre.dart';

Future<void> relancerMaintenant(BuildContext context, Client c, {Facture? facture}) async {
  final autorises = c.canauxAutorises.isEmpty ? [c.canalPrefere] : c.canauxAutorises;
  var canalChoisi = autorises.contains(c.canalPrefere) ? c.canalPrefere : autorises.first;
  final commentaire = TextEditingController();
  String? erreur;
  var enCours = false;
  Json? resultat;
  await montrerFeuille<void>(
    context,
    titre: t('Relancer {c} maintenant', {'c': c.nom}),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => CorpsFeuille(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              facture == null
                  ? t('Le message part tout de suite, sans attendre le calendrier des relances. Il reprend toutes les factures en retard de ce client.')
                  : t('Le message part tout de suite, sans attendre le calendrier des relances. Il porte sur la facture {n}.', {'n': facture.numero}),
              style: Textes.corps,
            ),
            const SizedBox(height: 14),
            if (autorises.length > 1) ...[
              Libelle(t('Canal')),
              ChoixPastilles(valeurs: autorises, choisie: canalChoisi, nom: canal, icone: iconeCanal, onChoisi: (v) => maj(() => canalChoisi = v)),
              const SizedBox(height: 12),
            ] else
              LigneInfo(t('Canal'), canal(canalChoisi)),
            ChampVerre(
              libelle: t('Pourquoi maintenant'),
              icone: 'crayon',
              controleur: commentaire,
              facultatif: true,
              indice: t('Le client a demandé un rappel, visite prévue demain…'),
            ),
            const SizedBox(height: 8),
            Text(
              t(
                'Avant l’envoi, Faktu revérifie le solde, les contestations, les promesses et l’accord du client. Au-delà de 500 000 FCFA, un validateur doit d’abord valider.',
              ),
              style: Textes.petit,
            ),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Relancer maintenant'),
              icone: 'envoyer',
              plein: true,
              enCours: enCours,
              onTap: () async {
                maj(() => (enCours, erreur) = (true, null));
                try {
                  resultat = await Donnees.instance.relancerMaintenant(
                    c.id,
                    canal: canalChoisi,
                    factureIds: facture == null ? null : [facture.id],
                    commentaire: commentaire.text.trim().isEmpty ? null : commentaire.text.trim(),
                  );
                  if (f.mounted) Navigator.pop(f);
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
  final r = resultat;
  if (r == null || !context.mounted) return;
  if (r['deja_fait'] == true) {
    bulle(context, t('{c} a déjà été relancé aujourd’hui sur ce canal : voici ce message.', {'c': c.nom}), icone: 'horloge');
  } else {
    switch ('${r['resultat']}') {
      case 'ENVOYEE_SIM':
        bulle(context, t('Relance envoyée à {c} par {k}.', {'c': c.nom, 'k': canal(canalChoisi)}), icone: 'coche');
      case 'EN_ATTENTE_VALIDATION':
        bulle(context, t('Plus de 500 000 FCFA : la relance attend un validateur, dans À revoir.'), icone: 'cadenas');
      default:
        final m = motif(r['motif'] as String?);
        bulle(context, m.isEmpty ? t('La relance n’a pas été envoyée.') : t('La relance n’a pas été envoyée : {m}', {'m': m}), icone: 'alerte');
    }
  }
  // Le message exact, tel qu il est parti (ou attend la validation).
  ouvrir(context, 'relance/${r['relance_id']}');
}
