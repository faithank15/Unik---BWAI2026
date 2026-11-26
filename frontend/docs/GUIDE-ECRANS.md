# Faktu, écran par écran

Faktu sert à une seule personne : celle qui relance les impayés. Par exemple l'agent de recouvrement d'une agence de microcrédit, qui doit savoir chaque matin qui relancer, quand, par quel canal, et qui ne surtout pas relancer (client qui a déjà payé, qui conteste, qui a promis une date). Les clients relancés n'utilisent pas l'application : ils reçoivent seulement les messages.

Ce guide dit ce que montre chaque page, à quoi sert chaque élément, et ce qu'on peut y faire. Deux rôles existent dans l'équipe de recouvrement :

- le **gestionnaire** suit les factures, saisit les paiements et les réponses des clients, et traite les dossiers à revoir ;
- le **validateur** fait tout cela, et décide en plus ce qui engage l'entreprise : relances de gros montant, contestations, échéanciers, promesses à plus de 30 jours, paramètres.

Une action réservée au validateur est marquée **(validateur)**. Le gestionnaire voit alors « Seul un validateur peut… » à la place du bouton.

La barre du bas mène partout : **Tableau de bord**, **À traiter**, **+** (ajouter), **À revoir**, **Compte**. Sur toutes les listes, tirer vers le bas actualise la page.

---

## Connexion

Ouvre une session sur le serveur de l'équipe.

| Élément | À quoi il sert |
|---|---|
| Nom d'utilisateur, Mot de passe | Les identifiants du compte. L'œil affiche ou masque le mot de passe. |
| Se connecter | Ouvre la session. La session reste ouverte au prochain lancement, jusqu'à la déconnexion. |
| Comptes de démonstration | Rappelle les deux comptes : `gestionnaire` et `validateur`. |

---

## Tableau de bord

La situation du jour, et les relances à préparer et envoyer.

| Élément | À quoi il sert |
|---|---|
| Date en haut | La date de référence : tous les calculs (retards, relances) se font à ce jour. |
| Encours à recouvrer | Ce que les clients doivent encore, dont la part en retard, sur combien de factures ouvertes. |
| Barre de couleurs | La répartition des factures par statut : en retard, à échéance, échéancier en cours, contestée, réglée, annulée. |
| Factures à relancer | Le nombre de factures en retard. Ouvre **À traiter**. |
| Dossiers à revoir | Ce qui attend une décision humaine. Ouvre **À revoir**. |
| Relances injustifiées évitées | Les relances qu'une règle simple aurait envoyées à tort (facture contestée, promesse en cours…) et que Faktu n'a pas envoyées. |
| Relances envoyées aujourd'hui | Le nombre de messages partis ce jour. |
| Relances du jour | Les relances du jour par statut : préparées, à valider, envoyées, sautées. |
| **Préparer** | Calcule les relances du jour : quelles factures, quelle étape, quel canal. Rien n'est envoyé. |
| **Envoyer** | Envoie les relances préparées (envoi simulé). Juste avant l'envoi, Faktu vérifie de nouveau chaque facture : un paiement arrivé entre-temps annule la relance. |
| Relances différées | Les clients dont le dernier message est trop récent : plus le montant est élevé, plus Faktu laisse de jours entre deux relances. La prochaine date possible est indiquée. |
| « N relances de gros montant attendent un validateur » | Au-delà de 500 000 FCFA dans un message, la relance attend un validateur. |
| Suivi | Raccourcis vers Toutes les relances, Messages envoyés, Relances suspendues, Journal. |
| Jour suivant **(validateur)** | Fait passer la date de référence au jour suivant, puis prépare et envoie les relances de ce jour. Sert à faire avancer la démonstration. |

---

## À traiter

Les factures à relancer, de la plus urgente à la moins urgente, et la liste des clients.

| Élément | À quoi il sert |
|---|---|
| Factures à relancer / Clients | Bascule entre la priorisation des factures et la liste des clients. |
| Recherche | Filtre par nom de client ou numéro de facture. |
| Ligne de facture | Le score de priorité à gauche (sur 100), le client, le numéro, les jours de retard et le reste à payer. Ouvre la facture. |
| Ligne de client | Le client et ce qu'il doit. Ouvre sa fiche. |

Le score additionne trois choses : l'ancienneté du retard, le montant dû et les retards passés du client. Le détail s'affiche sur la page de la facture.

---

## Facture

Tout sur une facture : où elle en est, pourquoi, et ce qu'on peut faire.

