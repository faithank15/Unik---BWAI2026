import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/jetons.dart';
import '../outils/langue.dart';

/// Une icone du pack Faktu (assets/icones) : a l encre, trait appuye comme les
/// symboles d iOS. Sa couleur suit le texte autour, comme `currentColor`.
class Icone extends StatelessWidget {
  const Icone(this.nom, {super.key, this.taille = 24, this.couleur});

  final String nom;
  final double taille;
  final Color? couleur;

  @override
  Widget build(BuildContext context) {
    final teinte = couleur ?? DefaultTextStyle.of(context).style.color ?? Couleurs.texte;
    return SvgPicture.asset(
      'assets/icones/$nom.svg',
      width: taille,
      height: taille,
      theme: SvgTheme(currentColor: teinte),
    );
  }
}

/// Le symbole de Faktu (la facture et sa piece cochee), le meme le jour et la nuit.
class LogoFaktu extends StatelessWidget {
  const LogoFaktu({super.key, this.taille = 48});

  final double taille;

  @override
  Widget build(BuildContext context) => SvgPicture.asset('assets/logo/faktu-symbole.svg', width: taille, height: taille, semanticsLabel: 'Faktu');
}

/// L attente de Faktu, a la place d un cercle de progression : la piece se retourne sur la
/// facture, comme une piece qu on encaisse. Mouvements reduits : tout reste immobile.
class LogoQuiTourne extends StatefulWidget {
  const LogoQuiTourne({super.key, this.taille = 40, this.couleur, this.tour = const Duration(milliseconds: 1400)});

  final double taille;

  /// Une seule couleur (blanc sur un bouton ocean) : la silhouette, sans les couleurs du logo.
  final Color? couleur;

  /// La duree d un retournement complet.
  final Duration tour;

  @override
  State<LogoQuiTourne> createState() => _LogoQuiTourneState();
}

class _LogoQuiTourneState extends State<LogoQuiTourne> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: widget.tour);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) {
      _c.stop();
    } else if (!_c.isAnimating) {
      _c.repeat();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  ColorFilter? get _filtre => widget.couleur == null ? null : ColorFilter.mode(widget.couleur!, BlendMode.srcIn);

  @override
  Widget build(BuildContext context) {
    final cote = widget.taille;
    return Semantics(
      label: t('Chargement'),
      child: ExcludeSemantics(
        child: SizedBox.square(
          dimension: cote,
          child: Stack(
            children: [
              SvgPicture.asset('assets/logo/faktu-feuille.svg', width: cote, height: cote, colorFilter: _filtre),
              AnimatedBuilder(
                animation: _c,
                builder: (_, enfant) {
                  // Un tour : immobile, puis la piece se retourne et revient, sur son propre centre.
                  final p = _c.value;
                  final phase = p < .2 ? 0.0 : (p > .8 ? 1.0 : Curves.easeInOutCubic.transform((p - .2) / .6));
                  return Transform(
                    alignment: const Alignment(0.4, 0.42),
                    transform: Matrix4.diagonal3Values(math.cos(2 * math.pi * phase), 1, 1),
                    child: enfant,
                  );
                },
                child: SvgPicture.asset('assets/logo/faktu-piece.svg', width: cote, height: cote, colorFilter: _filtre),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
