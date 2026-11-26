# Jeu de données fictif – recouvrement BWAI 2026

Jeu **entièrement fictif**, déterministe (graine `20261215`), régénérable en une commande :

```bash
python generate_dataset.py --seed 20261215 --out dataset/     # depuis la racine du dépôt
python tests_coherence.py                                   # les 16 contrôles de cohérence
python _composer_messages.py                                # étape distincte : 340 messages figés
```

Date de référence : **2026-12-15** (mardi). Aucun accès réseau, aucune dépendance au-delà de
la bibliothèque standard de Python (3.11 ou plus).

## Contenu

| Dossier | Rôle |
| --- | --- |
| `lot_nominal/` | Portefeuille importé : 30 clients, 120 factures, 147 échéances, 84 paiements, 5 avoirs, jours fériés |
| `lot_defectueux/` | 25 unités d'import dont 15 rejets attendus (scénario S02) |
| `etat_initial/` | Dossiers en cours chargés par la réinitialisation : accords, contestations, promesses, 74 relances historiques |
| `evenements/` | Paiements et avoir à injecter pendant les scénarios (jamais chargés au départ) |
| `messages/` | 340 messages figés et étiquetés, fiches de rédaction des 60 messages à écrire à la main |
| `verite_terrain/` | Résultats attendus (statuts, soldes, affectations, priorisation, relances jour par jour) et 23 scénarios |

## Conventions propres à ce générateur

Le document de données laisse certains formats ouverts. Voici ce que fait ce jeu ; chaque point
est repris dans `docs/QUESTIONS.md` du dépôt.

- **`relances_attendues.csv`** : une ligne par jour ouvré, client et canal où quelque chose est
  décidé, du 2026-12-15 au 2027-01-05, sans événement injecté, gros montants validés et envoyés
  le jour même. La colonne `echeances` liste `ECH-xxxx:étape` séparés par `;` pour les décisions
  `PREPAREE`, `EN_ATTENTE_VALIDATION`, `SAUTEE` et `ABSORBEE` ; elle liste seulement les `ECH-xxxx`
  pour `SUSPENDUE` et `REVUE`. Une relance regroupée a l'étape `GROUPE` (son ton est l'étape la
  plus grave) ; ses lignes moins graves sont répétées en `ABSORBEE`.
- **Suspensions** : une ligne `SUSPENDUE` par jour, client, canal et motif, pour toute échéance
  candidate (ACTIVE, solde positif, facture valide) suspendue, même sans étape due.
- **Revues** : `CONSENTEMENT_ABSENT`, `CANAL_INVALIDE` et `ESCALADE` ne sont écrites qu'à la
  création de l'entrée (une seule fois par client ou par échéance). Une décision reportée par
  l'espacement ne produit aucune ligne : elle réapparaît le jour où elle est envoyée.
- **Motifs** : `GROS_MONTANT` l'emporte, puis `JOUR_NON_OUVRE_REPORTE` (date brute non ouvrée,
  préparée le jour ouvré suivant), puis `REGROUPE`.
- **Consentement** : le contrôle du consentement et du canal précède la création d'un rappel P
  sauté : un client sans consentement n'a aucune relance, pas même `SAUTEE`.
- **`affectations_attendues.csv`** : pour un avoir, la colonne `paiement_id` contient l'identifiant
  `AVO-xxxx` (mode `AUTO_ANCIENNETE`).
- **`priorisation.csv`** : les trois composantes sont arrondies à 2 décimales pour l'affichage ;
  le score est l'arrondi (à la hausse à .5) de la somme non arrondie. Historique : un client est
  « en retard » sur une facture soldée si un **paiement** (pas un avoir) est daté après l'échéance.
