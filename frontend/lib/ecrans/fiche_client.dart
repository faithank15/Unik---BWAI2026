// La fiche d un client (GET /api/clients/{id}) : ce qu il doit, ses factures, son contact et ses
// preferences (modifiables : PUT /api/clients/{id}/preferences), ses relances, ses reponses et ses
// paiements. Chaque facture ouvre son detail et son explication.
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
import 'ajouter.dart';
import 'relance_manuelle.dart';

class EcranFicheClient extends StatefulWidget {
  const EcranFicheClient({super.key, required this.id});

  final String id;

  @override
  State<EcranFicheClient> createState() => _EcranFicheClientState();
}

class _EcranFicheClientState extends State<EcranFicheClient> {
  Client? _client;
  List<Message> _messages = const [];
  List<Paiement> _paiements = const [];
  String? _erreur;

  @override
  void initState() {
    super.initState();
    _charger();
    Donnees.instance.addListener(_suivre);
  }

  @override
  void dispose() {
    Donnees.instance.removeListener(_suivre);
    super.dispose();
  }

  // Une action ailleurs (paiement, decision) : la fiche se relit une fois, a la fin du rafraichissement.
  bool _attendFin = false;
  void _suivre() {
    if (Donnees.instance.enCours) {
      _attendFin = true;
    } else if (_attendFin) {
      _attendFin = false;
      _charger();
    }
  }

  Future<void> _charger() async {
    final d = Donnees.instance;
    try {
      final r = await Future.wait([d.client(widget.id), d.messages(clientId: widget.id), d.paiements(clientId: widget.id)]);
      if (!mounted) return;
      setState(() {
        _client = r[0] as Client;
        _messages = (r[1] as List<Message>).reversed.toList();
        _paiements = (r[2] as List<Paiement>).reversed.toList();
        _erreur = null;
      });
    } on ApiErreur catch (e) {
      if (mounted) setState(() => _erreur = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _client;
    return PageFaktu(
      titre: c?.nom ?? Donnees.instance.nomClient(widget.id),
      sousTitre: c == null ? widget.id : [c.id, c.ville, c.secteur].where((x) => x.isNotEmpty).join(' · '),
      retour: true,
      rafraichir: false,
      enfants: [
        if (c == null && _erreur != null) EtatErreur(message: _erreur!, onReessayer: _charger) else if (c == null) const Attente() else ..._contenu(context, c),
      ],
    );
  }

  List<Widget> _contenu(BuildContext context, Client c) {
    final ouvertes = c.factures.where((x) => x.ouverte).toList()..sort((a, b) => b.retard.compareTo(a.retard));
    final fermees = c.factures.where((x) => !x.ouverte).toList();
    final retardMax = ouvertes.fold(0, (m, f) => f.retard > m ? f.retard : m);
    return [
      Plaque(
        rayon: Mesures.rayonCarte,
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t('Reste à payer'), style: Textes.petit),
            const SizedBox(height: 2),
            Text(fcfa(c.encours), style: Textes.titre.copyWith(fontSize: 30)),
            if (retardMax > 0) ...[const SizedBox(height: 4), Text(retard(retardMax), style: Textes.petit.copyWith(color: Couleurs.erreur))],
          ],
        ),
      ),
      const SizedBox(height: 12),
      if (c.encours > 0) ...[
        BoutonVerre(texte: t('Relancer maintenant'), icone: 'envoyer', plein: true, onTap: () => relancerMaintenant(context, c)),
        const SizedBox(height: 10),
      ],
      Row(
        children: [
          Expanded(
            child: BoutonVerre(
              texte: t('Paiement'),
              icone: 'piece',
              onTap: () => formulairePaiement(context, clientId: c.id),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: BoutonVerre(
              texte: t('Réponse'),
              icone: 'commentaire',
              onTap: () => formulaireMessage(context, clientId: c.id),
            ),
          ),
        ],
      ),
      const SizedBox(height: 22),
      TitreSection(t('Contact'), lien: t('Modifier le contact'), onLien: () => modifierContact(context, c)),
      Plaque(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
        child: Column(
          children: [
            if (c.interlocuteur != null) LigneInfo(t('Interlocuteur'), c.interlocuteur!),
            LigneInfo(t('Canal préféré'), canal(c.canalPrefere)),
            if (c.whatsapp != null) LigneInfo('WhatsApp', c.whatsapp!),
            if (c.email != null) LigneInfo(t('E-mail'), c.email!),
            if (c.joursAEviter.isNotEmpty) LigneInfo(t('Jamais relancé le'), c.joursAEviter.map(jourSemaine).join(', ')),
            if (c.plageHoraire != 'AUCUNE') LigneInfo(t('Moment préféré'), plageHoraire(c.plageHoraire)),
            LigneInfo(t('Relances'), c.consentement ? t('Autorisées') : t('Refusées par le client'), couleur: c.consentement ? null : Couleurs.erreur),
            if (_modifieLe(c) != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, bottom: 4),
                child: Text(t('Préférences modifiées dans Faktu le {d}', {'d': dateLongue(_modifieLe(c)!)}), style: Textes.petit),
              ),
          ],
        ),
      ),
      const SizedBox(height: 22),
      TitreSection(accorder(ouvertes.length, 'Facture ouverte', 'Factures ouvertes')),
      if (ouvertes.isEmpty)
        EtatVide(icone: 'coche', titre: t('Aucune facture à payer'))
      else
        GroupeLignes(retrait: 16, lignes: [for (final f in ouvertes) LigneFacture(f, onTap: () => ouvrir(context, 'facture/${f.id}'))]),
      if (fermees.isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Réglées ou annulées')),
        GroupeLignes(retrait: 16, lignes: [for (final f in fermees) LigneFacture(f, onTap: () => ouvrir(context, 'facture/${f.id}'))]),
      ],
      if (c.relancesRecentes.isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Relances récentes')),
        GroupeLignes(
          retrait: 16,
          lignes: [for (final r in c.relancesRecentes) LigneRelance(r, nomClient: false, onTap: () => ouvrir(context, 'relance/${r.id}'))],
        ),
      ],
      if (_messages.isNotEmpty) ...[
        const SizedBox(height: 22),
        TitreSection(t('Réponses du client')),
        for (final m in _messages) ...[CarteMessage(m), const SizedBox(height: 10)],
      ],
      if (_paiements.isNotEmpty) ...[
        const SizedBox(height: 12),
        TitreSection(t('Paiements')),
        GroupeLignes(retrait: 54, lignes: [for (final p in _paiements) LignePaiement(p)]),
      ],
      const SizedBox(height: 22),
      BoutonVerre(texte: t('Voir le journal de ce client'), icone: 'journal', onTap: () => ouvrir(context, 'journal?objet=${c.id}')),
    ];
  }
}

