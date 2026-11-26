// Les montants et les dates, a un seul endroit (comme formatApp dans Sovrean) : aucun ecran ne
// les reecrit. Les montants sont des entiers en FCFA, sans decimales (cahier, section 9).

const _mois = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
const _moisLongs = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
const _jours = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'];

/// L espace insecable des milliers (Wura Mi n a pas l espace fine) : « 1 250 000 » ne se coupe jamais en fin de ligne.
const _espace = ' ';

/// 1250000 -> « 1 250 000 ».
String nombre(int n) {
  final signe = n < 0 ? '−' : '';
  final chiffres = n.abs().toString();
  final morceaux = <String>[];
  for (var fin = chiffres.length; fin > 0; fin -= 3) {
    morceaux.insert(0, chiffres.substring(fin - 3 < 0 ? 0 : fin - 3, fin));
  }
  return signe + morceaux.join(_espace);
}

/// 1250000 -> « 1 250 000 FCFA ».
String fcfa(int montant) => '${nombre(montant)} FCFA';

/// Un grand montant en court, pour les chiffres du tableau de bord : « 12,4 M FCFA ».
String fcfaCourt(int montant) {
  if (montant.abs() < 1000000) return fcfa(montant);
  final millions = montant / 1000000;
  final texte = millions.toStringAsFixed(millions.abs() < 10 ? 2 : 1).replaceAll('.', ',');
  return '$texte M FCFA';
}

/// Dans les listes : « 15 déc. 2026 ».
String dateCourte(DateTime d) => '${d.day} ${_mois[d.month - 1]} ${d.year}';

/// Sur les fiches : « 15 décembre 2026 ».
String dateLongue(DateTime d) => '${d.day} ${_moisLongs[d.month - 1]} ${d.year}';

/// La date de reference en tete du tableau de bord : « Mardi 15 décembre 2026 ».
String dateDuJour(DateTime d) {
  final jour = _jours[d.weekday - 1];
  return '${jour[0].toUpperCase()}${jour.substring(1)} ${dateLongue(d)}';
}

/// Dans le journal seulement : « 15 déc. 2026, 09:42 ».
String horodatage(DateTime d) => '${dateCourte(d)}, ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// L accord en nombre, avec deux phrases entieres (jamais un « s » colle a la main) :
/// accorder(3, '{n} facture en retard', '{n} factures en retard').
String accorder(int n, String singulier, String pluriel) => (n > 1 ? pluriel : singulier).replaceAll('{n}', nombre(n));

/// Les jours de retard, en mots.
String retard(int jours) => switch (jours) {
  0 => 'À échéance',
  1 => '1 jour de retard',
  _ => '${nombre(jours)} jours de retard',
};

/// Les textes du back-end ecrivent « 400000 FCFA » : on y remet les espaces des milliers.
String montantsLisibles(String texte) => texte.replaceAllMapped(RegExp(r'(\d{4,}) ?FCFA'), (m) => fcfa(int.parse(m[1]!)));
