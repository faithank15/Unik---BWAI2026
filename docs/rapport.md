# Rapport – Recouvrement automatique des factures impayées

Hackathon BWAI 2026, cas pratique 1. Prototype de démonstration : **aucune donnée réelle, aucun envoi réel, aucun paiement réel**.

## 1. Besoin

Dans les PME béninoises, les factures sont suivies sur Excel ou sur papier. Les relances partent trop tard, sans priorité claire, et parfois à tort : on réclame une facture déjà réglée, on ignore une contestation, on écrit trois fois le même jour au même client. Le prototype prépare **les bonnes relances au bon moment**, sans multiplier les sollicitations ni automatiser les décisions sensibles : les litiges, les gros montants et les cas incertains vont à une personne avant toute suite.

Deux principes guident la conception. Les calculs sont **déterministes et vérifiables** (aucun solde ni statut n'est stocké : tout se recalcule depuis les échéances, paiements et avoirs). L'IA est **limitée à une seule tâche** : classer les réponses des clients. Elle ne modifie jamais un solde, un paiement ou un statut ; le code décide, une personne tranche.

## 2. Parcours

1. **Import** local du portefeuille (CSV) avec contrôle des champs et des doublons, rejeu sans effet, rapport de rejets motivés.
2. **Calcul** à la date de référence (15 décembre 2026, avançable) : soldes, retards, statuts (non échue, échue, partiellement payée, soldée, contestée, couverte par un échéancier).
3. **Priorisation** des factures échues par un score documenté sur 100 (ancienneté 40, solde 35, historique de retard 25), avec la décomposition affichée.
4. **Planification** des relances graduées (rappel préventif P, puis R1, R2, R3) sur WhatsApp et par courriel simulés, avec messages types fixes, regroupement par client, espacement, report des dimanches et jours fériés.
5. **Revérification juste avant l'envoi** : une relance devenue injustifiée (paiement reçu, contestation, promesse, accord, message en attente) est annulée ; gros montants, litiges et cas incertains vont en **validation humaine**.
6. **Paiements et avoirs simulés** rattachés aux échéances, annulation immédiate des relances concernées.
7. **Réponses des clients** classées par l'IA (déjà payé, promesse, contestation, échéancier, délai, copie, autre), avec seuil de confiance et reprise humaine.
8. **Escalade** en revue humaine cinq jours après R3 sans suite.
9. **Tableau de bord** et **journal** : chaque chiffre renvoie à la liste qui l'explique ; `GET /api/factures/{id}/explication` rassemble la règle de statut appliquée, les pièces et les événements.

## 3. Architecture

```text
Interface web ──► API back-end locale (Python, FastAPI) ──► SQLite locale (WAL)
                       │  ├─ domaine : règles pures (soldes, statuts, priorisation, calendrier, canevas)
                       │  ├─ services : une transaction par cas d'usage, journal dans la même transaction
                       │  ├─ moteur de relances (planification, revérification, envoi simulé)
                       │  └─ module IA ──► API du LLM (seul accès réseau)
                       └─ canaux et paiements simulés
```

Le back-end est dans `backend/`, 59 routes documentées (`backend/openapi.json`), le front-end viendra à côté. Choix techniques justifiés : SQLite sans ORM pour contrôler explicitement les transactions `BEGIN IMMEDIATE` et les verrous ; sessions opaques et mots de passe hachés (scrypt) sans dépendance de plus ; l'IA derrière un **adaptateur unique** (délai, réessais, coupe-circuit, validation stricte de la sortie) remplaçable par un faux dans les tests. La règle d'architecture : le domaine ne dépend ni de FastAPI ni de la base, les services ouvrent la transaction, l'API ne fait que valider et sérialiser.

## 4. Contrôles

| Risque | Contrôle |
| --- | --- |
| Double comptabilisation, double envoi | Clés d'idempotence (import par empreinte SHA-256, paiement par mode + référence, relance par client/canal/échéances/date, classification par message et version de consigne) ; second traitement concurrent constate l'état déjà changé |
| Incohérence en cas de panne | Toute écriture sensible dans une transaction avec son événement de journal ; erreur injectée au milieu : tout est annulé |
| Relance injustifiée | Revérification dans la transaction d'envoi ; annulation immédiate après paiement, avoir, contestation, promesse, accord ou message |
| Action automatique à risque | Seul le VALIDATEUR valide un gros montant, clôt un litige, accepte un accord ; la classification n'a jamais accès aux soldes |
| Accès | Deux rôles, jetons à durée limitée, 5 échecs de connexion bloquent 5 minutes, chaque refus journalisé |
| Journal | En ajout seulement (déclencheurs SQL), acteur, horodatage, `correlation_id`, date métier |
| Données | Fictives ; aucun secret dans le dépôt (testé) ; le LLM ne reçoit ni nom, ni courriel, ni téléphone, ni montant |
| Message piégé | Le texte client est une donnée délimitée par des balises, jamais une instruction ; sortie validée par le code |

## 5. Protocole et résultats des tests

Le protocole suit le plan de tests : écrire les tests avant le code, ne jamais modifier la vérité terrain pour faire passer un test, aucun accès réseau (sockets bloqués, LLM remplacé par un faux), base rechargée de l'état initial à chaque test.

**Résultats métier (règles et calculs), indépendants de l'IA.**

| Mesure | Résultat |
| --- | --- |
| Tests automatisés | 767 sur 767 réussis, 0 ignoré ; couverture 96 % de `app/domain`, `app/services`, `app/ia` |
| Soldes et statuts conformes à la vérité terrain | 120 factures et 147 échéances, 0 écart |
| Affectations de paiements et avoirs | 92 sur 92, 0 écart |
| Priorisation | 47 rangs et scores identiques |
| Relances jour par jour (15/12 au 05/01) | 317 décisions identiques à la vérité terrain |
| Scénarios S01 à S23 | 23 sur 23 |
| Doublons produits par rejeu ou concurrence | 0 (jusqu'à 8 threads) |
| Sécurité | 401 sans jeton et 403 avec le mauvais rôle sur chaque route (matrice de 59 routes) |
| Reproductibilité | `make reset` en 0,1 s ; deux réinitialisations identiques ; installation vérifiée sur un clone propre |
| Performance (garde-fous) | planification d'une journée 20 ms ; priorisation 15 ms ; tableau de bord 20 ms |

La vérité terrain est calculée par un oracle indépendant, écrit dans le générateur du jeu de données, sans code partagé avec l'API. Les 16 contrôles de cohérence du jeu (unicité, intégrité, sommes, chronologie, volumes, statuts, affectations, déterminisme, confidentialité…) passent.

**Résultats IA (séparés).** Voir la fiche IA : sur le jeu de développement, exactitude 95 % contre 34 % pour une règle par mots-clés, aucune erreur critique. Le jeu de test n'a pas encore été utilisé.

## 6. Comparaison à la référence

Référence : la règle naïve « relancer chaque échéance en retard, une relance chacune ». Sur le portefeuille de démonstration au 15 décembre 2026 (51 échéances en retard) :

| | Règle naïve | Système |
| --- | --- | --- |
| Relances | 51 | 18 messages (22 lignes d'échéances regroupées) |
| Relances injustifiées (contestation ou promesse en cours) | 8, envoyées | 8, **évitées** (suspendues) |
| Messages économisés par le regroupement | 0 | 4 |
| Gros montants | envoyés | 4 mis en attente de validation humaine |

La mesure principale du gain est donc **les relances injustifiées évitées** : des clients qui ont contesté ou promis de payer ne sont pas relancés, et aucun client n'est relancé sur une facture déjà soldée entre la préparation et l'envoi (scénario S07). Les 51 de la règle naïve ne tiennent pas compte du calendrier ; le système n'en envoie que 14 le jour même (les autres sont suspendues, regroupées ou en attente de validation).

**Temps de traitement par dossier, système contre tableur : non mesuré.** Le chronométrage manuel de 20 dossiers par un membre de l'équipe, prévu au cahier des charges, reste à faire ; l'API ne le calcule pas.

## 7. Limites

- Prototype : pas d'envoi, de paiement ni de facturation réels ; pas d'intégration WhatsApp, mobile money ou facture normalisée. Montants TTC en FCFA, pas de TVA ni de comptabilité ; les pénalités de retard sont informatives.
- Français uniquement ; les mots en fon ou en yoruba sont une limite connue. La classification ne voit pas le contexte d'une conversation.
- Un accord d'échéancier n'est possible que sur une facture sans paiement.
- Les 400 messages d'évaluation sont fictifs. Les 340 premiers viennent de phrases-types composées par un modèle (Claude) différent de celui qui classe ; les 60 « écrits à la main » ont été **rédigés par ce même modèle, faute de temps, et non par des personnes**. Les noms d'entreprises et de personnes sont inventés, à relire.
- Le plan gratuit limite fortement l'usage : le modèle visé (Gemini 3.8 Flash) n'y autorise que 20 requêtes par jour, d'où le choix de `gemini-3.1-flash-lite` ; l'API des modèles Gemini est parfois surchargée ou lente.
- La confiance déclarée par le modèle n'est pas une probabilité calibrée : sur DEV elle est quasi toujours entre 0,9 et 1,0, donc peu informative pour régler un seuil.
- Aucune interface n'est livrée avec ce dépôt.

## 8. Coûts estimatifs d'usage

**Coût du MVP : nul.** Le prototype tourne en local (aucune infrastructure à payer) et utilise le **plan gratuit** de l'API Gemini. Ce plan a des limites qui ont pesé pendant le développement : le modèle visé initialement (Gemini 3.8 Flash) n'y autorise que 20 requêtes par jour, ce qui a conduit au modèle `gemini-3.1-flash-lite`, qui a traité les 100 messages de développement sans coût. Les conditions du plan gratuit (quotas, usage des contenus envoyés) sont à vérifier auprès du fournisseur ; ici, toutes les données sont fictives.

Le TDR demande aussi un coût estimatif d'**usage réel**. L'estimation suivante concerne une exploitation sur plan payant et se calcule à partir de **mesures** faites sur le jeu DEV : en moyenne 822 jetons en entrée et 108 en sortie par message.

Tarif payant de `gemini-3.1-flash-lite` : **0,25 $ par million de jetons en entrée et 1,50 $ par million en sortie** (relevé auprès de sources secondaires concordantes ; à vérifier sur la page officielle des tarifs de Google avant toute décision).

Coût par message = (822 × 0,25 + 108 × 1,50) / 1 000 000 ≈ **0,00037 $** (environ 0,22 FCFA à 600 FCFA le dollar, hypothèse).

| Volume mensuel | Coût de l'API (plan payant) |
| --- | --- |
| 100 messages | 0,04 $ (≈ 22 FCFA) |
| 500 messages | 0,18 $ (≈ 110 FCFA) |
| 2 000 messages | 0,74 $ (≈ 440 FCFA) |

Les appels échoués (503, quota) ne sont pas supposés facturés ; une marge de 10 % couvre les réessais. Le **coût humain de la revue est très supérieur** à celui de l'API : 86 % des messages passent en revue (toutes les catégories sensibles). Avec une hypothèse de 1,5 minute par revue et 2 500 FCFA l'heure, cela représente environ 54 FCFA par message, soit environ 107 500 FCFA pour 2 000 messages par mois. Pour réduire la facture : consigne plus courte, moins d'exemples, ou regroupement des revues d'un même client.

## 9. Étapes d'une éventuelle expérimentation

1. **Connecteurs réels** : WhatsApp Business, courriel, mobile money, en remplaçant les simulateurs (déjà isolés en modules internes).
2. **Données réelles anonymisées** d'une PME, avec un contrat de données pour le LLM (hébergement, durée de conservation, consentement des clients) : aujourd'hui le fournisseur reçoit le texte des messages.
3. **Relecture comptable et juridique** des règles : pénalités de retard, mentions légales, jours fériés complets (fêtes mobiles absentes), seuil de gros montant.
4. **Évaluation sur de vrais messages** : jeu de test annoté par deux personnes, mesure des erreurs critiques et du temps gagné, ajustement des seuils.
5. **Exploitation** : base de données serveur, sauvegardes, supervision, gestion des utilisateurs, intégration avec l'outil de facturation existant.
