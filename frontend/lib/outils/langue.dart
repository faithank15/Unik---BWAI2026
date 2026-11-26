// Les textes de l application. Faktu est en francais seulement (cahier des charges, section 2),
// mais tout passe quand meme par t() : c est la regle de Discover, et une autre langue
// s ajoutera sans toucher aux ecrans.
import 'package:flutter/foundation.dart';

class Langue extends ChangeNotifier {
  Langue._();
  static final instance = Langue._();

  /// La seule langue pour l instant.
  String code = 'fr';

  String traduire(String fr, [Map<String, Object?>? valeurs]) {
    var texte = fr;
    valeurs?.forEach((cle, valeur) => texte = texte.replaceAll('{$cle}', '$valeur'));
    return texte;
  }
}

/// Le texte affiche, avec ses valeurs : t('{n} factures', {'n': 3}).
String t(String fr, [Map<String, Object?>? valeurs]) => Langue.instance.traduire(fr, valeurs);

/// L accord en nombre : en francais, 0 et 1 restent au singulier.
String tn(int n, String un, String plusieurs) => t(n <= 1 ? un : plusieurs, {'n': n});
