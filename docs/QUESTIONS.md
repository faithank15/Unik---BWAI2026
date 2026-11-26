# Questions et ambiguïtés relevées

Ordre d'autorité en cas de contradiction : cahier des charges, puis spécification du back-end
pour les règles métier, puis document de données pour les formats de fichiers. Chaque entrée
donne la question, les options, la recommandation retenue et son statut. Une entrée
« Tranché » a été appliquée sans attendre une réponse ; elle reste révisable.

## A. Écarts entre documents (tranchés par l'ordre d'autorité)

### A1. Nombre de tables : 18 ou 23 ?
Le cahier des charges (section 5) annonce 18 tables ; la spécification (section 5) en compte 23
et 3 vues, car elle ajoute `utilisateurs`, `sessions`, `sequences`, `envois_simules` et
`traitements_lot`.
- Options : suivre le cahier (18) ou la spécification (23).
- **Recommandation retenue : 23 tables et 3 vues**, telles que la spécification les donne. Les
  cinq tables ajoutées sont des tables techniques que la spécification liste comme ajouts « à
  reporter dans le cahier si l'équipe les valide ».
- Statut : **Tranché.**

### A2. Nom de la route de la boîte d'envoi simulée
Le plan de tests (gabarit de la section 9) cite `/api/envois-simules` ; la spécification
(section 13) donne `GET /api/canaux/envois`.
- **Recommandation retenue : `GET /api/canaux/envois`.** Le plan de tests précise lui-même que
  ses noms de routes sont indicatifs et que la section 13 fait foi.
- Statut : **Tranché.**

### A3. Paiement partiel entre la planification et l'envoi (cas T-E03)
Le plan de tests laisse le choix entre « envoi avec le nouveau solde » et « nouvelle
planification ». La spécification (section 7.8 et section 14) relit le solde dans la
transaction d'envoi et n'annule que si le solde est nul.
- **Recommandation retenue : envoi avec le solde relu dans la transaction** ; la ligne n'est
  retirée que si le solde devient nul (`SOLDE_NUL`). Le message affiche le solde du moment de
  l'envoi, jamais celui de la planification.
- Statut : **Tranché.**

### A4. Code de rejet `IDENTIFIANT_EXISTANT_DIFFERENT`
La spécification (section 8.1) l'ajoute à la liste du document de données (« code ajouté »),
qui ne le connaît pas.
- **Recommandation retenue : l'implémenter** à l'import (même identifiant déjà en base avec
  d'autres valeurs). Le lot défectueux n'en contient aucun exemple, donc le scénario S02 reste
  à 15 rejets ; un test unitaire (cas T-I05) le couvre.
- Statut : **Tranché.**

## B. Choix du générateur de jeu de données

### B1. Facture 0042 : émission le 2026-12-14 ou échéance le 2026-12-16 ?
Le document dit « échéance le 2026-12-16, facture émise le 12-14 », mais aussi « l'échéance vaut
l'émission plus le délai de la condition de paiement » (au minimum 15 jours pour une condition
non comptant).
- Options : (a) émission le 12-14 sans respecter la condition ; (b) émission le **12-01** en
  `15_JOURS`, échéance le 12-16.
- **Recommandation retenue : (b).** Le comportement voulu (rappel P sauté avec le motif
  `P_TROP_PROCHE`) vient de la règle de la spécification 7.2 (P due le 12-13 est antérieure à la
  date de référence), pas de la date d'import.
- Statut : **Tranché.**

### B2. Retard des cinq partiellement payées échues : « 3 à 25 jours »
Un retard de 25 jours place R3 envoyée depuis plus de 5 jours et déclencherait une escalade, ce
qui contredit le scénario S22 (« les 2 factures de retard d'au moins 20 jours du bloc 0073 à
0086 »).
- **Recommandation retenue : retards de 3, 6, 12, 16 et 18 jours**, de sorte que seules les
  factures 0085 et 0086 escaladent au 2026-12-15.
- Statut : **Tranché.**

### B3. Échéances non échues « entre 4 et 60 jours »
Avec une émission au plus tard le 2026-12-14 et une condition de 60 jours au maximum, une
échéance ne dépasse pas le 2027-02-12.
- **Recommandation retenue : échéances jusqu'au 2027-02-10** (57 jours).
- Statut : **Tranché.**

