# Faktu

L'interface mobile (Flutter) de **Faktu**, le prototype de recouvrement des factures impayées du BWAI 2026 (cas 1). Le back-end Python porte toutes les règles : l'application affiche ce qu'il calcule et lui envoie les décisions des personnes.

La direction artistique est celle de Discover. Les règles à suivre sont dans `D:\regles-unk` (à copier dans `docs/` du dépôt) ; le cahier des charges y est aussi.

## Lancer

L'application parle au back-end du dépôt `Unik---BWAI2026` (FastAPI). Voir [docs/ALIGNEMENT-BACKEND.md](docs/ALIGNEMENT-BACKEND.md) : ce qui est branché, ce qui a été retiré, les questions au back-end, et les commandes pour lancer les deux ensemble.

```bash
adb reverse tcp:8000 tcp:8000      # téléphone en USB, back-end lancé sur le PC
flutter run                        # adresse par défaut : http://127.0.0.1:8000
```

## Organisation

| Dossier | Contenu |
|---|---|
| `lib/donnees/` | Les objets du back-end (`modeles.dart`), toutes les routes et l'état partagé (`donnees.dart`), le thème choisi (`affichage.dart`). |
| `lib/outils/` | Le seul client d'API (`api.dart`), les montants et dates (`format.dart`), les codes en mots (`libelles.dart`), les textes (`langue.dart`). |
| `lib/ecrans/` | Tableau de bord, À traiter, client, facture et ses actions, À revoir, relances et boîte d'envoi, journal, compte et paramètres, ajouter. |
| `lib/widgets/` | Les composants de Discover (verre, feuilles, champs, bannières, barre d'onglets), ceux de Faktu (`faktu.dart`) et des formulaires (`formulaires.dart`). |
| `lib/theme/` | Les jetons, le thème et le défilement de Discover. |

## Vérifier

```bash
flutter analyze
flutter test
dart format -l 160 <fichiers modifiés>
```