/// Modifier le contact et les preferences d un client : canal, canaux autorises, accord pour les
/// relances, numero, courriel, interlocuteur. Sert aussi aux revues « contact invalide » et
/// « sans accord de relance ».
Future<bool> modifierContact(BuildContext context, Client c) async {
  var canalPrefere = c.canalPrefere;
  final autorises = {...c.canauxAutorises};
  var consentement = c.consentement;
  final whatsapp = TextEditingController(text: c.whatsapp ?? '');
  final email = TextEditingController(text: c.email ?? '');
  final interlocuteur = TextEditingController(text: c.interlocuteur ?? '');
  final jours = {...c.joursAEviter};
  var plage = c.plageHoraire;
  String? erreur;
  var enCours = false;
  final ok = await montrerFeuille<bool>(
    context,
    titre: t('Contact de {c}', {'c': c.nom}),
    contenu: (f) => StatefulBuilder(
      builder: (f, maj) => CorpsFeuille(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Libelle(t('Canal préféré')),
            ChoixPastilles(
              valeurs: const ['WHATSAPP', 'EMAIL'],
              choisie: canalPrefere,
              nom: canal,
              icone: iconeCanal,
              onChoisi: (v) => maj(() => canalPrefere = v),
            ),
            const SizedBox(height: 14),
            Libelle(t('Canaux autorisés')),
            Wrap(
              spacing: 8,
              children: [
                for (final v in const ['WHATSAPP', 'EMAIL'])
                  Pastille(
                    texte: canal(v),
                    icone: autorises.contains(v) ? 'coche' : iconeCanal(v),
                    retenue: autorises.contains(v),
                    onTap: () => maj(() => autorises.contains(v) ? autorises.remove(v) : autorises.add(v)),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: Text(t('Le client accepte d’être relancé'), style: Textes.libelle)),
                Switch(value: consentement, onChanged: (v) => maj(() => consentement = v)),
              ],
            ),
            const SizedBox(height: 10),
            ChampVerre(libelle: 'WhatsApp', icone: 'whatsapp', controleur: whatsapp, clavier: TextInputType.phone, indice: '+2290100000000'),
            const SizedBox(height: 12),
            ChampVerre(libelle: t('E-mail'), icone: 'enveloppe', controleur: email, clavier: TextInputType.emailAddress),
            const SizedBox(height: 12),
            ChampVerre(libelle: t('Interlocuteur'), icone: 'profil', controleur: interlocuteur, facultatif: true, indice: t('Mme Adjoa Houngbo')),
            const SizedBox(height: 14),
            Libelle(t('Jours où ne pas le relancer'), facultatif: true),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final j in joursSemaine)
                  Pastille(
                    texte: jourSemaine(j),
                    icone: jours.contains(j) ? 'fermer' : null,
                    retenue: jours.contains(j),
                    onTap: () => maj(() => jours.contains(j) ? jours.remove(j) : jours.add(j)),
                  ),
              ],
            ),
            const SizedBox(height: 14),
            Libelle(t('Moment préféré pour le contacter')),
            ChoixPastilles(valeurs: plagesHoraires, choisie: plage, nom: plageHoraire, onChoisi: (v) => maj(() => plage = v)),
            const SizedBox(height: 6),
            Text(t('Un jour à éviter est traité comme un dimanche pour ce client : la relance attend le jour suivant permis.'), style: Textes.petit),
            ErreurFormulaire(erreur),
            const SizedBox(height: 16),
            BoutonVerre(
              texte: t('Enregistrer'),
              plein: true,
              enCours: enCours,
              onTap: () async {
                if (!autorises.contains(canalPrefere)) {
                  return maj(() => erreur = t('Le canal préféré doit faire partie des canaux autorisés.'));
                }
                maj(() => (enCours, erreur) = (true, null));
                try {
                  await Donnees.instance.modifierPreferences(c.id, {
                    'canal_prefere': canalPrefere,
                    'canaux_autorises': autorises.toList(),
                    'consentement_relance': consentement,
                    'whatsapp': whatsapp.text.trim().isEmpty ? null : whatsapp.text.trim().replaceAll(' ', ''),
                    'email': email.text.trim().isEmpty ? null : email.text.trim(),
                    'interlocuteur': interlocuteur.text.trim().isEmpty ? null : interlocuteur.text.trim(),
                    'jours_a_eviter': [
                      for (final j in joursSemaine)
                        if (jours.contains(j)) j,
                    ],
                    'plage_horaire': plage,
                  });
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
  if (ok == true && context.mounted) bulle(context, t('Contact enregistré.'), icone: 'coche');
  return ok == true;
}

/// Une facture dans une liste : son numero, son statut, ce qu il reste a payer.
class LigneFacture extends StatelessWidget {
  const LigneFacture(this.f, {super.key, required this.onTap});

  final Facture f;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final a = apparenceFacture(f.statut, retard: f.retard);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(f.numero, style: Textes.libelle),
                  const SizedBox(height: 5),
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      PastilleStatut(a, petite: true),
                      if (f.partiellementPayee) PastilleStatut(Apparence(t('Payée en partie'), 'piece', Couleurs.ocean), petite: true),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  fcfa(f.ouverte ? f.solde : f.montantTtc),
                  style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: Couleurs.texte, decoration: a.barre ? TextDecoration.lineThrough : null),
                ),
                if (f.ouverte && f.solde != f.montantTtc) Text(t('sur {m}', {'m': fcfa(f.montantTtc)}), style: Textes.petit),
              ],
            ),
            const SizedBox(width: 4),
            Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
          ],
        ),
      ),
    );
  }
}

