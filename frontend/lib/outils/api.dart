// Le seul client d API de Faktu (back-end FastAPI du depot Unik---BWAI2026). Aucun ecran n appelle
// http directement (regles unk, 10-integration-flutter.md).
//
// L adresse vient de --dart-define=FAKTU_API ; par defaut http://127.0.0.1:8000, qui marche sur un
// telephone branche en USB apres `adb reverse tcp:8000 tcp:8000`. Depuis l emulateur Android :
// http://10.0.2.2:8000.
//
// Le contrat : backend/openapi.json. Les erreurs ont la forme
// {"erreur": {"code", "message", "details", "correlation_id"}} (specification, section 4).
// L idempotence n est pas un en-tete : elle vient des donnees (reference externe d un paiement,
// cle d une relance). Le formulaire garde donc la meme reference d un essai a l autre.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

const adresseApi = String.fromEnvironment('FAKTU_API', defaultValue: 'http://127.0.0.1:8000');

class ApiErreur implements Exception {
  const ApiErreur(this.message, {this.statut = 0, this.code, this.regle});

  /// Le message du serveur (deja en francais), sinon une phrase « Impossible de… ».
  final String message;
  final int statut;

  /// NON_AUTHENTIFIE, ACCES_REFUSE, CONFLIT, REGLE_METIER, VALIDATION…
  final String? code;

  /// Pour une REGLE_METIER : laquelle (DATE_PASSEE, REVUE_DEJA_RESOLUE…).
  final String? regle;

  bool get sessionExpiree => statut == 401;
  bool get roleInsuffisant => statut == 403;
  bool get horsConnexion => statut == 0;

  @override
  String toString() => message;
}

class Api {
  Api._();
  static final instance = Api._();

  String? jeton;

  /// Appele quand le serveur dit que la session a expire (401) : retour a la connexion.
  void Function()? surSessionExpiree;

  final _client = http.Client();
  static const _delai = Duration(seconds: 20);

  Uri _uri(String chemin, [Map<String, Object?>? requete]) {
    final propre = {
      for (final e in (requete ?? const <String, Object?>{}).entries)
        if (e.value != null) e.key: '${e.value}',
    };
    return Uri.parse('$adresseApi/api$chemin').replace(queryParameters: propre.isEmpty ? null : propre);
  }

  Map<String, String> _entetes({bool json = true}) => {
    'Accept': 'application/json',
    if (json) 'Content-Type': 'application/json',
    if (jeton != null) 'Authorization': 'Bearer $jeton',
  };

  /// Une lecture : une seconde tentative si le reseau coupe (une lecture ne change rien).
  Future<dynamic> lire(String chemin, [Map<String, Object?>? requete]) async {
    for (var essai = 0; ; essai++) {
      try {
        return _decoder(await _client.get(_uri(chemin, requete), headers: _entetes()).timeout(_delai));
      } on ApiErreur {
        rethrow;
      } catch (_) {
        if (essai >= 1) throw const ApiErreur(_horsLigne);
        await Future<void>.delayed(const Duration(milliseconds: 800));
      }
    }
  }

  /// Une liste paginee ({total, elements}) : tout, page apres page (200 au plus par page).
  Future<List<Map<String, dynamic>>> liste(String chemin, [Map<String, Object?>? requete]) async {
    final tout = <Map<String, dynamic>>[];
    for (var decalage = 0; ; decalage += 200) {
      final r = (await lire(chemin, {...?requete, 'limite': 200, 'decalage': decalage}) as Map).cast<String, dynamic>();
      final elements = [for (final e in (r['elements'] as List? ?? const [])) (e as Map).cast<String, dynamic>()];
      tout.addAll(elements);
      final total = r['total'] as int? ?? tout.length;
      if (elements.isEmpty || tout.length >= total) return tout;
    }
  }

  /// Une action. Pas de seconde tentative automatique : c est la personne qui renvoie, avec les
  /// memes donnees (le back-end reconnait un rejeu et ne compte rien deux fois).
  Future<dynamic> envoyer(String chemin, [Map<String, Object?>? corps, String methode = 'POST']) async {
    try {
      final requete = http.Request(methode, _uri(chemin))
        ..headers.addAll(_entetes())
        ..body = jsonEncode(corps ?? const {});
      return _decoder(await http.Response.fromStream(await _client.send(requete).timeout(_delai)));
    } on ApiErreur {
      rethrow;
    } catch (_) {
      throw const ApiErreur(_horsLigne);
    }
  }

