import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app.dart';
import 'donnees/affichage.dart';
import 'donnees/donnees.dart';
import 'outils/sobriete.dart';
import 'widgets/lentille.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // L ecran de bord a bord, la barre d etat transparente (comme Discover).
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  chargerLentille();
  await Affichage.instance.charger();
  await Sobriete.instance.demarrer();
  await Donnees.instance.reprendreSession();
  if (Donnees.instance.utilisateur != null) Donnees.instance.rafraichir(force: true).ignore();
  runApp(const AppFaktu());
}
