// Les pieces propres a Faktu, faites avec celles de Discover : l en-tete de page, la pastille de
// statut, les chiffres du tableau de bord, le detail du score, et les etats vide, erreur et
// attente. Un ecran n en fait jamais sa propre version.
import 'package:flutter/cupertino.dart' show CupertinoSliverRefreshControl, RefreshIndicatorMode;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../donnees/donnees.dart';
import '../donnees/modeles.dart';
import '../outils/format.dart';
import '../outils/langue.dart';
import '../outils/libelles.dart';
import '../theme/jetons.dart';
import '../theme/theme.dart';
import 'icone.dart';
import 'page.dart';
import 'verre.dart';

/// Une page de Faktu : l en-tete (titre, retour si on peut revenir, une action a droite), puis
/// le contenu qui defile sous l heure, avec la place de la barre d onglets en bas. On tire
/// vers le bas pour rafraichir.
class PageFaktu extends StatelessWidget {
  const PageFaktu({super.key, required this.titre, required this.enfants, this.sousTitre, this.action, this.retour = false, this.rafraichir = true});

  final String titre;
  final String? sousTitre;
  final List<Widget> enfants;
  final Widget? action;
  final bool retour;
  final bool rafraichir;

  @override
  Widget build(BuildContext context) {
    final haut = MediaQuery.paddingOf(context).top;
    final marge = Mesures.margeDe(MediaQuery.sizeOf(context).width);
    final contenu = SliverPadding(
      padding: EdgeInsets.fromLTRB(marge, haut + 10, marge, Mesures.hautOnglets + 48 + MediaQuery.paddingOf(context).bottom),
      sliver: SliverList.list(
        children: [
          Row(
            children: [
              if (retour) ...[RondVerre(icone: 'retour', semantique: t('Retour'), onTap: () => context.pop()), const SizedBox(width: 12)],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(titre, style: retour ? Textes.sousTitre : Textes.titre, maxLines: 2, overflow: TextOverflow.ellipsis),
                    if (sousTitre != null) ...[const SizedBox(height: 2), Text(sousTitre!, style: Textes.petit)],
                  ],
                ),
              ),
              ?action,
            ],
          ),
          const SizedBox(height: 22),
          ...enfants,
        ],
      ),
    );
    return Scaffold(
      body: SousLHeure(
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
          slivers: [
            // Tirer vers le bas, tout en haut : le logo apparait, puis la piece se retourne
            // pendant que les donnees se rafraichissent (comme l accueil de Discover).
            if (rafraichir)
              CupertinoSliverRefreshControl(
                onRefresh: () => Donnees.instance.rafraichir(force: true),
                builder: (context, etat, tire, seuil, _) {
                  final v = seuil <= 0 ? 0.0 : (tire / seuil).clamp(0.0, 1.0);
                  final tourne = etat == RefreshIndicatorMode.armed || etat == RefreshIndicatorMode.refresh;
                  return Padding(
                    padding: EdgeInsets.only(top: haut),
                    child: Center(
                      child: Opacity(opacity: tourne ? 1 : v, child: tourne ? const LogoQuiTourne(taille: 30) : const LogoFaktu(taille: 30)),
                    ),
                  );
                },
              ),
            contenu,
          ],
        ),
      ),
    );
  }
}

/// Le titre d une section, avec un lien a droite (« Tout voir »).
class TitreSection extends StatelessWidget {
  const TitreSection(this.texte, {super.key, this.lien, this.onLien});

  final String texte;
  final String? lien;
  final VoidCallback? onLien;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(4, 6, 4, 10),
    child: Row(
      children: [
        Expanded(
          child: Text(
            texte,
            style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w700, color: Couleurs.texte),
          ),
        ),
        if (lien != null)
          GestureDetector(
            onTap: onLien,
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.all(4),
              child: Text(lien!, style: Textes.lien),
            ),
          ),
      ],
    ),
  );
}

/// Un statut : toujours un mot et une icone (jamais une couleur seule).
class PastilleStatut extends StatelessWidget {
  const PastilleStatut(this.apparence, {super.key, this.petite = false});

  final Apparence apparence;
  final bool petite;

  @override
  Widget build(BuildContext context) {
    final a = apparence;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: petite ? 8 : 10, vertical: petite ? 3 : 5),
      decoration: BoxDecoration(color: a.fond ?? a.couleur.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icone(a.icone, taille: petite ? 13 : 15, couleur: a.couleur),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              a.texte,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: petite ? 12 : 13, fontWeight: FontWeight.w600, color: a.couleur),
            ),
          ),
        ],
      ),
    );
  }
}