  /// L envoi de fichiers (import d un lot) : un champ par fichier.
  Future<dynamic> envoyerFichiers(String chemin, Map<String, (String, List<int>)> fichiers) async {
    final requete = http.MultipartRequest('POST', _uri(chemin))..headers.addAll(_entetes(json: false));
    for (final e in fichiers.entries) {
      requete.files.add(http.MultipartFile.fromBytes(e.key, e.value.$2, filename: e.value.$1));
    }
    try {
      return _decoder(await http.Response.fromStream(await _client.send(requete).timeout(const Duration(seconds: 60))));
    } on ApiErreur {
      rethrow;
    } catch (_) {
      throw const ApiErreur(_horsLigne);
    }
  }

  static const _horsLigne = 'Impossible de joindre le serveur. Vérifiez la connexion et réessayez.';

  dynamic _decoder(http.Response r) {
    dynamic corps;
    try {
      corps = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      corps = null;
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return corps;
    final erreur = corps is Map ? corps['erreur'] : null;
    final message = erreur is Map ? erreur['message'] : null;
    final details = erreur is Map ? erreur['details'] : null;
    final regle = details is Map ? details['regle'] as String? : null;
    final e = ApiErreur(
      _phrases[regle] ??
          (message is String && message.isNotEmpty
              ? message
              : switch (r.statusCode) {
                  401 => 'Votre session a expiré. Reconnectez-vous.',
                  403 => 'Votre rôle ne permet pas cette action.',
                  409 => 'Ce dossier vient d’être traité par quelqu’un d’autre.',
                  422 => 'Les informations saisies ne sont pas valides.',
                  _ => 'Impossible de terminer l’action. Réessayez.',
                }),
      statut: r.statusCode,
      code: erreur is Map ? erreur['code'] as String? : null,
      regle: regle,
    );
    if (e.sessionExpiree && jeton != null) surSessionExpiree?.call();
    throw e;
  }
}

/// Les regles du back-end, dites a la personne qui saisit : ce qui bloque et quoi faire.
/// Une regle absente garde le message du serveur.
const _phrases = {
  'FACTURE_NON_IDENTIFIABLE': 'Ce client a plusieurs factures ouvertes. Choisissez la facture concernée.',
  'FACTURE_NON_OUVERTE': 'Cette facture est déjà réglée ou annulée. Choisissez une facture ouverte.',
  'FACTURE_NON_RELANCABLE': 'Cette facture est réglée ou annulée : elle ne peut plus être relancée.',
  'DATE_PASSEE': 'La date promise est déjà passée. Choisissez une date à partir d’aujourd’hui.',
  'DATE_FUTURE': 'Cette date est dans le futur. Choisissez une date passée ou celle d’aujourd’hui.',
  'AVOIR_SUPERIEUR_AU_SOLDE': 'Le montant de l’avoir dépasse ce que le client doit encore sur cette facture.',
  'SUR_AFFECTATION': 'Le montant affecté dépasse ce qu’il reste à payer, ou ce qu’il reste du paiement.',
  'TRANCHES_INSUFFISANTES': 'Un échéancier compte au moins deux tranches.',
  'DATES_INVALIDES': 'Les dates des tranches doivent se suivre, à partir d’aujourd’hui.',
  'MESSAGE_DEJA_TRAITE': 'Cette réponse a déjà été classée.',
  'REVUE_DEJA_RESOLUE': 'Ce dossier a déjà été traité par quelqu’un d’autre.',
  'CONTESTATION_DEJA_CLOTUREE': 'Cette contestation est déjà close.',
  'PROMESSE_NON_EN_COURS': 'Cette promesse n’est plus en cours : elle ne peut plus être annulée.',
  'ECHEANCE_REMPLACEE': 'Cette échéance a été remplacée par un échéancier. Actualisez la page.',
  'CLIENTS_DIFFERENTS': 'Toutes les échéances doivent appartenir au client du paiement.',
};
