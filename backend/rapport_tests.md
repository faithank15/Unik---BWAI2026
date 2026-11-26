# Rapport de tests

Total : **767** tests, 767 réussis, 0 en échec, 0 ignorés. Durée cumulée : 102 s.

## Par famille

| Famille | Réussis | Échecs | Ignorés |
| --- | --- | --- | --- |
| API | 53 | 0 | 0 |
| Base, transactions et journal | 11 | 0 | 0 |
| Calendrier | 8 | 0 | 0 |
| Canevas | 13 | 0 | 0 |
| Concurrence et reprise | 10 | 0 | 0 |
| Contrat d'API | 19 | 0 | 0 |
| Dossiers, revue, journal | 37 | 0 | 0 |
| IA (faux LLM) | 61 | 0 | 0 |
| Import | 19 | 0 | 0 |
| Messages | 31 | 0 | 0 |
| Moteur de relances | 46 | 0 | 0 |
| Paiements et avoirs | 28 | 0 | 0 |
| Reproductibilité | 7 | 0 | 0 |
| Règles pures | 25 | 0 | 0 |
| Réseau bloqué | 2 | 0 | 0 |
| Scénarios S01 à S23 | 20 | 0 | 0 |
| Secrets | 4 | 0 | 0 |
| Sécurité | 296 | 0 | 0 |
| Tableau de bord et journal | 23 | 0 | 0 |
| Équivalence avec la vérité terrain | 9 | 0 | 0 |
| Évaluation IA | 45 | 0 | 0 |

## Échecs

Aucun.

## Tests ignorés (motif écrit obligatoire)

Aucun.

## Couverture (`app/domain`, `app/services`, `app/ia`)

| Module | Couverture |
| --- | --- |
| `app/domain/__init__.py` | 100 % |
| `app/domain/affectation.py` | 100 % |
| `app/domain/calendrier.py` | 100 % |
| `app/domain/canevas.py` | 100 % |
| `app/domain/imports.py` | 100 % |
| `app/domain/priorisation.py` | 100 % |
| `app/domain/relances.py` | 100 % |
| `app/domain/soldes.py` | 100 % |
| `app/ia/__init__.py` | 100 % |
| `app/ia/adaptateur.py` | 100 % |
| `app/ia/dates.py` | 100 % |
| `app/ia/decision.py` | 100 % |
| `app/ia/faux.py` | 97 % |
| `app/ia/gemini.py` | 60 % |
| `app/ia/validation.py` | 98 % |
| `app/services/__init__.py` | 100 % |
| `app/services/calculs.py` | 96 % |
| `app/services/chargeur.py` | 96 % |
| `app/services/dossiers.py` | 95 % |
| `app/services/effets.py` | 100 % |
| `app/services/imports.py` | 93 % |
| `app/services/messages.py` | 94 % |
| `app/services/paiements.py` | 92 % |
| `app/services/parametres.py` | 82 % |
| `app/services/relances.py` | 96 % |
| `app/services/reset.py` | 100 % |
| `app/services/revue.py` | 100 % |
| `app/services/tableau.py` | 100 % |
| **Total** | **95.7 %** |

## Traçabilité règle → test