- **Lot défectueux** : `nb_lignes` compte les lignes de `clients.csv` et de `factures.csv`
  (25 = 4 + 21) ; les échéances sont validées avec leur facture. Un défaut d'échéance est rapporté
  sur la ligne de `echeances.csv`, un défaut de facture ou de client sur sa propre ligne
  (l'en-tête est la ligne 1). 15 rejets, 10 lignes acceptées.
- **Contestations** : `echeance_id` vide (portent sur la facture entière).
- **Contenu des relances historiques** : canevas de la spécification ; pour le courriel, la ligne
  `Objet : …` ouvre le contenu.
- **Messages** : les 340 messages générés sont figés dans `messages/messages_generes_figes.csv`
  (gabarits liés au portefeuille à la génération). Les 60 messages « écrits à la main »
  (`messages/redaction_main.csv`, colonnes `message_id`, `contenu`, `copie_demandee`, `date_kind`,
  `montant_promis`, `facture_mode`, `difficultes`) suivent les fiches de `fiches_redaction_main.csv`.
  **Faute de temps, ils ont été rédigés par Claude (Anthropic) à la demande de l'équipe, et non
  par des personnes** : c'est une limite pour la valeur de preuve de ce sous-ensemble (voir plus
  bas). Le client, le canal, la catégorie et le jeu viennent de la fiche ; la date de réception,
  le numéro de facture cité et la date promise sont liés de façon déterministe. La colonne `relu`
  vaut `NON` partout : la relecture croisée de 20 % des étiquettes reste à faire par l'équipe.

## Limites connues

- Noms d'entreprises et de personnes inventés : une relecture humaine reste nécessaire pour
  écarter toute ressemblance avec une entreprise réelle.
- Jours fériés : liste partielle (fêtes mobiles islamiques absentes) ; seuls 2026-12-25 et
  2027-01-01 comptent dans la fenêtre simulée.
- Expressions en fon et en yoruba : mots isolés mêlés au français, à faire relire par un
  locuteur avant toute évaluation sérieuse (catégorie `LANGUE_LOCALE`, limite connue).
- Les 400 messages ont été composés par Claude (Anthropic), donc par un modèle différent de
  celui qui classera (Gemini), mais les 340 premiers à partir de phrases-types : leur diversité
  réelle est inférieure à celle de messages saisis par des clients. Les 60 messages « à la main »
  n'ont **pas** été écrits par des humains, contrairement à la précaution du cahier des charges
  contre les scores gonflés : les remplacer par de vrais messages reste souhaitable.

## Empreintes SHA-256