### B4. Accord PROPOSE : combien d'échéances ?
« Chaque accord compte 4 échéances » vaut pour les accords acceptés ; un accord PROPOSE est sans
effet sur les échéances (spécification, section 10).
- **Recommandation retenue : la facture 0106 garde sa seule échéance ACTIVE.** Total de **147
  échéances** (« environ 150 ») : 120 + 12 tranches + 15 pour les cinq accords acceptés.
- Statut : **Tranché.**

### B5. Format de `relances_attendues.csv`
Le schéma ne dit pas comment représenter les échéances d'une relance regroupée, les lignes
absorbées, les suspensions ni les revues.
- **Recommandation retenue** (détaillée dans `dataset/README.md`) : `echeances` = liste
  `ECH-xxxx:étape` séparés par `;` pour les relances, liste d'`ECH-xxxx` pour les suspensions et
  les revues ; une ligne `SUSPENDUE` par jour et par motif ; revues écrites une seule fois ;
  aucune ligne pour un report d'espacement. Le test du jalon M2 lit ce format.
- Statut : **Tranché**, à confirmer avec la personne en charge du jeu si elle en produit un autre.

### B6. Motif d'une relance à la fois regroupée et reportée
`JOUR_NON_OUVRE_REPORTE` ou `REGROUPE` ?
- **Recommandation retenue : `GROS_MONTANT`, puis `JOUR_NON_OUVRE_REPORTE`, puis `REGROUPE`.**
  Le report est l'information la plus utile pour la scène « dimanche et jour férié » (S15).
- Statut : **Tranché.**

### B7. Client sans consentement : rappel P sauté ou revue ?
La spécification (7.1 et 7.3) crée la relance `SAUTEE` à l'étape 5 et traite le consentement au
regroupement.
- **Recommandation retenue : contrôler le consentement et le canal avant de créer un rappel P
  sauté.** Un client sans consentement n'a donc aucune relance, ce que dit le document de
  données (« envoi interdit, dossier en revue »).
- Statut : **Tranché** ; le moteur du jalon M2 applique le même ordre.

### B8. Avoirs dans `affectations_attendues.csv`
La colonne se nomme `paiement_id` alors qu'un avoir n'est pas un paiement.
- **Recommandation retenue : y inscrire l'identifiant `AVO-xxxx`.** Le préfixe lève l'ambiguïté.
- Statut : **Tranché.**

### B9. Lot défectueux : qu'est-ce qu'une « ligne » ?
Le document compte 25 unités (15 rejets, 10 acceptées) mais une facture rejetée entraîne aussi le
rejet de ses échéances.
- **Recommandation retenue : `nb_lignes` = lignes de `clients.csv` + lignes de `factures.csv`
  (4 + 21) ; chaque rejet est rapporté une fois, sur la ligne qui porte le défaut.**
- Statut : **Tranché.**

### B10. S01 et les accords : `echeances.csv` référence des accords
Une échéance de tranche porte `accord_id`, clé étrangère vers `accords_echeancier`, qui ne fait
pas partie des fichiers importés par l'API.
- Options : (a) charger `accords_echeancier.csv` avant l'import ; (b) accepter un fichier
  `accords_echeancier` optionnel dans l'import ; (c) ignorer `accord_id` à l'import.
- **Recommandation : (b).** À trancher au jalon M1 avec le test S01.
- Statut : **Tranché au jalon M1 : option (b).** L'import accepte un fichier
  `accords_echeancier` facultatif, inclus dans l'empreinte ; le lot nominal en compte donc cinq
  (quatre fichiers de `lot_nominal/` plus `etat_initial/accords_echeancier.csv`) et `reset`
  enregistre cette empreinte (S01 rejoué après un `reset` répond DEJA_IMPORTE).

