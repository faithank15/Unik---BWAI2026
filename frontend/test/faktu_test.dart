import 'package:faktu/donnees/modeles.dart';
import 'package:faktu/outils/api.dart';
import 'package:faktu/outils/format.dart';
import 'package:faktu/outils/libelles.dart';
import 'package:faktu/widgets/formulaires.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Format', () {
    test('les montants en FCFA, entiers, avec une espace insécable', () {
      expect(fcfa(1250000), '1\u00A0250\u00A0000\u00A0FCFA');
      expect(fcfa(0), '0\u00A0FCFA');
      expect(nombre(999), '999');
    });

    test('l accord en nombre : 0 et 1 au singulier', () {
      expect(accorder(1, '{n} facture', '{n} factures'), '1 facture');
      expect(accorder(0, '{n} facture', '{n} factures'), '0 facture');
      expect(accorder(3, '{n} facture', '{n} factures'), '3 factures');
    });

    test('les dates en français, et au format de l API', () {
      expect(dateCourte(DateTime(2026, 12, 15)), '15 déc. 2026');
      expect(dateDuJour(DateTime(2026, 12, 15)), 'Mardi 15 décembre 2026');
      expect(iso(DateTime(2026, 1, 5)), '2026-01-05');
    });

    test('un montant saisi à la main', () {
      expect(lireMontant('1 250 000'), 1250000);
      expect(lireMontant('1.250.000'), 1250000);
      expect(lireMontant(''), isNull);
      expect(lireMontant('0'), isNull);
    });
  });

  group('Réponses réelles du back-end', () {
    test('une ligne de priorisation garde le détail du score', () {
      final p = Priorite({
        'facture_id': 'FAC-2026-0103',
        'numero': 'FA-2026-0503',
        'client_id': 'CLI-0030',
        'retard_jours': 22,
        'solde': 400000,
        'points_anciennete': '29.33',
        'points_solde': '14.00',
        'points_historique': '12.50',
        'score': '55.83',
        'rang': 1,
        'suspension': null,
      });
      expect(p.score, closeTo(55.83, 0.001));
      expect(p.anciennete + p.pointsSolde + p.historique, closeTo(p.score, 0.01));
      expect(p.rang, 1);
    });

    test('une facture et ses échéances', () {
      final f = Facture({
        'id': 'FAC-2026-0001',
        'numero': 'FA-2026-0401',
        'client': {'id': 'CLI-0001', 'raison_sociale': 'Établissements Gbénami et Fils'},
        'montant_ttc': 82000,
        'statut': 'SOLDEE',
        'solde': 0,
        'affecte': 82000,
        'echeances': [
          {'id': 'ECH-0001', 'rang': 1, 'date_echeance': '2026-10-20', 'montant_du': 82000, 'affecte': 82000, 'solde': 0, 'retard_jours': 0, 'etat': 'ACTIVE'},
        ],
      });
      expect(f.clientId, 'CLI-0001');
      expect(f.ouverte, isFalse);
      expect(f.echeances.single.dateEcheance, DateTime(2026, 10, 20));
    });

    test('une revue réservée au validateur', () {
      expect(const ElementRevue({'type': 'GROS_MONTANT'}).reserveAuValidateur, isTrue);
      expect(const ElementRevue({'type': 'PAIEMENT_AMBIGU'}).reserveAuValidateur, isFalse);
    });
  });

  group('Libellés', () {
    test('chaque code connu a ses mots, un code inconnu reste lisible', () {
      expect(apparenceFacture('COUVERTE_PAR_ECHEANCIER').texte, 'Échéancier en cours');
      expect(apparenceRelance('ENVOYEE_SIM').texte, 'Envoyée');
      expect(motif('SOLDE_NUL'), 'Le client a payé entre la préparation et l’envoi.');
      expect(typeRevue('UN_TYPE_NOUVEAU'), 'Un type nouveau');
      for (final c in categories) {
        expect(categorie(c), isNot(contains('_')));
      }
    });
  });

  test('l adresse du back-end par défaut passe par adb reverse', () {
    expect(adresseApi, 'http://127.0.0.1:8000');
  });

  test('les montants du back-end deviennent lisibles', () {
    expect(montantsLisibles('Le solde est de 400000 FCFA'), 'Le solde est de 400 000 FCFA');
  });
}