| Fichier | SHA-256 |
| --- | --- |
| `_composer_messages.py` | `40314c755eec416381c53d47c222aaad7ecd26b259617457326bf56834a83d6c` |
| `etat_initial/accords_echeancier.csv` | `3f7c585b01e108d4be20d3d0f1e6cfd66c341bcc2548459d2127c8d7a883c95e` |
| `etat_initial/contestations.csv` | `d593bacce446e1c9df565cfa360cabae0d702529449f5c80e51f30e80176b829` |
| `etat_initial/promesses_paiement.csv` | `e5158053fd76a29b4999fc729ec61cf8c791867a68c84cedcb4c83b700516f47` |
| `etat_initial/relance_lignes_historique.csv` | `a53e1b6630a4892d069fa35b3966668ad0de4edfe98d8f4177abe1fe1cadb37f` |
| `etat_initial/relances_historique.csv` | `cbbe74e624b4bc5514914d1e57fdc72414d09c53a8a22e9423b1d0e3527b7719` |
| `evenements/avoir_couvrant.csv` | `3669b172359de1415335940b1533e895fd040fe909b434894126e5d0fd1c6408` |
| `evenements/paiement_ambigu.csv` | `2a0d988f6186e1ef3f2aed9a2dc4631a7a05f1cc95edb9f3b4e5b574c20bf59b` |
| `evenements/paiement_entre_preparation_et_envoi.csv` | `fabed926d870d633c60b816eea71e6bc88781c29d6e162c222ba687fef161480` |
| `evenements/paiement_multifactures.csv` | `60470b1d943ecdccf885d1f39b2ed81c9aa3e3f401894da1ff63ef02ca9fe7ef` |
| `evenements/paiement_promesse_tenue.csv` | `92b1879e5aa3a01ac75ab207fa396362cc076be99b8a4df716ceb3a71d335ee2` |
| `evenements/paiement_rejoue.csv` | `ea1aec3aedd63edf1d1ef0c68f45ffd74d8e11d4c0fc03b3ded1e80c6301530c` |
| `generate_dataset.py` | `21ea7bc7edc3413e784e27e3d8f5ccf85e11e3a71fc2bd24bd778d98de76f43a` |
| `lot_defectueux/clients.csv` | `57c47ea5e62ec04d239194c54cb5810443a9c823f27af538490b934d5d84fc99` |
| `lot_defectueux/echeances.csv` | `e6b7bba7983b52f48ebeaf40a13d7305d10a3756105ce78993720c3fcdf66747` |
| `lot_defectueux/factures.csv` | `136290fe4557042280e801cf4c58f1b051551c3b63761f103670ab39bd1f57e0` |
| `lot_defectueux/rejets_attendus.csv` | `f908e925a9a0cf6358bf5cc3c266d7ed422265a0e49b42430fe1318d6359c5a8` |
| `lot_nominal/avoirs.csv` | `127477f7f4f53f319461e495bb1b244693bf7daf673c323cd2940828bf1273c6` |
| `lot_nominal/clients.csv` | `00e69d0a3529617359d8019ca106fa39b7f6ce35a9884d10976924d8679b8481` |
| `lot_nominal/echeances.csv` | `9010eb8ecfa93172b8cca291fbeb2efe3e86d20b3a761abc31d674ee889070db` |
| `lot_nominal/factures.csv` | `ee7022f8a574af69df2fedc71982f36f9a1f5d6c4ff7bbbe6bde4610360bfcaa` |
| `lot_nominal/jours_feries.csv` | `70bd8e5622c50294e3cf732dda27c63868c720fb76d152116769e324cedb62ed` |
| `lot_nominal/paiements.csv` | `7f9c2d274b3d1862a10923e171eddc6ade81358d17e133254276587a484a7390` |
| `lot_nominal/preferences_contact.csv` | `349afcb670cc9e86c9083e6dffa71c8a5b7a82c762de3348eefc093420b05e42` |
| `messages/etiquettes.csv` | `860517ea5ac507623beb565aec716a1e22c47037c6ff50a38d16675eb61b1e87` |
| `messages/fiches_redaction_main.csv` | `64f8428e89c261e3b3c70f6936eb35727f782c8c713395ba5f4baff78ec755b3` |
| `messages/messages_clients.csv` | `b28a14224d356c298c021ba5f8d6b8559a3224daea544ad0132d291fecf1c7ef` |
| `messages/messages_generes_figes.csv` | `6e9021e8cb3860f486ebbba9c2cf01b08897413f34c73f4d82b463098ca7ee20` |
| `messages/redaction_main.csv` | `824e5389617c207734581d4528ea2b62295ad2429fe184ed34a4702b21cbc9c2` |
| `params.json` | `cd5aa621f705082c20e392b45ee03fd1470ecdc5e1c0007730105e0dd673453a` |
| `tests_coherence.py` | `3a1b8734b02eb6ffea59a40f560af39dabd9832b192aa2d80ea52d698fc4a6b9` |
| `verite_terrain/affectations_attendues.csv` | `ada21f8ba93990aa261948f3bc481c342c3cda50c706d00e9a69c9604c6da683` |
| `verite_terrain/priorisation.csv` | `185c8d2c458d99e098b54495234bef96bfe27020656fa861438a29e4989617c0` |
| `verite_terrain/relances_attendues.csv` | `3c8ebd1d1682ce34db9186983429262513705b4d01c4f3f5051a88d3a4e1dd46` |
| `verite_terrain/scenarios/S01.json` | `670886a693dcc833cf6f1558c1e0a7367e73a50fab79bfe4b45c4c33c8cabb7e` |
| `verite_terrain/scenarios/S02.json` | `9064aabbb9de483cfd51c91699ff07dcb9211252a1a0c431229d29c77c4381d2` |
| `verite_terrain/scenarios/S03.json` | `e71d7db3966964f9ed4c845f72d2ae687641885a4ed3faf7d7d2313ea95264de` |
| `verite_terrain/scenarios/S04.json` | `2f44569c05c3d46c569dd40b1f47d52ea8d10e45c5efc99b41013ed09f8c9680` |
| `verite_terrain/scenarios/S05.json` | `d76f8ef5a9ce6a88e59a270c2fe7e25120c1aae27bc3bbf5b5bc4a1eec6b748f` |
| `verite_terrain/scenarios/S06.json` | `6bfec58f32c5864f42689b335135f66eeda5c9ce8764b0e3ffb66f900c0d883c` |
| `verite_terrain/scenarios/S07.json` | `e1dd1e23f0eb36449f377242bfbd0fa87258a1c79163f1aed2ca3c38accb6029` |
| `verite_terrain/scenarios/S08.json` | `5c70f47d232602d5b17a83f4aa99cd8b3f545497f4be0e74d56feab6e1b13da6` |
| `verite_terrain/scenarios/S09.json` | `c02439a115ccc13bc89484192f37a46a2b6fbc5eb8808a6a0c9df841723d348a` |
| `verite_terrain/scenarios/S10.json` | `cebf391e65a5815a91a707747d3c5f48919e8ff542d8a9c827e6ec101e9cdc0c` |
| `verite_terrain/scenarios/S11.json` | `89eb7d4e4c48119d85c40f9efa02639546f341d27ba401a74cfeadaa82404194` |
| `verite_terrain/scenarios/S12.json` | `9a8f2abb3a4d948ce4cc2e778f37f813101370204bd830766fb0c7871776ac8c` |
| `verite_terrain/scenarios/S13.json` | `04e3374cb791836f56098819a3f6fd02abb3af1c83ed2e1a9f99a9ebd7fd8089` |
| `verite_terrain/scenarios/S14.json` | `10d34c31560c909c8ec2425f2cda588c73d65b9d9b930d5fc4fddd4bfdd56742` |
| `verite_terrain/scenarios/S15.json` | `ea475ccfadf73210541809be77cbe606c048b0ae80587f7df928e3f8713cc291` |
| `verite_terrain/scenarios/S16.json` | `febb6899b28b33e6a9393f062e38ae8844aa5662c356076620ed7e4e766f0511` |
| `verite_terrain/scenarios/S17.json` | `76182b7f906d4bd04d0eddc54f7834892dcca7c5f7b29cbb0cb8cdc2d8ecf02b` |
| `verite_terrain/scenarios/S18.json` | `1c7163bc1db172ab60b5508d6ea0a1880a37e99e4ad8411d2cbd0540fad6b198` |
| `verite_terrain/scenarios/S19.json` | `4b465a58de56fbac1051fc4c5c1623e35cd765b0e511ba8075a6e3c11da03785` |
| `verite_terrain/scenarios/S20.json` | `974d324109981dae447ba097bd9e45fb6eb77bb400d4566099ccdf655a9fa5ba` |
| `verite_terrain/scenarios/S21.json` | `18cc6ce87ed86969949bc6c023a0b37ea2fb7289fd3e2594c1647cf83d3f4957` |
| `verite_terrain/scenarios/S22.json` | `b66e3e49a87532f62cdda66d6749da4247b9557a27af0a1b7b08ef07859c5446` |
| `verite_terrain/scenarios/S23.json` | `19d379a9487ad2807530bcd7678e15701674af57510f748fa56207a04a426d84` |
| `verite_terrain/soldes_echeances.csv` | `07295bf9f24e9b1940773920e3c5ce6a5f94a3c7f3d2bb42e1a72fcfbbf7c5ad` |
| `verite_terrain/statuts_factures.csv` | `8ecce6e076ad0d0b16071580dce2dea46d41adbc1e7602a33eaf4fbaa21f8383` |
