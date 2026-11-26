// Des pages a la suite (les lieux de l accueil, les lifestyles) : on glisse du doigt vers
// la suivante ou la precedente, sans revenir a la liste.
import 'dart:math';

import 'package:flutter/material.dart';

class PagesEnSuite extends StatefulWidget {
  const PagesEnSuite({super.key, required this.ids, required this.depart, required this.page});

  /// Les pages, dans l ordre de la liste d ou l on vient.
  final List<String> ids;

  /// Celle qui s ouvre.
  final String depart;

  final Widget Function(String id) page;

  @override
  State<PagesEnSuite> createState() => _PagesEnSuiteState();
}

class _PagesEnSuiteState extends State<PagesEnSuite> {
  late final PageController _pages = PageController(initialPage: max(0, widget.ids.indexOf(widget.depart)));

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PageView.builder(
    controller: _pages,
    itemCount: widget.ids.length,
    itemBuilder: (context, i) => KeyedSubtree(key: ValueKey(widget.ids[i]), child: widget.page(widget.ids[i])),
  );
}

/// La suite passee en `extra` a l ouverture d une page (une liste d identifiants), si elle
/// contient bien celle qui s ouvre.
List<String>? suiteDe(Object? extra, String id) {
  if (extra is! List<String> || extra.length < 2 || !extra.contains(id)) return null;
  return extra;
}