### B11. 60 messages « à la main »
Le cahier des charges demande 60 messages écrits à la main par l'équipe (précaution contre des
scores gonflés quand le même modèle génère et classe).
- **Recommandation retenue (faute de temps)** : les 60 messages ont été rédigés par Claude
  (Anthropic) à la demande de l'équipe, d'après les fiches de rédaction, et fusionnés
  (`dataset/messages/redaction_main.csv`). Le jeu compte donc 400 messages. Claude étant un
  modèle différent de celui qui classera (Gemini), la règle « le modèle qui classe n'a pas généré
  les messages » reste respectée ; en revanche ces 60 messages ne sont pas écrits par des humains.
  À remplacer par de vrais messages si l'équipe en a le temps. À déclarer dans la fiche IA.
- Les étiquettes `relu` sont toutes à `NON` (relecture croisée de 20 % à faire).
- Statut : **Tranché** (limite déclarée).

### B12. Noms et langues locales
Les raisons sociales et les noms de personnes sont inventés ; les mots de fon et de yoruba des
messages `LANGUE_LOCALE` n'ont pas été relus par un locuteur.
- Statut : **Ouvert** (relecture humaine, voir `dataset/README.md`).

## C. Choix d'implémentation (jalon M1)

### C1. Erreur de validation : 400 ou 422 ?
Le plan de tests (T-H03) cite 422 pour un corps mal formé ; la spécification (section 4) donne
400 `VALIDATION` et réserve 422 aux règles métier.
- **Recommandation retenue : 400 `VALIDATION`** (la spécification prévaut), 422 `REGLE_METIER`
  pour les violations de règle (`details.regle`).
- Statut : **Tranché.**

### C2. Codes de rejet d'import hors liste
Le document de données ne couvre pas : valeur d'énumération invalide, facture ou accord inconnu
pour une échéance, raison sociale déjà prise par un autre identifiant, montant non entier.
- **Recommandation retenue : `VALEUR_INVALIDE`, `FACTURE_INCONNUE`, `ACCORD_INCONNU`,
  `IDENTIFIANT_EXISTANT_DIFFERENT` (raison sociale en double) et `MONTANT_NON_POSITIF` (montant
  non entier).** Le lot défectueux n'en contient aucun, le scénario S02 est inchangé.
- Statut : **Tranché.**

### C3. Rapport d'import : une cause, un rejet
Une facture rejetée entraîne le rejet de ses échéances ; lister chaque ligne aurait donné plus de
15 rejets pour le lot défectueux (S02).
- **Recommandation retenue** (cohérente avec B9) : un rejet par cause, sur la ligne qui porte le
  défaut ; les lignes rejetées par ricochet ne figurent pas au rapport. `nb_lignes` compte les
  lignes de clients, préférences, factures et accords.
- Statut : **Tranché.**

### C4. Identifiants des affectations et des événements injectés
La spécification ne donne pas de préfixe pour les affectations.
- **Recommandation retenue : `AFF-NNNN`** (séquence). Dans le jeu de données, chaque fichier
  d'événements se rejoue seul sur l'état initial : tous ont l'identifiant `PAY-0085`.
- Statut : **Tranché.**

### C5. Date d'un paiement ou d'un avoir
- **Recommandation retenue : refus 422 `DATE_FUTURE` si la date dépasse `date_reference`**
  (cas T-Y05 du plan de tests, qui laisse le choix entre refus et mise en attente).
- Statut : **Tranché.**

### C6. Événements ajoutés au catalogue du journal
`PREFERENCES_MODIFIEES` (mise à jour des préférences de contact). Le journal reste en ajout seul.
- Statut : **Tranché.**

### C7. Filtre `suspendue` des factures
Il dépend du calcul des suspensions (moteur de relances).
- **Recommandation : l'ajouter au jalon M2**, avec `/api/relances/suspensions`.
- Statut : **Reporté au M2.**

## D. Choix d'implémentation (jalon M2)

### D1. Motif porté par une relance envoyée
La table `relances` n'a pas de colonne dédiée au motif de planification.
- **Recommandation retenue** : `relances.motif` porte `GROS_MONTANT`, `JOUR_NON_OUVRE_REPORTE` ou
  `REGROUPE` dès la planification et le garde après l'envoi ; pour une relance annulée ou sautée
  il porte le motif d'annulation ou de saut.
- Statut : **Tranché.**

### D2. Interruption de lot de démonstration
`simulation_interruption_apres` doit permettre « interrompre puis reprendre » avec deux appels
identiques à `/api/relances/envoyer` (scénario de démonstration, étape 10).
- **Recommandation retenue** : la simulation est consommée à l'interruption (paramètre remis à
  vide et journalisé), la reprise va donc jusqu'au bout.