| Élément | À quoi il sert |
|---|---|
| Pastilles en haut | Le statut (en retard depuis N jours, réglée, contestée…) et « Payée en partie » si un paiement a déjà été reçu. |
| Reste à payer, Montant TTC, Déjà payé, Émise le, Délai de paiement | Les chiffres de la facture. |
| Pourquoi ce statut | La règle qui donne le statut, et pourquoi les autres statuts ne s'appliquent pas. |
| Priorité n° X sur Y | Le rang de la facture et le détail du score : retard, montant dû, retards passés. |
| Échéances | Chaque échéance : date, montant dû, payé, reste, et son statut. « Remplacée » si un échéancier l'a remplacée. |
| Ce qui a été payé | Les paiements et avoirs affectés à cette facture. |
| Suivi du dossier | Contestation, promesse et échéancier liés à la facture, avec leur état. |
| Relances | Les relances de cette facture : étape, date, statut. Ouvre le détail de la relance. |
| Réponses du client | Les messages du client liés à cette facture, avec leur classement. |

**Actions**

| Action | Ce qu'elle fait |
|---|---|
| Enregistrer un paiement | Saisit un paiement reçu pour cette facture (voir **Ajouter**). |
| Relancer ce client maintenant | La même relance immédiate, limitée à cette facture. |
| Enregistrer un avoir | Réduit ce que le client doit : montant, date, motif. S'il couvre le solde, les relances s'arrêtent. |
| Ouvrir une contestation | Note ce que le client conteste. Les relances de la facture s'arrêtent jusqu'à la clôture. |
| Clore la contestation **(validateur)** | Décide : le client a raison, la facture est due, ou abandon. Commentaire obligatoire. Si la facture reste due, les relances reprennent. |
| Noter une promesse de paiement | Date promise et montant (facultatif). Les relances attendent la date promise, plus 2 jours. Au-delà de 30 jours : validateur seulement. |
| Annuler (sur une promesse en cours, en rouge) | Annule la promesse : les relances reprennent. |
| Proposer un échéancier | Répartit le montant en tranches (au moins 2, dates croissantes, somme égale au montant TTC). |
| Accepter ou refuser **(validateur)** | Accepté, l'échéancier remplace les échéances de la facture. |
| Ouvrir le client | Ouvre la fiche du client. |
| Voir le journal de cette facture | Toutes les actions passées sur cette facture. |

---

## Fiche client

Un client, ce qu'il doit, comment le joindre.

| Élément | À quoi il sert |
|---|---|
| Reste à payer | Le total que le client doit, toutes factures confondues. |
| Contact | Interlocuteur, canal préféré, téléphone WhatsApp, e-mail, et s'il accepte d'être relancé. |
| Relancer maintenant | Envoie une relance tout de suite, sans attendre le calendrier : choix du canal et raison facultative. Faktu revérifie d'abord le solde, les contestations, les promesses et l'accord du client ; au-delà de 500 000 FCFA, un validateur décide. Le message envoyé s'ouvre ensuite. |
| Modifier le contact | Change l'interlocuteur, les canaux autorisés, le canal préféré, l'accord de relance, les jours où ne pas le relancer et le moment préféré. La fiche indique la date de la dernière modification faite dans Faktu. |
| Factures | Les factures ouvertes, puis « Réglées ou annulées ». Chacune ouvre sa page. |
| Relances récentes | Les derniers messages envoyés à ce client. |
| Réponses du client | Ses messages et leur classement. |
| Paiements | Les paiements reçus, et la part restant à affecter. |
| Voir le journal de ce client | Toutes les actions passées sur ce client. |

---

## Ajouter (bouton +)

Trois saisies à la main.

**Enregistrer un paiement**

| Champ | À quoi il sert |
|---|---|
| Client | Le client qui a payé. Sans client, le paiement part dans **À revoir** pour être affecté. |
| Pour la facture | La facture indiquée par le client. Sans facture, le paiement va aux échéances les plus anciennes. |
| Montant (FCFA) | S'écrit avec les espaces des milliers pendant la saisie. |
| Mode de paiement | Mobile money, virement, espèces ou chèque. |
| Date du paiement | Aujourd'hui ou avant. |
| Référence | Le numéro de la transaction. Enregistrer deux fois la même référence ne compte pas le paiement deux fois. |

**Ajouter la réponse d'un client**

| Champ | À quoi il sert |
|---|---|
| Client | Qui a répondu. |
| Canal de réception | WhatsApp ou e-mail. |
| Texte du message | Le message tel que reçu. |
| Facture citée | La facture dont parle le client, s'il en cite une. |

Après l'ajout, l'IA classe la réponse. Si elle n'est pas sûre, ou si le cas est sensible, la réponse arrive dans **À revoir**.

**Importer un portefeuille**

Pour qu'une agence ou un opérateur mette toute sa base dans Faktu sans passer par le serveur : il exporte ses données en CSV (logiciel de gestion, tableur) et les importe depuis le téléphone.

