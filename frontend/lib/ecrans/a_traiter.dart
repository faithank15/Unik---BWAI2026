// A traiter : les factures echues classees par le back-end (GET /api/priorisation), avec le detail
// de leur score. Le score organise le travail, il ne predit pas qui paiera (cahier 6.6). Un second
// onglet donne tous les clients (GET /api/clients), cherchables par nom.
import 'package:flutter/material.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import '../widgets/champ.dart';
import '../widgets/faktu.dart';
import '../widgets/verre.dart';

class EcranATraiter extends StatefulWidget {
  const EcranATraiter({super.key});

  @override
  State<EcranATraiter> createState() => _EcranATraiterState();
}

class _EcranATraiterState extends State<EcranATraiter> {
  final _recherche = TextEditingController();
  var _clients = false;

  @override
  void dispose() {
    _recherche.dispose();
    super.dispose();
  }

  static String _sansAccents(String s) {
    const de = 'àâäéèêëîïôöùûüç';
    const vers = 'aaaeeeeiioouuuc';
    var r = s.toLowerCase();
    for (var i = 0; i < de.length; i++) {
      r = r.replaceAll(de[i], vers[i]);
    }
    return r;
  }

  bool _correspond(String cherche, List<String> champs) => cherche.isEmpty || champs.any((c) => _sansAccents(c).contains(cherche));

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: Donnees.instance,
    builder: (context, _) {
      final d = Donnees.instance;
      final cherche = _sansAccents(_recherche.text.trim());
      final factures = d.priorisation.where((p) => _correspond(cherche, [d.nomClient(p.clientId), p.numero, p.factureId])).toList();
      if (_clients && !d.clientsAJour) d.tousLesClients().ignore();
      final clients = d.clientsCharges.where((c) => _correspond(cherche, [c.nom, c.id, c.ville])).toList()..sort((a, b) => b.encours.compareTo(a.encours));
      final total = factures.fold(0, (s, p) => s + p.solde);
      return PageFaktu(
        titre: t('À traiter'),
        sousTitre: _clients
            ? accorder(clients.length, '{n} client', '{n} clients')
            : '${accorder(factures.length, '{n} facture en retard', '{n} factures en retard')} · ${fcfa(total)}',
        enfants: [
          Row(
            children: [
              Pastille(texte: t('Factures à relancer'), retenue: !_clients, onTap: () => setState(() => _clients = false)),
              const SizedBox(width: 8),
              Pastille(texte: t('Clients'), retenue: _clients, onTap: () => setState(() => _clients = true)),
            ],
          ),
          const SizedBox(height: 12),
          ChampVerre(
            icone: 'loupe',
            indice: _clients ? t('Rechercher un client') : t('Client ou numéro de facture'),
            controleur: _recherche,
            onChanged: (_) => setState(() {}),
            action: TextInputAction.search,
          ),
          const SizedBox(height: 16),
          if (d.tableau == null && d.erreur != null)
            EtatErreur(message: d.erreur!, onReessayer: () => d.rafraichir(force: true))
          else if (d.tableau == null)
            const Attente()
          else if (_clients)
            ...(d.clientsAJour ? _listeClients(context, clients) : const [Attente()])
          else
            ..._listeFactures(context, factures, cherche.isNotEmpty),
        ],
      );
    },
  );

  List<Widget> _listeFactures(BuildContext context, List<Priorite> liste, bool recherche) => [
    if (liste.isEmpty)
      EtatVide(icone: recherche ? 'loupe' : 'coche', titre: recherche ? t('Aucune facture trouvée') : t('Aucune facture en retard'))
    else ...[
      GroupeLignes(lignes: [for (final p in liste) LignePriorite(p, onTap: () => ouvrir(context, 'facture/${p.factureId}'))]),
      const SizedBox(height: 14),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: Text(
          t(
            'Le score sur 100 classe le travail : le retard compte pour 40, le montant dû pour 35, les retards passés du client pour 25. Il ne prédit pas qui paiera.',
          ),
          style: Textes.petit.copyWith(color: Couleurs.discret),
        ),
      ),
    ],
  ];

  List<Widget> _listeClients(BuildContext context, List<Client> liste) => [
    if (liste.isEmpty)
      EtatVide(icone: 'loupe', titre: t('Aucun client trouvé'))
    else
      GroupeLignes(retrait: 16, lignes: [for (final c in liste) LigneClient(c, onTap: () => ouvrir(context, 'client/${c.id}'))]),
  ];
}
