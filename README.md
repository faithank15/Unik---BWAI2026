# Recouvrement automatique des factures impayées

Prototype du hackathon **BWAI 2026**, cas pratique 1. Un gestionnaire de créances local importe un portefeuille de factures, calcule soldes, retards et statuts, prépare des relances graduées sur WhatsApp et par courriel, et classe les réponses des clients avec une IA. **Tout est simulé** : envois, paiements et données.

> Prototype de démonstration. Aucune donnée réelle, aucun envoi réel, aucun paiement réel.

## Sommaire

1. [Ce que fait le prototype](#1-ce-que-fait-le-prototype)
2. [Architecture](#2-architecture)
3. [Prérequis](#3-prérequis)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Lancement](#6-lancement)
7. [Comptes de test](#7-comptes-de-test)
8. [Jeu de données et réinitialisation](#8-jeu-de-données-et-réinitialisation)
9. [Reproduire les scénarios](#9-reproduire-les-scénarios)
10. [Tests](#10-tests)
11. [IA : modèle, mode dégradé, évaluation](#11-ia--modèle-mode-dégradé-évaluation)
12. [Sécurité et limites](#12-sécurité-et-limites)
13. [Dépendances, modèles et licences](#13-dépendances-modèles-et-licences)
14. [Documentation](#14-documentation)
15. [Version remise](#15-version-remise)

## 1. Ce que fait le prototype

- **Import local** d'un portefeuille (clients, factures, échéances) avec contrôle des champs et des doublons, rejouable sans doublon.
- **Calculs déterministes** des soldes, retards et statuts (non échue, échue, partiellement payée, soldée, contestée, couverte par un échéancier). Aucun solde n'est stocké : tout se calcule.
- **Priorisation** des factures échues par un score documenté sur 100 (ancienneté, solde, historique de retard).
- **Relances graduées** simulées (rappel préventif P, puis R1, R2, R3) sur WhatsApp et par courriel, avec messages types fixes.
- **Revérification juste avant l'envoi** : une relance devenue injustifiée (paiement reçu, contestation, promesse…) est annulée ; idempotence et traitements concurrents sans double action.
- **Validation humaine** pour les gros montants, les litiges et les cas incertains ; **escalade** après la dernière relance.
- **Paiements simulés** (mobile money, virement, espèces, chèque) rattachés aux échéances.
- **Classification IA** des réponses clients (déjà payé, promesse, contestation, demande d'échéancier, demande de délai, demande de copie, autre) avec seuil de confiance et reprise humaine.
- **Journal** en ajout seulement et **tableau de bord** où chaque chiffre renvoie aux pièces qui l'expliquent.
- **Fonctionnement local** : seule la classification utilise le réseau ; sans elle, tout le reste continue.

## 2. Architecture

```text
Interface web ──► API back-end locale (Python, FastAPI) ──► SQLite locale
                       │  ├─ moteur de règles (soldes, statuts, priorisation)
                       │  ├─ relances (planification, revérification, envoi simulé)
                       │  ├─ revue humaine et journal
                       │  └─ module IA ──► API du LLM (service externe)
                       └─ canaux simulés (WhatsApp, courriel) et paiements simulés
```

```text
recouvrement-api/
├── app/            code : domaine, services, API, IA, tâches de fond
├── dataset/        jeu de données fictif et vérité terrain
├── docs/           cahier des charges, données, IA, spécification du back-end
├── tests/          tests automatisés
├── Makefile
└── .env.example
```

## 3. Prérequis

- Python 3.11 ou plus récent
- `make` (sous Windows : WSL, ou lancer les commandes du Makefile à la main)
- Une clé d'API du LLM, **facultative** : sans elle, les messages restent « à classer » et peuvent être classés à la main

## 4. Installation

```bash
git clone <url-du-depot>
cd recouvrement-api
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
make install
cp .env.example .env             # puis renseigner .env (voir section 5)
```

## 5. Configuration

La configuration technique se fait dans `.env` (jamais versionné). Les paramètres métier (seuils, délais, date de référence) sont dans la table `parametres` et se modifient par l'API.

| Variable | Rôle | Valeur par défaut |
| --- | --- | --- |
| `DATABASE_PATH` | Fichier SQLite | `./data/recouvrement.db` |
| `DATASET_DIR` | Dossier du jeu de données | `./dataset` |
| `DEMO_HOOKS_ENABLED` | Active réinitialisation, changement de date et simulations | `true` |
| `CORS_ORIGINS` | Origines autorisées pour l'interface | `http://localhost:5173` |
| `SESSION_TTL_HEURES` | Durée de vie d'une session | `8` |
| `SEED_MDP_GESTIONNAIRE` | Mot de passe de démonstration du compte gestionnaire | à définir |
| `SEED_MDP_VALIDATEUR` | Mot de passe de démonstration du compte validateur | à définir |
| `LLM_FOURNISSEUR` | Fournisseur du LLM | `gemini` |
| `LLM_MODELE` | Identifiant exact du modèle | à confirmer |
| `LLM_API_KEY` | Clé d'API du LLM (facultative) | vide |
| `LLM_TIMEOUT_SECONDES` | Délai maximal d'un appel | `15` |
| `LLM_REESSAIS` | Nombre de nouvelles tentatives | `2` |
| `LOG_LEVEL` | Niveau de journalisation technique | `INFO` |

Aucun secret ne doit figurer dans le dépôt, les journaux ou ce README.

## 6. Lancement

```bash
make reset      # charge le jeu de données (date de référence 2026-12-15)
make run        # lance l'API sur http://localhost:8000
```

- Documentation interactive de l'API : `http://localhost:8000/docs`
- Vérification : `GET http://localhost:8000/api/sante`
- Interface de démonstration : à compléter par la personne en charge de l'interface (commande de lancement et adresse).

## 7. Comptes de test

Deux comptes de démonstration sont créés par `make reset`. Leurs mots de passe viennent de `.env` ; ce sont des comptes fictifs, à ne jamais réutiliser ailleurs.

| Nom d'utilisateur | Rôle | Droits principaux |
| --- | --- | --- |
| `gestionnaire` | GESTIONNAIRE | Consulter, importer, enregistrer paiements et avoirs, planifier et envoyer des relances, classer des messages, traiter la plupart des revues |
| `validateur` | VALIDATEUR | Tout ce que fait le gestionnaire, plus : valider ou rejeter les relances de gros montant, clôturer les contestations, accepter les accords d'échéancier, modifier les paramètres, réinitialiser les données |

## 8. Jeu de données et réinitialisation

Le jeu de données est fictif et généré par un script à graine fixe : mêmes entrées, mêmes fichiers. Il contient 30 clients, 120 factures, environ 150 échéances et environ 90 paiements, ainsi que 400 messages clients étiquetés pour évaluer l'IA.

- **Date de référence** : 2026-12-15 (un mardi). Tous les calculs et décisions en dépendent, ce qui les rend reproductibles.
- **Réinitialiser** : `make reset` (moins de 10 secondes). La même opération existe par `POST /api/admin/reset` si `DEMO_HOOKS_ENABLED` est vrai.
- **Avancer le temps** : `POST /api/admin/avancer` avec le nombre de jours, pour simuler les jours suivants.
- **Vérité terrain** : `dataset/verite_terrain/` contient les résultats attendus (statuts, soldes, affectations, priorisation, relances jour par jour). Ne jamais la modifier pour faire passer un test.

## 9. Reproduire les scénarios

Chaque scénario est un test nommé `test_Sxx_...`, dont la description et le résultat attendu sont dans `dataset/verite_terrain/scenarios/Sxx.json`.

```bash
make test                              # tous les tests, scénarios compris
pytest tests/test_scenarios.py -k S07  # un scénario précis
```

| # | Scénario |
| --- | --- |
| S01 | Import nominal rejoué deux fois : aucun doublon |
| S02 | Import avec défauts : rejets motivés |
| S03 | Soldes, statuts et paiement partiel |
| S04 | Paiement couvrant plusieurs factures du même client |
| S05 | Paiement ambigu : non affecté, en revue |
| S06 | Paiement rejoué : aucune double comptabilisation |
| S07 | Relance annulée : paiement reçu entre la préparation et l'envoi |
| S08 | Traitements concurrents : une seule action |
| S09 | Gros montant : validation humaine avant envoi |
| S10 | Contestation : suspension puis reprise |
| S11 | Promesse tenue ou non tenue |
| S12 | Échéancier : relance sur la tranche manquée seulement |
| S13 | Échéances le même jour : un message regroupé |
| S14 | Import tardif : R1 puis R2 et R3 espacés |
| S15 | Report d'envoi un dimanche ou un jour férié |
| S16 | Rappel P sauté |
| S17 | Réponse « déjà payé » : revue, jamais de marquage automatique |
| S18 | Réponse à faible confiance : revue |
| S19 | Reprise après interruption en plein lot |
| S20 | Consentement absent ou canal invalide |
| S21 | Avoir couvrant le solde : relances annulées |
| S22 | Escalade après R3 |
| S23 | API du LLM indisponible : messages « à classer », reste du système fonctionnel |

**Démonstration manuelle en 3 minutes** : la séquence d'appels est décrite dans `docs/` (spécification du back-end, section 16) : connexion, tableau de bord, priorisation, planification, validation d'un gros montant, paiement puis envoi, messages clients, panne du LLM, reprise d'un lot interrompu, explication d'un résultat.

## 10. Tests

```bash
make test       # pytest, sans accès réseau
make lint       # style
```

Les tests n'utilisent jamais la vraie API du LLM : un faux modèle le remplace. Ils vérifient en particulier que le système retrouve **exactement** la vérité terrain du jeu de données (statuts, soldes, affectations, priorisation, relances jour par jour), l'idempotence, la concurrence, la reprise après interruption, la sécurité des routes et le journal.

Résultats à reporter ici au moment du gel :

| Mesure | Valeur |
| --- | --- |
| Tests passés | à compléter |
| Couverture de `app/domain` et `app/services` | à compléter |

## 11. IA : modèle, mode dégradé, évaluation

- **Tâche** : classer le message d'un client en 7 catégories et en extraire la date promise, le montant et la facture citée. L'IA ne modifie jamais un solde, un paiement ou un statut, et n'écrit aucun message.
- **Modèle** : Gemini 3.8 Flash, via une offre gratuite avec quota ; identifiant de version exact à déclarer dans la fiche IA.
- **Sans clé d'API ou en cas de panne** : les messages restent « à classer », les relances des factures concernées sont suspendues, et la classification peut se faire à la main. Le reste du système fonctionne.
- **Seuils de confiance** : un message n'entraîne d'action automatique que si sa confiance dépasse le seuil de sa catégorie ; sinon une personne reprend la main.
- **Évaluation** : jeu de développement de 100 messages, jeu de test de 300 messages utilisé une seule fois après gel, comparaison à une règle simple par mots-clés. Résultats et limites dans la fiche IA.

## 12. Sécurité et limites

- Données entièrement fictives ; aucun secret ni donnée sensible dans le dépôt.
- Accès par comptes à deux rôles, jetons de session à durée limitée, mots de passe hachés.
- Toute action sensible est transactionnelle et inscrite dans un journal en ajout seulement.
- Les messages des clients sont traités comme des données non fiables par l'IA.

**Limites connues**

- Prototype de démonstration : pas d'envoi, de paiement ni de facturation réels, pas d'intégration WhatsApp, mobile money ou facture normalisée.
- Montants TTC en FCFA ; pas de TVA ni de comptabilité ; les pénalités de retard sont informatives et ne s'ajoutent pas au solde.
- Français uniquement ; les messages en langues locales sont une limite connue.
- La classification n'a pas accès au contexte d'une conversation.
- Un accord d'échéancier n'est possible que sur une facture sans paiement.

**Étapes d'une éventuelle expérimentation** : connecteurs réels (WhatsApp, courriel, mobile money), hébergement et contrat de données pour le LLM, relecture comptable et juridique des règles (pénalités, mentions), jeu de données réel anonymisé.

## 13. Dépendances, modèles et licences

À figer et à vérifier à la date de gel (versions exactes dans `pyproject.toml`).

| Composant | Rôle | Version | Licence |
| --- | --- | --- | --- |
| FastAPI | API | à compléter | MIT |
| Uvicorn | Serveur | à compléter | BSD-3-Clause |
| Pydantic | Validation des schémas | à compléter | MIT |
| python-multipart | Import de fichiers | à compléter | Apache-2.0 |
| httpx | Appels au LLM | à compléter | BSD-3-Clause |
| pytest | Tests | à compléter | MIT |
| SQLite | Base de données (module standard de Python) | incluse avec Python | Domaine public |
| Gemini 3.8 Flash | Classification (service externe) | à confirmer | Conditions du fournisseur |

Composants préexistants et code généré par IA : à déclarer ici (outils d'assistance au développement utilisés, bibliothèques de l'interface).

## 14. Documentation

| Document | Contenu |
| --- | --- |
| `docs/cahier-des-charges.md` | Périmètre, décisions, modèle de données, règles métier |
| `docs/donnees.md` | Génération du jeu de données, vérité terrain, scénarios |
| `docs/ia.md` | Contrat du classifieur, seuils, évaluation, fiche IA |
| `docs/specification-backend.md` | Schéma SQL, algorithmes, API, tests, jalons |
| `openapi.json` | Contrat d'API exporté |
| `docs/QUESTIONS.md` | Questions et ambiguïtés relevées pendant le développement |

Livrables du TDR : le rapport de 3 à 5 pages, la fiche IA et la vidéo de 2 à 3 minutes accompagnent ce dépôt.

## 15. Version remise

| Élément | Valeur |
| --- | --- |
| Commit gelé | à compléter |
| Date et heure du gel | à compléter |
| Vidéo de démonstration | à compléter |
| Équipe | à compléter |
