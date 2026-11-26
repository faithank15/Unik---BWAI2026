# LLM – jeu DEV

Messages évalués : 100

| Mesure | Valeur |
| --- | --- |
| Exactitude globale | 95.0% |
| F1 macro | 0.95 |
| Taux de revue | 86.0% |
| Précision automatique | 1.0 |
| Exactitude des dates promises | 0.92 |
| Dates inventées | 0.0 |
| Erreurs critiques non rattrapées (C1 à C4) | 0 |
| copie_demandee F1 | 0.963 |
| Latence médiane / p95 (s) | 3.091 / 14.598 |

## Par catégorie

| Catégorie | Précision | Rappel | F1 | Support |
| --- | --- | --- | --- | --- |
| DEJA_PAYE | 1.0 | 1.0 | 1.0 | 15 |
| PROMESSE_PAIEMENT | 0.9091 | 1.0 | 0.9524 | 20 |
| CONTESTATION | 0.8824 | 1.0 | 0.9375 | 15 |
| DEMANDE_ECHEANCIER | 1.0 | 1.0 | 1.0 | 10 |
| DEMANDE_DELAI | 1.0 | 0.8 | 0.8889 | 10 |
| DEMANDE_COPIE_FACTURE | 0.9091 | 1.0 | 0.9524 | 10 |
| AUTRE_INCERTAIN | 1.0 | 0.85 | 0.9189 | 20 |

## Erreurs critiques

| Code | Total | Non rattrapées |
| --- | --- | --- |
| C1 | 0 | 0 |
| C2 | 0 | 0 |
| C3 | 0 | 0 |
| C4 | 0 | 0 |

## Par difficulté

| Difficulté | n | Exactitude |
| --- | --- | --- |
| AUCUNE | 64 | 0.9688 |
| DATE_RELATIVE | 11 | 0.9091 |
| HORS_SUJET_OU_VIDE | 3 | 1.0 |
| INJECTION | 5 | 1.0 |
| LANGUE_LOCALE | 3 | 1.0 |
| MAUVAISE_REFERENCE | 4 | 0.75 |
| MULTI_INTENTION | 4 | 1.0 |
| NEGATION | 7 | 0.8571 |
| TIERS | 3 | 1.0 |

## Matrice de confusion (lignes : étiquette, colonnes : prédiction)

| |DEJA_PAYE|PROMESSE_|CONTESTAT|DEMANDE_E|DEMANDE_D|DEMANDE_C|AUTRE_INC|
| --- | --- | --- | --- | --- | --- | --- | --- |
| DEJA_PAYE |15|0|0|0|0|0|0|
| PROMESSE_PAI |0|20|0|0|0|0|0|
| CONTESTATION |0|0|15|0|0|0|0|
| DEMANDE_ECHE |0|0|0|10|0|0|0|
| DEMANDE_DELA |0|2|0|0|8|0|0|
| DEMANDE_COPI |0|0|0|0|0|10|0|
| AUTRE_INCERT |0|0|2|0|0|1|17|

## Seuils (cibles : {'critiques': 0, 'precision_min': 0.95, 'revue_max': 0.4})

Seuil retenu : None

| Seuil | Revue | Précision auto | Critiques non rattrapées |
| --- | --- | --- | --- |
| 0.5 | 0.86 | 1.0 | 0 |
| 0.55 | 0.86 | 1.0 | 0 |
| 0.6 | 0.86 | 1.0 | 0 |
| 0.65 | 0.86 | 1.0 | 0 |
| 0.7 | 0.86 | 1.0 | 0 |
| 0.75 | 0.86 | 1.0 | 0 |
| 0.8 | 0.86 | 1.0 | 0 |
| 0.85 | 0.86 | 1.0 | 0 |
| 0.9 | 0.86 | 1.0 | 0 |
| 0.95 | 0.86 | 1.0 | 0 |

*La confiance donnée par un modèle n'est pas une probabilité calibrée ; les résultats métier (soldes, statuts, relances) sont présentés à part.*

## Calibration (exactitude par tranche de confiance)

- 0.8-0.9 : 1.0 (1)
- 0.9-1.0 : 0.9495 (99)