- Statut : **Tranché.**

### D3. Relance annulée : lignes conservées
Quand toutes les lignes d'une relance sont injustifiées, la relance passe à ANNULEE et garde ses
lignes (comme l'historique du jeu de données) ; les étapes restent « traitées ». Quand seule une
partie est injustifiée, les lignes sont retirées (événement `LIGNE_RETIREE`) et leurs étapes
redeviennent candidates.
- Statut : **Tranché.**

### D4. Suspension par message : portée
Facture citée, sinon toutes les factures du client ; les messages classés `DEMANDE_COPIE_FACTURE`
ne suspendent pas (décision du document IA).
- Statut : **Tranché** (déjà acté dans la spécification).

## E. Choix d'implémentation (jalon M3)

### E1. Tranches d'un accord proposé
La table `accords_echeancier` ne stocke que `nb_tranches`, pas les dates ni les montants.
- **Recommandation retenue** : les tranches proposées sont conservées dans l'événement
  `ACCORD_PROPOSE` du journal (en ajout seulement, donc non modifiables) et relues à
  l'acceptation. Alternative : une colonne JSON dans `accords_echeancier` (changement de schéma).
- Statut : **Tranché.**

### E2. Client réel du LLM non testé
`app/ia/gemini.py` n'a jamais tourné contre l'API (aucune clé, aucun réseau). L'identifiant exact
du modèle, le format de réponse et les quotas sont à vérifier à l'essai réel (`make eval-ia`,
jalon M5). Tout le flux est testé avec le faux LLM.
- Statut : **Ouvert.**

### E3. Messages sans facture identifiable
Contestation, promesse ou délai sans facture identifiable : aucune action automatique, revue
(`LITIGE` ou `PROMESSE_A_VALIDER` motif `FACTURE_NON_IDENTIFIABLE`). Une facture est
identifiable si le modèle en cite une qui est ouverte, si le message en cite une, ou si le client
n'en a qu'une d'ouverte.
- Statut : **Tranché.**

### E4. Résolution d'une revue de message
Quand toutes les revues ouvertes d'un message sont résolues par `POST /api/revue/{id}/resoudre`,
le message passe à `TRAITE` et ses relances reprennent (la suspension par message disparaît).
- Statut : **Tranché.**