/// Un chiffre du tableau de bord : le nombre en grand, ce qu il compte dessous. Touchable.
class CarteChiffre extends StatelessWidget {
  const CarteChiffre({super.key, required this.valeur, required this.libelle, this.icone, this.couleur, this.onTap});

  final String valeur;
  final String libelle;
  final String? icone;
  final Color? couleur;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final carte = Plaque(
      rayon: Mesures.rayonCarte,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (icone != null) ...[Icone(icone!, taille: 20, couleur: couleur ?? Couleurs.discret), const SizedBox(height: 10)],
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              valeur,
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: -0.6, color: couleur ?? Couleurs.texte),
            ),
          ),
          const SizedBox(height: 2),
          Text(libelle, style: Textes.petit, maxLines: 2),
        ],
      ),
    );
    if (onTap == null) return carte;
    return Appuyable(onTap: onTap, semantique: '$valeur, $libelle', child: carte);
  }
}

/// Le detail du score de priorite (cahier 6.6), tel que le back-end le calcule : trois barres,
/// ce qui le compose se lit.
class DetailScore extends StatelessWidget {
  const DetailScore(this.p, {super.key});

  final Priorite p;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      _barre(t('Retard'), p.anciennete, 40),
      const SizedBox(height: 8),
      _barre(t('Montant dû'), p.pointsSolde, 35),
      const SizedBox(height: 8),
      _barre(t('Retards passés'), p.historique, 25),
    ],
  );

  Widget _barre(String nom, double points, double sur) => Row(
    children: [
      SizedBox(width: 112, child: Text(nom, style: Textes.petit)),
      Expanded(
        child: Container(
          height: 6,
          alignment: Alignment.centerLeft,
          decoration: BoxDecoration(color: Couleurs.secondaire, borderRadius: BorderRadius.circular(3)),
          child: FractionallySizedBox(
            widthFactor: (points / sur).clamp(0.0, 1.0),
            heightFactor: 1,
            child: DecoratedBox(
              decoration: BoxDecoration(color: Couleurs.ocean, borderRadius: BorderRadius.circular(3)),
            ),
          ),
        ),
      ),
      SizedBox(
        width: 62,
        child: Text(
          '${points.toStringAsFixed(1).replaceAll('.', ',')}/${sur.round()}',
          textAlign: TextAlign.end,
          style: Textes.petit.copyWith(color: Couleurs.texte),
        ),
      ),
    ],
  );
}

/// Le score en rond, a gauche d une ligne.
class RondScore extends StatelessWidget {
  const RondScore(this.total, {super.key});

  final double total;

  @override
  Widget build(BuildContext context) {
    final fort = total >= 60;
    return Container(
      width: 46,
      height: 46,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: fort ? Couleurs.ocean : Couleurs.secondaire, borderRadius: BorderRadius.circular(14)),
      child: Text(
        '${total.round()}',
        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: fort ? Colors.white : Couleurs.texte),
      ),
    );
  }
}

/// Une ligne de la liste priorisee : la facture, son client, son retard, son solde. Le nom tient
/// sur sa propre ligne : il n est plus coupe par le montant.
class LignePriorite extends StatelessWidget {
  const LignePriorite(this.p, {super.key, required this.onTap});

  final Priorite p;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
      child: Row(
        children: [
          RondScore(p.score),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(Donnees.instance.nomClient(p.clientId), maxLines: 1, overflow: TextOverflow.ellipsis, style: Textes.libelle),
                const SizedBox(height: 2),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${p.numero} · ${retard(p.retard)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Textes.petit.copyWith(color: Couleurs.erreur),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      fcfa(p.solde),
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Couleurs.texte),
                    ),
                  ],
                ),
                if (p.suspension != null) ...[const SizedBox(height: 2), Text(motif(p.suspension), style: Textes.petit)],
              ],
            ),
          ),
          const SizedBox(width: 4),
          Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
        ],
      ),
    ),
  );
}

/// Une ligne de client : le nom, la ville, l encours.
class LigneClient extends StatelessWidget {
  const LigneClient(this.c, {super.key, required this.onTap});

