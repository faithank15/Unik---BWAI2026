// Les reglages, comme ceux de Discover (et des Parametres du telephone) : des groupes de lignes
// sur une plaque, une icone, le nom, la valeur a droite ou un interrupteur.
import 'package:flutter/material.dart';

import '../theme/jetons.dart';
import 'icone.dart';
import 'verre.dart';

typedef Motif = (String, String?);

class GroupeReglages extends StatelessWidget {
  const GroupeReglages({super.key, this.titre, required this.lignes});

  final String? titre;
  final List<LigneReglage> lignes;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 18),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (titre != null)
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 8),
            child: Text(
              titre!,
              style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w700, color: Couleurs.texte),
            ),
          ),
        Plaque(
          child: Column(
            children: [
              // Le trait part du texte, comme dans les Parametres du telephone.
              for (var i = 0; i < lignes.length; i++) ...[if (i > 0) Divider(height: 1, thickness: 0.7, indent: 52, color: Couleurs.filet), lignes[i]],
            ],
          ),
        ),
      ],
    ),
  );
}

class LigneReglage extends StatelessWidget {
  const LigneReglage({
    super.key,
    required this.icone,
    required this.texte,
    this.valeur,
    this.onTap,
    this.interrupteur,
    this.onChanged,
    this.danger = false,
    this.info = false,
  });

  final String icone;
  final String texte;
  final String? valeur;
  final VoidCallback? onTap;
  final bool? interrupteur;
  final ValueChanged<bool>? onChanged;
  final bool danger;

  /// Une ligne d information : rien a toucher, pas de chevron.
  final bool info;

  @override
  Widget build(BuildContext context) {
    final couleur = danger ? Couleurs.erreur : Couleurs.texte;
    final ligne = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: Mesures.hautLigne),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 14, 8),
        child: Row(
          children: [
            Icone(icone, taille: 22, couleur: couleur),
            const SizedBox(width: 14),
            Expanded(
              child: Text(
                texte,
                style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w500, color: couleur),
              ),
            ),
            // La valeur, collee a droite contre le chevron, sur deux lignes au plus et 42 % de la ligne :
            // longue (« Parametre par defaut du systeme »), avec une police large ou agrandie, elle
            // poussait le titre.
            if (valeur != null) ...[
              const SizedBox(width: 12),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.42),
                child: Text(
                  valeur!,
                  textAlign: TextAlign.end,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 14.5, height: 1.25, color: Couleurs.discret),
                ),
              ),
              const SizedBox(width: 6),
            ],
            if (interrupteur != null)
              Switch(
                value: interrupteur!,
                activeTrackColor: Couleurs.ocean,
                inactiveTrackColor: Couleurs.pisteEteinte,
                inactiveThumbColor: Colors.white,
                trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
                onChanged: onChanged,
              )
            else if (!danger && !info)
              Icone('chevron-droite', taille: 18, couleur: Couleurs.chevron),
          ],
        ),
      ),
    );
    if (interrupteur != null) return MergeSemantics(child: ligne);
    if (info) return ligne;
    return InkWell(onTap: onTap, child: ligne);
  }
}

/// Un choix parmi plusieurs, dans une feuille (theme, police).
class ListeMotifs extends StatelessWidget {
  const ListeMotifs({super.key, required this.motifs, required this.choisi, required this.onChoisi});

  final List<Motif> motifs;
  final int? choisi;
  final ValueChanged<int> onChoisi;

  @override
  Widget build(BuildContext context) => Plaque(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < motifs.length; i++) ...[
          if (i > 0) Divider(height: 1, thickness: 0.7, indent: 48, color: Couleurs.filet),
          Semantics(
            selected: choisi == i,
            inMutuallyExclusiveGroup: true,
            child: InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: () => onChoisi(i),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                child: Row(
                  children: [
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 260),
                      curve: Courbes.interface,
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: choisi == i ? Couleurs.texte : Couleurs.trait, width: 1.5),
                      ),
                      alignment: Alignment.center,
                      child: AnimatedScale(
                        scale: choisi == i ? 1 : 0,
                        duration: const Duration(milliseconds: 360),
                        curve: Courbes.ressort,
                        child: Container(
                          width: 11,
                          height: 11,
                          decoration: BoxDecoration(color: Couleurs.texte, shape: BoxShape.circle),
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(motifs[i].$1, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                          if (motifs[i].$2 != null) Text(motifs[i].$2!, style: TextStyle(fontSize: 12.5, color: Couleurs.discret)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    ),
  );
}
