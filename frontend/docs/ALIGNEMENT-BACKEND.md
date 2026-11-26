# L'interface mobile et le back-end : ce qui est branché

Référence : le dépôt `Unik---BWAI2026`, dossier `backend/` (`openapi.json`, 59 routes). L'interface n'invente aucun flux : chaque écran et chaque formulaire appelle une route qui existe.

## Ce qui a été retiré de l'interface (pas de route, ou superflu)

| Retiré | Pourquoi |
|---|---|
| Le faux back-end intégré à l'application (données de démonstration) | Le back-end a déjà son jeu de données, `POST /api/admin/reset` et `POST /api/admin/avancer`. |
| Le score par client | Le back-end classe des **factures** (`GET /api/priorisation`), pas des clients. |
| Le choix de la police et « Réduire les animations » | Superflu dans une application de travail. Les animations suivent le réglage du téléphone. |
| « Effacer les données de ce téléphone » | Aucune contrepartie côté serveur ; la déconnexion (`POST /api/auth/logout`) suffit. |
| L'en-tête `Idempotency-Key` | Le back-end ne l'utilise pas. L'idempotence vient des données : la référence d'un paiement, la clé d'une relance, l'empreinte d'un import. Le formulaire de paiement garde donc la même référence d'un envoi à l'autre. |
| L'import d'un seul fichier CSV | `POST /api/imports` attend un **lot** : `clients`, `factures`, `echeances` (+ `preferences_contact`, `accords_echeancier`). L'application les choisit ensemble. |
| « Préparer et envoyer » en un seul bouton | Le back-end sépare `planifier` et `envoyer` ; entre les deux, un paiement annule la relance (S07). Deux boutons. |

## Ce qui a été ajouté (route existante, l'application en avait besoin)

| Saisie ou action | Route |
|---|---|
| Paiement : client (facultatif), montant, mode, date, référence, facture indiquée | `POST /api/paiements` |
| Affecter un paiement ambigu, échéance par échéance | `POST /api/paiements/{id}/affecter` |
| Avoir : montant, date, motif | `POST /api/avoirs` |
| Réponse d'un client : canal, texte, facture citée | `POST /api/messages` |
| Classer une réponse à la main (catégorie, date et montant promis, facture) | `POST /api/messages/{id}/valider-categorie` |
| Relancer l'IA sur une réponse à classer | `POST /api/messages/{id}/classer` |
| Ouvrir une contestation / la clore (validateur) | `POST /api/contestations`, `…/{id}/cloturer` |
| Promesse de paiement / l'annuler | `POST /api/promesses`, `…/{id}/annuler` |
| Proposer un échéancier (tranches) / l'accepter ou le refuser (validateur) | `POST /api/accords`, `…/{id}/accepter`, `…/{id}/refuser` |
| Contact et préférences d'un client | `PUT /api/clients/{id}/preferences` |
| Valider ou rejeter une relance de gros montant (validateur) | `POST /api/relances/{id}/valider`, `…/rejeter` |
| Clore un dossier de revue « sans suite », noter une décision d'escalade | `POST /api/revue/{id}/resoudre` |
| Explication d'une facture (règle de statut retenue et écartées) | `GET /api/factures/{id}/explication` |
| Boîte d'envoi simulée (le texte exact envoyé) | `GET /api/canaux/envois` |
| Relances suspendues et comparaison à la règle naïve | `GET /api/relances/suspensions`, `GET /api/evaluation/comparaison-reference` |
| Paramètres métier (lecture ; modification par le validateur) | `GET /api/parametres`, `PUT /api/parametres/{cle}` |

## Questions au back-end et réponses

1. **Les noms des clients dans les listes** : fait par le back-end (`client_raison_sociale`). L'application ne charge plus les 30 clients au démarrage ; elle retient les noms donnés par les listes et ne charge la liste complète que pour l'onglet Clients ou le choix d'un client.
2. **Les décisions d'une escalade** : toujours en texte libre côté serveur ; l'application garde `APPEL_CLIENT`, `MISE_EN_DEMEURE`, `ABANDON`, `SANS_SUITE`.
3. **Revue « contact invalide » après correction** : l'application résout encore la revue avec `CONTACT_CORRIGE`.
4. **Une IA qui propose, l'agent qui valide** : en partie fait. Le back-end fait rédiger l'introduction et la conclusion des **courriels** par le LLM, selon le cas du client et le ton de l'étape (les montants, dates et factures restent insérés par le code) ; WhatsApp garde les canevas. Le moment des relances reste un calendrier, mais l'espacement grandit avec le montant.

## Branché après l'extension IA du back-end (26 novembre 2026)

| Dans l'application | Route |
|---|---|
| **Relancer maintenant** (fiche client, et depuis une facture), avec canal et raison | `POST /api/relances/manuelle` |
| Jours où ne pas relancer le client, moment préféré, date de la dernière modification | `PUT /api/clients/{id}/preferences` (`jours_a_eviter`, `plage_horaire`, `provenance`) |
| **Courriels rédigés par l'IA** (Compte) : cas, ton, objet, introduction, conclusion, « Marquer comme relue » | `GET /api/redactions`, `POST /api/redactions/relue` |
| Relances différées par l'espacement, avec leur prochaine date (tableau de bord) | `GET /api/tableau-de-bord` (`relances_reportees`) |
| Origine d'une relance : calendrier ou manuelle | `GET /api/relances/{id}` (`origine`) |
| Erreurs expliquées : jour non ouvré, jour à éviter, relance déjà en cours, rien à relancer, canal ou consentement | règles `JOUR_NON_OUVRE`, `JOUR_A_EVITER`, `RELANCE_DEJA_EN_COURS`, `RIEN_A_RELANCER`, `CANAL_INVALIDE`, `CONSENTEMENT_ABSENT` |

## Lancer avec le back-end

```bash
# Dans le dépôt Unik---BWAI2026/backend
make reset && make run                 # API sur http://0.0.0.0:8000

# Téléphone branché en USB : il voit le PC à l'adresse 127.0.0.1:8000
adb reverse tcp:8000 tcp:8000

# Dans Faktu
flutter run                                              # adresse par défaut : http://127.0.0.1:8000
flutter run --dart-define=FAKTU_API=http://10.0.2.2:8000 # émulateur Android
flutter run --dart-define=FAKTU_API=http://192.168.1.20:8000  # téléphone sur le même Wi-Fi que le PC
```

Comptes : `gestionnaire` et `validateur`, avec les mots de passe définis dans `backend/.env` (`SEED_MDP_GESTIONNAIRE`, `SEED_MDP_VALIDATEUR`). Sans `LLM_API_KEY`, les réponses restent « à classer » et les courriels utilisent les messages types.