class LignePaiement extends StatelessWidget {
  const LignePaiement(this.p, {super.key});

  final Paiement p;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
    child: Row(
      children: [
        Icone('piece', taille: 22, couleur: p.resteNonAffecte == 0 ? Couleurs.succes : Couleurs.discret),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${modePaiement(p.mode)}${p.datePaiement == null ? '' : ' · ${dateCourte(p.datePaiement!)}'}', style: Textes.libelle),
              Text(
                p.resteNonAffecte > 0 ? t('{m} à affecter', {'m': fcfa(p.resteNonAffecte)}) : (p.reference ?? ''),
                style: Textes.petit.copyWith(color: p.resteNonAffecte > 0 ? Couleurs.erreur : null),
              ),
            ],
          ),
        ),
        Text(
          fcfa(p.montant),
          style: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: Couleurs.texte),
        ),
      ],
    ),
  );
}

/// Une relance : l etape, le canal, la date, son statut, et le motif s il y en a un.
class LigneRelance extends StatelessWidget {
  const LigneRelance(this.r, {super.key, this.nomClient = true, this.onTap});

  final Relance r;
  final bool nomClient;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final date = r.dateEnvoi ?? r.datePrevue;
    final quand = '${etape(r.etape)}${date == null ? '' : ' · ${dateCourte(date)}'}';
    final ligne = Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icone(iconeCanal(r.canal), taille: 18, couleur: Couleurs.discret),
              const SizedBox(width: 8),
              Expanded(
                child: Text(nomClient ? Donnees.instance.nomClient(r.clientId) : quand, maxLines: 1, overflow: TextOverflow.ellipsis, style: Textes.libelle),
              ),
              const SizedBox(width: 8),
              PastilleStatut(apparenceRelance(r.statut), petite: true),
            ],
          ),
          if (nomClient) ...[const SizedBox(height: 4), Text(quand, style: Textes.petit)],
          if (r.motif != null && r.statut != 'EN_ATTENTE_VALIDATION') ...[
            const SizedBox(height: 4),
            Text(motif(r.motif), style: Textes.petit.copyWith(color: Couleurs.texte)),
          ],
        ],
      ),
    );
    return onTap == null ? ligne : InkWell(onTap: onTap, child: ligne);
  }
}