| Fichier | Contenu |
|---|---|
| clients.csv (obligatoire) | Les clients : identifiant, nom, activité, ville, e-mail, WhatsApp. |
| factures.csv (obligatoire) | Ce que chaque client doit : numéro, date, montant, conditions de paiement. |
| echeances.csv (obligatoire) | Les dates de paiement de chaque facture et le montant dû à chacune. |
| preferences_contact.csv (facultatif) | Canal préféré, canaux autorisés, accord pour être relancé, interlocuteur. |
| accords_echeancier.csv (facultatif) | Les échéanciers déjà accordés. |

L'écran rappelle ces fichiers, puis **Choisir les fichiers** ouvre les fichiers du téléphone : on les sélectionne ensemble. Le rapport donne le nombre de lignes acceptées et, pour chaque ligne refusée, le fichier, le numéro de ligne et le motif (numéro WhatsApp mal formé, échéances qui ne font pas le montant de la facture…). Les mêmes fichiers importés deux fois n'ajoutent rien en double.

---

## À revoir

Tout ce que le système ne décide pas seul.

| Élément | À quoi il sert |
|---|---|
| Réponses à classer | Les messages que l'IA n'a pas pu classer. Les relances du client sont suspendues en attendant. |
| Classer cette réponse | Choisit ce que dit le message : dit avoir déjà payé, promesse, contestation, demande d'échéancier, de délai ou de copie, autre. Selon le choix, une date, un montant et une facture sont demandés. |
| Demander à l'IA de la classer à nouveau | Relance le classement automatique. |
| Filtres | Tous les dossiers, ou un seul type. |
| Carte de dossier | Le type, le client, la raison, puis les actions qui conviennent. |

**Actions selon le type de dossier**

| Dossier | Actions |
|---|---|
| Gros montant **(validateur)** | Valider et envoyer, ou Ne pas envoyer (en rouge). |
| Contestation **(validateur)** | Clore la contestation, ou Classer sans suite. |
| Paiement à affecter | Affecter le paiement échéance par échéance, ou Classer sans suite. |
| Contact invalide, Sans accord de relance | Modifier le contact, ou Marquer comme corrigé. |
| Sans suite après la 3e relance **(validateur)** | Noter la décision : appel au client, mise en demeure, abandon ou sans suite, avec un commentaire. |
| Réponse incertaine, promesse à valider, demande d'échéancier, de copie | Classer cette réponse, ou Classer sans suite. |

---

## Relances

**Toutes les relances** : trois onglets, À venir, Envoyées, Arrêtées. Chaque ligne donne le client, l'étape, la date et le statut, et ouvre le détail.

**Détail d'une relance**

| Élément | À quoi il sert |
|---|---|
| Canal, Prévue le, Envoyée le, Motif, Total du message | Les informations de la relance. Le motif explique une relance sautée, suspendue ou reportée. |
| Lignes | Les factures regroupées dans ce message. |
| Texte envoyé au client | Le message exact. |
| Valider et envoyer / Ne pas envoyer **(validateur)** | Pour une relance de gros montant. |
| Historique | Chaque changement de statut. |

**Messages envoyés** : la boîte d'envoi simulée. Le texte exact de chaque message, avec le destinataire et la date. Rien n'est réellement envoyé.

**Relances suspendues** : en haut, la comparaison avec une relance de toutes les factures échues (combien auraient été envoyées, combien à tort, combien Faktu en a évité, combien de messages le regroupement a économisés). Dessous, chaque échéance suspendue et la raison : contestation, promesse, échéancier, réponse à traiter.

---

## Journal

Chaque action, qui l'a faite et pourquoi. Les entrées ne peuvent être ni modifiées ni supprimées.

| Élément | À quoi il sert |
|---|---|
| Filtres | Tous, Système, IA, Utilisateur. |
| Entrée | Ce qui s'est passé, qui (système, IA ou personne), quand, sur quel objet, ce qui a changé, et la date de référence du moment. |

Le journal s'ouvre aussi filtré sur une facture ou un client.

---

## Compte

| Élément | À quoi il sert |
|---|---|
| Carte du compte | Le nom, le rôle et ce que ce rôle permet. |
| Thème | Clair, sombre, ou celui du téléphone. |
| Paramètres métier | Les règles du recouvrement : jours entre les relances, seuil des gros montants, plafond des promesses… Le validateur les modifie ; chaque changement est inscrit au journal. |
| Courriels rédigés par l'IA | Les formulations écrites par l'IA (introduction et conclusion), par cas de client et par ton. Les montants et factures sont insérés par Faktu. Chaque formulation peut être relue et marquée « Relue ». |
| Journal | Le journal complet. |
| Réinitialiser les données **(validateur)** | Recharge le jeu de données de démonstration au 15 décembre 2026. Tout ce qui a été fait depuis est effacé. |
| Bon à savoir | Ce que la démonstration ne fait pas : envois et paiements simulés, IA limitée au classement des réponses, messages en français, pénalités non ajoutées au solde. |
| Se déconnecter (en rouge) | Ferme la session sur ce téléphone. |
