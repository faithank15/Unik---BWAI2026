// L affichage choisi dans le compte et garde d un lancement a l autre : le theme seulement (celui
// du telephone par defaut, ou clair, ou sombre). La police reste Wura Mi, et les animations
// suivent le reglage « reduire les animations » du telephone : ces choix n ont pas leur place dans
// une application de travail.
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum ModeTheme { systeme, clair, sombre }

class Affichage extends ChangeNotifier {
  Affichage._();
  static final instance = Affichage._();

  ModeTheme mode = ModeTheme.systeme;

  Future<void> charger() async {
    try {
      final p = await SharedPreferences.getInstance();
      mode = ModeTheme.values.asNameMap()[p.getString('theme')] ?? ModeTheme.systeme;
    } catch (_) {
      // Sans stockage (les tests) : le theme du telephone.
    }
  }

  void choisirTheme(ModeTheme m) {
    mode = m;
    notifyListeners();
    SharedPreferences.getInstance().then((p) => p.setString('theme', m.name)).catchError((_) => false);
  }
}