  final Client c;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(c.nom, maxLines: 1, overflow: TextOverflow.ellipsis, style: Textes.libelle),
                const SizedBox(height: 2),
                Text(
                  '${c.ville} · ${accorder(c.nbFacturesOuvertes, '{n} facture ouverte', '{n} factures ouvertes')}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Textes.petit,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            fcfa(c.encours),
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Couleurs.texte),
          ),
          const SizedBox(width: 4),
          Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
        ],
      ),
    ),
  );
}

/// Une plaque de lignes separees par un filet qui part du texte (comme les Parametres).
class GroupeLignes extends StatelessWidget {
  const GroupeLignes({super.key, required this.lignes, this.retrait = 72});

  final List<Widget> lignes;
  final double retrait;

  @override
  Widget build(BuildContext context) => Plaque(
    child: Column(
      // Etiree : une ligne plus courte que les autres ne se centre pas.
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < lignes.length; i++) ...[if (i > 0) Divider(height: 1, thickness: 0.7, indent: retrait, color: Couleurs.filet), lignes[i]],
      ],
    ),
  );
}

/// Rien a montrer : une phrase simple, une icone, sans illustration.
class EtatVide extends StatelessWidget {
  const EtatVide({super.key, required this.icone, required this.titre, this.texte});

  final String icone;
  final String titre;
  final String? texte;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
    child: Column(
      children: [
        Icone(icone, taille: 30, couleur: Couleurs.discret),
        const SizedBox(height: 12),
        Text(titre, textAlign: TextAlign.center, style: Textes.libelle),
        if (texte != null) ...[const SizedBox(height: 4), Text(texte!, textAlign: TextAlign.center, style: Textes.petit)],
      ],
    ),
  );
}

/// Un chargement qui a echoue : ce qui s est passe, et Réessayer.
class EtatErreur extends StatelessWidget {
  const EtatErreur({super.key, required this.message, required this.onReessayer});

  final String message;
  final VoidCallback onReessayer;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 16),
    child: Column(
      children: [
        Icone('hors-ligne', taille: 30, couleur: Couleurs.discret),
        const SizedBox(height: 12),
        Text(message, textAlign: TextAlign.center, style: Textes.discret),
        const SizedBox(height: 16),
        BoutonVerre(texte: t('Réessayer'), large: false, icone: 'retourner', onTap: onReessayer),
      ],
    ),
  );
}

/// L attente : le logo de Faktu, jamais un cercle de progression.
class Attente extends StatelessWidget {
  const Attente({super.key, this.hauteur = 220});

  final double hauteur;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: hauteur,
    child: const Center(child: LogoQuiTourne(taille: 46)),
  );
}

/// La mention « Simulation » : les envois et les paiements ne sont jamais reels (cahier).
class MentionSimulation extends StatelessWidget {
  const MentionSimulation({super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
    decoration: BoxDecoration(
      border: Border.all(color: Couleurs.trait),
      borderRadius: BorderRadius.circular(6),
    ),
    child: Text(
      t('Simulation'),
      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Couleurs.discret),
    ),
  );
}

/// Une ligne cle : valeur, sur les fiches.
class LigneInfo extends StatelessWidget {
  const LigneInfo(this.cle, this.valeur, {super.key, this.couleur, this.fort = false});

  final String cle;
  final String valeur;
  final Color? couleur;
  final bool fort;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(fontSize: 14.5, fontWeight: fort ? FontWeight.w700 : FontWeight.w600, color: couleur ?? Couleurs.texte);
    // Une valeur courte (un nombre, une date) laisse toute la place au libelle ;
    // une longue partage la ligne.
    final courte = valeur.length <= 18;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (courte)
            Expanded(child: Text(cle, style: Textes.discret.copyWith(fontSize: 14.5)))
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 150),
              child: Text(cle, style: Textes.discret.copyWith(fontSize: 14.5)),
            ),
          const SizedBox(width: 16),
          if (courte)
            Text(valeur, style: style)
          else
            Expanded(
              child: Text(valeur, textAlign: TextAlign.end, style: style),
            ),
        ],
      ),
    );
  }
}

/// Ouvre une page de detail dans l onglet courant (le retour y ramene) : ouvrir(context,
/// 'client/CLI-0001') depuis A traiter ouvre /a-traiter/client/CLI-0001.
void ouvrir(BuildContext context, String chemin) {
  final segments = GoRouterState.of(context).uri.pathSegments;
  final onglet = segments.isEmpty ? 'accueil' : segments.first;
  context.push('/$onglet/$chemin');
}