/// Une reponse du client : le texte, ce que l IA en a compris et avec quelle confiance, et
/// l etiquette d une personne si elle existe (elle l emporte toujours).
class CarteMessage extends StatelessWidget {
  const CarteMessage(this.m, {super.key});

  final Message m;

  @override
  Widget build(BuildContext context) {
    final valide = m.categorieValidee;
    return Plaque(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icone(iconeCanal(m.canal), taille: 18, couleur: Couleurs.discret),
              const SizedBox(width: 8),
              Expanded(child: Text([canal(m.canal), if (m.dateReception != null) dateCourte(m.dateReception!)].join(' · '), style: Textes.petit)),
              Text(statutMessage(m.statut), style: Textes.petit),
            ],
          ),
          const SizedBox(height: 8),
          Text('« ${m.contenu} »', style: Textes.corps),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              if (valide != null)
                PastilleStatut(Apparence(categorie(valide), 'verifie', Couleurs.succes))
              else if (m.categorieIa != null)
                PastilleStatut(Apparence('${t('IA')} : ${categorie(m.categorieIa!)}', 'etincelle', Couleurs.ocean)),
              if (valide == null && m.confiance != null) PastilleStatut(Apparence(confiance(m.confiance), 'aide', Couleurs.discret)),
              if (m.datePromise != null)
                PastilleStatut(Apparence(t('Promis le {d}', {'d': dateCourte(m.datePromise!)}), 'calendrier', Couleurs.texte, fond: Couleurs.secondaire)),
              if (m.montantPromis != null) PastilleStatut(Apparence(fcfa(m.montantPromis!), 'piece', Couleurs.texte, fond: Couleurs.secondaire)),
              if (m.copieDemandee) PastilleStatut(Apparence(t('Copie demandée'), 'document', Couleurs.texte, fond: Couleurs.secondaire)),
            ],
          ),
          if (m.justification != null && valide == null) ...[const SizedBox(height: 8), Text(m.justification!, style: Textes.petit)],
        ],
      ),
    );
  }
}

/// La derniere date a laquelle une preference a ete changee dans Faktu (et non par l import).
DateTime? _modifieLe(Client c) {
  DateTime? derniere;
  for (final v in c.provenance.values) {
    final p = json(v);
    final d = date(p['date']);
    if (p['source'] == 'GESTIONNAIRE' && d != null && (derniere == null || d.isAfter(derniere))) derniere = d;
  }
  return derniere;
}