### E5. `DEJA_PAYE` validé par une personne
Aucun paiement n'est créé ni marqué : la vérification se fait par les routes de paiement
habituelles. La validation de catégorie résout seulement la revue et lève la suspension.
- Statut : **Tranché** (règle absolue : l'IA et la classification ne modifient jamais un paiement).

## F. Choix d'implémentation (jalon M4)

### F1. Périmètre temporel des compteurs de relances
Le tableau de bord donne « les comptes par statut à la date de référence ».
- **Recommandation retenue** : les relances dont `date_prevue` est la date de référence ; le
  lien associé (`/api/relances?date=…&statut=…`) retrouve exactement la liste.
- Statut : **Tranché.**

### F2. Retard moyen et taux de promesses tenues
Retard moyen : moyenne des retards des échéances en retard, arrondie à une décimale. Taux de
promesses tenues : TENUE / (TENUE + NON_TENUE), 0,0 sans promesse jugée.
- Statut : **Tranché.**

### F3. Comparaison à la référence
Règle naïve : une relance par échéance en retard. Relances injustifiées : échéances en retard
suspendues (contestation, promesse, accord, message en attente). Le gain est mesuré à la date de
référence ; le temps gagné se mesure à part, par chronométrage manuel sur 20 dossiers.
- Statut : **Tranché** (le chronométrage reste une action de l'équipe).

### F4. Explication d'une facture
Les relances historiques (sans événement de journal) sont présentées comme « antérieures au
chargement » (`anterieure_au_chargement`), comme le demande la spécification. La liste des règles
de statut écartées reprend les règles passées avant celle qui s'applique, avec leur motif.
- Statut : **Tranché.**

## G. Durcissement (jalon M5)

### G1. Export CSV
La spécification demande de préfixer d'une apostrophe toute valeur d'export CSV commençant par
`=`, `+`, `-` ou `@`, mais la section 13 ne définit aucune route d'export.
- **Recommandation retenue** : fonction `neutraliser_formule` prête et testée ; aucune route
  d'export n'est ajoutée (hors périmètre de la section 13).
- Statut : **Tranché.**

### G2. Évaluation du modèle réel
`make eval-ia` évalue toujours la règle simple sur DEV ; il évalue aussi le modèle réel si
`LLM_API_KEY` est renseignée. Le jeu TEST exige `make eval-ia-test` (`--confirmer-gel`) pour
rappeler qu'il ne s'utilise qu'une fois, après gel du modèle, de la consigne et des seuils.
Les résultats du modèle réel, le calibrage des seuils et la fiche IA restent à produire.
- Statut : **Ouvert** (dépend de la clé, du quota et de l'identifiant exact du modèle).

### G3. Dérogations aux seuils de performance
Les seuils de performance du plan de tests (T-PF) sont indicatifs ; ils passent largement sur la
machine de développement (planification d'une journée < 2 s, tableau de bord < 0,5 s).
- Statut : **Tranché.**

## H. Structure du dépôt et client LLM réel

### H1. Back-end dans `backend/`
Le dépôt accueillera un front-end : tout le back-end (app, tests, dataset, scripts, Makefile,
`pyproject.toml`, `.env`, `openapi.json`) est dans `backend/`. Un `Makefile` à la racine renvoie
vers lui (`make test` = `make -C backend test`). Les documents de référence et ce fichier restent
dans `docs/` à la racine, partagés avec le front-end.
- Statut : **Tranché.**

### H2. Modèle retenu : `gemini-3.1-flash-lite` plutôt que `gemini-3.8-flash`
« Gemini 3.8 Flash » correspond à l'identifiant exact `gemini-3.8-flash` (relevé dans la liste des
modèles de l'API avec la clé du projet). Mais sur l'offre gratuite son quota est de **20
requêtes par jour et par projet** (erreur 429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`),
alors que le document IA prévoit environ 400 messages plus les itérations de consigne ; l'API y a
aussi souvent répondu 503 (« forte demande ») ou dépassé le délai.
- Essai comparatif sur 10 messages DEV : `gemini-3.1-flash-lite` 10 réponses sur 10, 10 bonnes
  catégories, latence médiane 2,4 s ; `gemini-3-flash-preview` 9 sur 10 (1,5 s) ; les autres
  modèles testés ont renvoyé 429 ou dépassé le délai.
- **Recommandation retenue** : `gemini-3.1-flash-lite` (le « second modèle de secours » prévu par
  le document IA), dont l'évaluation complète sur DEV est dans
  `docs/rapport_ia_dev_gemini-3.1-flash-lite.md`. Grok (xAI) n'a pas été essayé : aucune clé
  disponible, et un modèle Gemini performant répondait déjà ; l'adaptateur isole le fournisseur,
  un client xAI pourrait s'ajouter sans toucher au reste.
- Pour revenir au 3.8 : activer la facturation du projet, régler `LLM_MODELE=gemini-3.8-flash`,
  réévaluer sur DEV avant de geler.
- Statut : **Tranché**, à confirmer par l'équipe (la fiche IA doit déclarer le modèle réel).

### H3. Disponibilité de l'API
Les appels réels peuvent recevoir 503 (« forte demande »), 429 (quota) ou dépasser le délai.
Conséquences prévues et testées : réessais espacés, coupe-circuit, mode dégradé (message « à
classer »), délai de 30 s en configuration (90 s pour l'évaluation) et reprise sur cache pour
l'évaluation (`make eval-ia`). Une chute du modèle ne bloque jamais le reste du système.
- Statut : **Tranché** (à surveiller avant la démonstration).

### H4. Cibles du plan de tests pour l'IA
La cible « taux de revue ≤ 40 % » est incompatible avec la règle de la spécification (toute
catégorie sensible, soit environ 70 % des messages, passe en revue humaine). Les cibles de
précision automatique et d'erreurs critiques non rattrapées sont respectées sur DEV.
- Statut : **Ouvert** (à ajuster avec l'équipe dans la fiche IA).