| Identifiant | Tests |
| --- | --- |
| A02 | test_A02_sans_indication_la_plus_ancienne_d_abord |
| A03 | test_A03_reparti_dans_l_ordre_avec_reliquat_reporte |
| A04 | test_A04_reference_d_un_autre_client_ignoree |
| A05 | test_A05_excedent_non_affecte_jamais_de_solde_negatif, test_A05_surpaiement_reste_non_affecte_jamais_de_solde_negatif |
| A07 | test_A07_entrees_invalides[date_paiement-15/12/2026], test_A07_entrees_invalides[date_paiement-2026-02-30], test_A07_entrees_invalides[mode-BITCOIN] |
| B01 | test_B01_B02_message_piege_reste_une_donnee_encadree_par_des_balises |
| B02 | test_B01_B02_message_piege_reste_une_donnee_encadree_par_des_balises |
| B03 | test_B03_texte_tronque_et_caracteres_de_controle_supprimes |
| C01 | test_C01_non_echue |
| C02 | test_C02_echue_un_jour |
| C05 | test_C05_solde_nul_est_soldee |
| C08 | test_C08_annulee_l_emporte_sur_contestee |
| C09 | test_C09_soldee_l_emporte_sur_contestee |
| C10 | test_C10_contestee_l_emporte_sur_echeancier |
| C11 | test_C11_echeancier_l_emporte_sur_echue_seulement_sans_tranche_manquee |
| CO01 | test_CO01_meme_relance_envoyee_par_plusieurs_threads_sans_erreur, test_S08_CO01_deux_a_huit_traitements_paralleles_une_seule_action |
| CO02 | test_CO02_meme_paiement_enregistre_par_plusieurs_threads |
| CO03 | test_CO03_paiement_et_envoi_simultanes_jamais_d_envoi_apres_le_paiement |
| CO04 | test_CO04_deux_validations_de_la_meme_relance_une_seule_transition |
| CO06 | test_CO06_base_occupee_reessai_borne_jamais_d_echec_silencieux |
| D04 | test_D04_promesse_au_seuil_prudent_avec_date_valide |
| D05 | test_D05_promesse_juste_sous_le_seuil_prudent |
| D06 | test_D06_promesse_sans_date_hors_plafond_passee_ou_sans_facture[kw0-SANS_DATE-True], test_D06_promesse_sans_date_hors_plafond_passee_ou_sans_facture[kw1-AU_DELA_DU_PLAFOND-True], test_D06_promesse_sans_date_hors_plafond_passee_ou_sans_facture[kw2-DATE_PASSEE-True] |
| D07 | test_D07_delai_avec_date_traite_comme_une_promesse_origine_delai |
| D09 | test_D09_copie_demandee_ajoute_une_revue_sans_toucher_aux_relances |
| DU10 | test_dates_standard[dans 2 jours-attendu10] |
| DU11 | test_dates_standard[dans 7 jours-attendu11] |
| DU12 | test_dates_standard[dans 1 jour-attendu12] |
| DU13 | test_dates_standard[lundi prochain-attendu13] |
| DU14 | test_dates_standard[d\xe9but de semaine prochaine-attendu14] |
| DU15 | test_dates_standard[le 20-attendu15] |
| DU16 | test_dates_standard[le 5-attendu16] |
| DU17 | test_dates_standard[le 1-attendu17] |
| DU18 | test_dates_standard[le 2-attendu18] |
| DU19 | test_dates_standard[le 25 sans faute-attendu19] |
| DU20 | test_dates_standard[fin du mois-attendu20] |
| DU21 | test_dates_standard[paiement fin du mois-attendu21] |
| DU22 | test_dates_standard[Je paie le 28-attendu22] |
| DU23 | test_dates_standard[c'est bon pour demain-attendu23] |
| E01 | test_E01_envoi_normal_ecrit_envoi_simule_et_evenement |
| E02 | test_E02_paiement_complet_annule_la_relance_aucun_envoi |
| E03 | test_E03_paiement_partiel_envoi_avec_le_nouveau_solde |
| E04 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[CONTESTATION_OUVERTE-sql0-args0], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[MESSAGE_EN_ATTENTE-sql2-args2], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[PROMESSE_EN_COURS-sql1-args1] |
| E05 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[CONTESTATION_OUVERTE-sql0-args0], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[MESSAGE_EN_ATTENTE-sql2-args2], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[PROMESSE_EN_COURS-sql1-args1] |
| E06 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[CONTESTATION_OUVERTE-sql0-args0], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[MESSAGE_EN_ATTENTE-sql2-args2], test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[PROMESSE_EN_COURS-sql1-args1] |
| E07 | test_E07_jour_non_ouvre_la_relance_reste_planifiee_puis_part_le_lundi |
| E08 | test_E08_gros_montant_non_valide_n_est_jamais_envoye |
| E09 | test_E09_validation_par_un_validateur_puis_envoi_et_trace, test_E09_valider_deux_fois_est_sans_effet |
| E10 | test_E10_rejet_annule_avec_le_motif_du_rejet |
| E11 | test_E11_un_gestionnaire_ne_peut_ni_valider_ni_rejeter |
| H01 | test_H01_injection_sql_dans_les_filtres |
| H02 | test_H02_facture_inexistante_404 |
| H03 | test_H03_corps_mal_forme |
| H06 | test_H06_html_stocke_comme_texte |
| H07 | test_H07_C4_injection_obeie_jamais_de_marquage_paye |
| I01 | test_I01_lot_nominal |
| I03 | test_I03_meme_lot_deux_fois_aucun_doublon |
| I04 | test_I04_fichier_modifie_seule_la_ligne_nouvelle_est_traitee |
| I05 | test_I05_identifiant_existant_avec_donnees_differentes |
| I06 | test_I06_fichier_trop_gros_refuse_sans_effet |
| I07 | test_I07_valeurs_dangereuses_prefixees_d_une_apostrophe[+33], test_I07_valeurs_dangereuses_prefixees_d_une_apostrophe[-2+3], test_I07_valeurs_dangereuses_prefixees_d_une_apostrophe[=1+1] |
| I09 | test_I09_montant_au_mauvais_format_date_invalide_echeance_avant_emission |
| ID03 | test_ID03_envoi_de_la_meme_relance_un_seul_envoi_un_seul_evenement |
| J01 | test_J01_journal_refuse_modification_et_suppression |
| J02 | test_J02_J03_chaque_operation_sensible_ecrit_un_evenement_avec_acteur_et_correlation, test_J02_chaque_evenement_du_catalogue_est_emis |
| J03 | test_J02_J03_chaque_operation_sensible_ecrit_un_evenement_avec_acteur_et_correlation |
| J04 | test_J04_echec_ne_cree_pas_de_session, test_J04_une_operation_refusee_n_ecrit_aucun_evenement_de_succes |
| K01 | test_K01_dimanche_non_ouvre |
| K02 | test_K02_samedi_ouvre |
| K03 | test_K03_jour_ferie_non_ouvre |
| K04 | test_K04_report_au_prochain_jour_ouvre |
| K06 | test_K06_fin_d_annee |
| L01 | test_L01_V1_json_invalide_champ_en_trop_ou_manquant[42], test_L01_V1_json_invalide_champ_en_trop_ou_manquant[[1, 2]], test_L01_V1_json_invalide_champ_en_trop_ou_manquant[brut4] |
| L02 | test_L02_V2_categorie_hors_liste |
| L03 | test_L03_V3_confiance_hors_bornes[-0.1], test_L03_V3_confiance_hors_bornes[0.9], test_L03_V3_confiance_hors_bornes[1.2] |
| L04 | test_L04_V4_date_hors_de_reception_plus_365_jours[2026-02-30], test_L04_V4_date_hors_de_reception_plus_365_jours[2026-12-09], test_L04_V4_date_hors_de_reception_plus_365_jours[20261218] |
| L05 | test_L05_V5_date_pour_une_categorie_sans_date[AUTRE_INCERTAIN], test_L05_V5_date_pour_une_categorie_sans_date[CONTESTATION], test_L05_V5_date_pour_une_categorie_sans_date[DEJA_PAYE] |
| L06 | test_L06_V6_montant_invalide_mis_a_nul_message_en_revue[-5], test_L06_V6_montant_invalide_mis_a_nul_message_en_revue[0], test_L06_V6_montant_invalide_mis_a_nul_message_en_revue[12.5] |
| L07 | test_L07_V7_facture_absente_des_factures_ouvertes |
| L08 | test_L08_V8_justification_tronquee_sans_autre_consequence |
| N01 | test_N01_les_routes_exposees_sont_exactement_celles_de_la_section_13 |
| N02 | test_N02_exemple_detail_de_facture, test_N02_exemple_explication_et_tableau_de_bord, test_N02_exemple_login |
| N03 | test_N03_format_d_erreur_homogene, test_N03_format_d_erreur_homogene[get-/api/factures/FAC-9999-None-404-INTROUVABLE], test_N03_format_d_erreur_homogene[get-/api/factures?limite=0-None-400-VALIDATION] |
| N04 | test_N04_meme_forme_de_liste_partout[/api/avoirs], test_N04_meme_forme_de_liste_partout[/api/clients], test_N04_meme_forme_de_liste_partout[/api/echeances] |
| N05 | test_N05_openapi_json_exporte_identique_a_l_application |
| P01 | test_P01 |
| P02 | test_P02_retard_plafonne |
| P03 | test_P03_montant_plafonne |
| P06 | test_P06_composantes_exactes_sans_arrondi_intermediaire |
| PF01 | test_PF01_liste_priorisee_en_moins_de_300_ms |
| PF02 | test_PF02_planification_d_une_journee_complete_en_moins_de_2_s |
| PF03 | test_PF03_tableau_de_bord_en_moins_de_500_ms |
| R01 | test_R01_resume_de_planification |
| R03 | test_R03_planifier_deux_fois_le_meme_jour_ne_cree_rien |
| R04 | test_R04_R05_un_seul_message_groupe_au_ton_le_plus_grave |
| R05 | test_R04_R05_un_seul_message_groupe_au_ton_le_plus_grave |
| R06 | test_R06_espacement_minimal_deux_jours |
| R07 | test_R07_rattrapage_une_seule_etape_espacee_de_cinq_jours |
| R08 | test_R08_rappel_p_saute_avec_motif |
| R09 | test_R09_aucun_rappel_p_pour_un_accord_accepte |
| R10 | test_R10_pas_de_relance_pour_facture_soldee_ou_annulee |
| R11 | test_R11_R12_seuil_strict_de_validation_humaine, test_R11_au_dessus_du_seuil_en_attente_de_validation |
| R12 | test_R11_R12_seuil_strict_de_validation_humaine |
| RE01 | test_RE01_reset_complet_en_moins_de_10_secondes |
| RE02 | test_RE02_deux_resets_complets_identiques_hors_horodatages |
| RP01 | test_S19_RP01_lot_interrompu_apres_5_puis_repris_sans_doublon |
| RP03 | test_RP03_atomicite_une_erreur_annule_paiement_et_journal, test_RP03_atomicite_une_erreur_pendant_l_envoi_annule_tout |
| S0 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[CONTESTATION_OUVERTE-sql0-args0], test_accord_refus_regles_metier[<lambda>-DATES_INVALIDES0], test_promesse_refus[corps0-422] |
| S01 | test_S01_apres_reset_le_lot_nominal_est_deja_importe, test_S01_contestation_ouverte_suspend, test_S01_import_nominal_rejoue_deux_fois_aucun_doublon |
| S02 | test_S02_lot_defectueux, test_S02_lot_defectueux_apres_le_nominal, test_S02_promesse_suspend_jusqu_a_la_date_plus_deux_jours |
| S03 | test_S03_echeancier_accepte_suspend_sauf_tranche_manquee, test_S03_paiements_partiels |
| S04 | test_S04_message_en_attente_suspend_sauf_demande_de_copie, test_S04_paiement_couvrant_plusieurs_factures |
| S05 | test_S05_paiement_ambigu |
| S06 | test_S06_paiement_rejoue |
| S07 | test_S07_relance_annulee_apres_paiement, test_paiement_event_fichier_s07_style |
| S08 | test_S08_CO01_deux_a_huit_traitements_paralleles_une_seule_action, test_S08_traitements_concurrents_une_seule_action |
| S09 | test_S09_gros_montants_validation_avant_envoi |
| S1 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[PROMESSE_EN_COURS-sql1-args1], test_accord_refus_regles_metier[<lambda>-DATES_INVALIDES1], test_promesse_refus[corps1-400] |
| S10 | test_S10_suspension_puis_reprise_apres_cloture |
| S11 | test_S11_promesse_tenue_apres_paiement, test_S11_promesses |
| S12 | test_S12_apres_acceptation_relance_sur_la_tranche_manquee_seulement, test_S12_relance_sur_la_tranche_manquee_seulement |
| S13 | test_S13_message_regroupe |
| S14 | test_S14_escalade_progressive |
| S15 | test_S15_dimanche_et_jour_ferie |
| S16 | test_S16_rappel_p_saute |
| S17 | test_S17_deja_paye_revue_solde_inchange_aucun_paiement |
| S18 | test_S18_message_incertain_revue_ni_promesse_ni_contestation |
| S19 | test_S19_RP01_lot_interrompu_apres_5_puis_repris_sans_doublon, test_S19_lot_interrompu_puis_repris |
| S2 | test_E04_E05_E06_evenement_entre_planification_et_envoi_annule[MESSAGE_EN_ATTENTE-sql2-args2], test_promesse_refus[corps2-422], test_valider_categorie_refus[corps2-422] |
| S20 | test_S20_client_sans_consentement_ni_canal_valide_en_revue |
| S21 | test_S21_avoir_couvrant |
| S22 | test_S22_escalade_apres_r3 |
| S23 | test_S23_llm_indisponible_messages_a_classer_le_reste_fonctionne |
| S3 | test_N03_format_d_erreur_homogene[post-/api/paiements-corps3-400-VALIDATION], test_promesse_refus[corps3-422], test_valider_categorie_refus[corps3-422] |
| S4 | test_N03_format_d_erreur_homogene[post-/api/avoirs-corps4-422-REGLE_METIER], test_promesse_refus[corps4-404] |
| S5 | test_N03_format_d_erreur_homogene[post-/api/paiements-corps5-201-None], test_promesse_refus[corps5-400] |
| T-0 | test_A07_entrees_invalides[montant-0] |
| T-15 | test_A07_entrees_invalides[date_paiement-15/12/2026] |
| T-20 | test_A07_entrees_invalides[date_paiement-2026-02-30] |
| T0 | test_ordre_de_priorite_des_statuts_par_paires[ANNULEE-SOLDEE-kw_fort0-kw_faible0] |
| T1 | test_ordre_de_priorite_des_statuts_par_paires[SOLDEE-CONTESTEE-kw_fort1-kw_faible1] |
| T2 | test_ordre_de_priorite_des_statuts_par_paires[CONTESTEE-COUVERTE_PAR_ECHEANCIER-kw_fort2-kw_faible2] |
| T3 | test_ordre_de_priorite_des_statuts_par_paires[ECHUE-NON_ECHUE-kw_fort3-kw_faible3] |
| T4 | test_L01_V1_json_invalide_champ_en_trop_ou_manquant[brut4] |
| T5 | test_L01_V1_json_invalide_champ_en_trop_ou_manquant[brut5] |
| TE0 | test_U02_jeton_invalide_donne_401[entete0-GET-/api/accords], test_U02_jeton_invalide_donne_401[entete0-GET-/api/auth/moi], test_U02_jeton_invalide_donne_401[entete0-GET-/api/avoirs] |
| TE1 | test_U02_jeton_invalide_donne_401[entete1-GET-/api/accords], test_U02_jeton_invalide_donne_401[entete1-GET-/api/auth/moi], test_U02_jeton_invalide_donne_401[entete1-GET-/api/avoirs] |
| TE2 | test_U02_jeton_invalide_donne_401[entete2-GET-/api/accords], test_U02_jeton_invalide_donne_401[entete2-GET-/api/auth/moi], test_U02_jeton_invalide_donne_401[entete2-GET-/api/avoirs] |
| TF8 | test_fichier_non_utf8 |
| U01 | test_U01_chaque_route_protegee_refuse_l_absence_de_jeton[GET-/api/accords], test_U01_chaque_route_protegee_refuse_l_absence_de_jeton[GET-/api/auth/moi], test_U01_chaque_route_protegee_refuse_l_absence_de_jeton[GET-/api/avoirs] |
| U02 | test_U02_jeton_expire, test_U02_jeton_invalide, test_U02_jeton_invalide_donne_401[entete0-GET-/api/accords] |
| U03 | test_U03_route_reservee_au_validateur_appelee_par_un_gestionnaire_donne_403[POST-/api/accords/{}/accepter], test_U03_route_reservee_au_validateur_appelee_par_un_gestionnaire_donne_403[POST-/api/accords/{}/refuser], test_U03_route_reservee_au_validateur_appelee_par_un_gestionnaire_donne_403[POST-/api/admin/avancer] |
| U04 | test_U04_connexion_jeton_opaque_et_session |
| U05 | test_U05_mauvais_mot_de_passe_et_identifiant_inconnu_identiques |
| U06 | test_U06_deconnexion_revoque_le_jeton |
| U07 | test_U07_mots_de_passe_haches_scrypt |
| U08 | test_U08_aucun_secret_dans_le_journal |
| V01 | test_V01_avoir_partiel_reduit_le_solde |
| V02 | test_V02_avoir_total_solde_la_facture |
| V03 | test_V03_avoir_superieur_au_solde_refuse |
| V04 | test_V04_avoir_rejoue_un_seul_effet |
| X01 | test_X01_X03_escalade_apres_r3_sans_suite_une_seule_fois |
| X02 | test_X02_paiement_avant_cinq_jours_aucune_escalade |
| X03 | test_X01_X03_escalade_apres_r3_sans_suite_une_seule_fois |
| Y01 | test_Y01_paiement_valide_affecte_et_journalise |
| Y02 | test_Y02_rejeu_meme_corps_200_sans_ecriture |
| Y04 | test_Y04_facture_annulee_refusee |
| Y05 | test_Y05_date_posterieure_a_la_date_de_reference |
| Z01 | test_Z01_api_indisponible_apres_les_reessais |
| Z02 | test_Z02_coupe_circuit_apres_trois_echecs_puis_refermeture |
| Z03 | test_Z03_aucune_transaction_ouverte_pendant_l_appel_au_llm |
| Z04 | test_Z04_reclassification_du_meme_message_aucun_nouvel_appel |
