"""Matrice des routes et de leur rôle minimal (spécification, sections 12 et 13).

Source de vérité des tests de sécurité : chaque route de l'OpenAPI doit y figurer, et inversement.
PUBLIC : sans jeton ; AUTH : GESTIONNAIRE ou VALIDATEUR ; VALIDATEUR : rôle minimal VALIDATEUR ;
SELON : le rôle dépend du type ou des valeurs (vérifié par des tests dédiés).
"""
PUBLIC, AUTH, VALIDATEUR, SELON = "PUBLIC", "AUTH", "VALIDATEUR", "SELON"

MATRICE: dict[tuple[str, str], str] = {
    # Santé, contexte et paramètres
    ("GET", "/api/sante"): PUBLIC,
    ("GET", "/api/contexte"): AUTH,
    ("POST", "/api/auth/login"): PUBLIC,
    ("POST", "/api/auth/logout"): AUTH,
    ("GET", "/api/auth/moi"): AUTH,
    ("GET", "/api/parametres"): AUTH,
    ("PUT", "/api/parametres/{}"): VALIDATEUR,
    # Portefeuille
    ("GET", "/api/clients"): AUTH,
    ("GET", "/api/clients/{}"): AUTH,
    ("PUT", "/api/clients/{}/preferences"): AUTH,
    ("GET", "/api/factures"): AUTH,
    ("GET", "/api/factures/{}"): AUTH,
    ("GET", "/api/factures/{}/explication"): AUTH,
    ("GET", "/api/echeances"): AUTH,
    ("GET", "/api/priorisation"): AUTH,
    # Imports, paiements et avoirs
    ("POST", "/api/imports"): AUTH,
    ("GET", "/api/imports"): AUTH,
    ("GET", "/api/imports/{}"): AUTH,
    ("POST", "/api/paiements"): AUTH,
    ("POST", "/api/paiements/import"): AUTH,
    ("GET", "/api/paiements"): AUTH,
    ("GET", "/api/paiements/{}"): AUTH,
    ("POST", "/api/paiements/{}/affecter"): AUTH,
    ("POST", "/api/avoirs"): AUTH,
    ("POST", "/api/avoirs/import"): AUTH,
    ("GET", "/api/avoirs"): AUTH,
    # Relances et canaux simulés
    ("POST", "/api/relances/planifier"): AUTH,
    ("POST", "/api/relances/envoyer"): AUTH,
    ("POST", "/api/relances/manuelle"): AUTH,
    ("GET", "/api/redactions"): AUTH,
    ("POST", "/api/redactions/relue"): AUTH,
    ("GET", "/api/relances"): AUTH,
    ("GET", "/api/relances/suspensions"): AUTH,
    ("GET", "/api/relances/{}"): AUTH,
    ("POST", "/api/relances/{}/valider"): VALIDATEUR,
    ("POST", "/api/relances/{}/rejeter"): VALIDATEUR,
    ("GET", "/api/canaux/envois"): AUTH,
    # Messages, dossiers et revue
    ("POST", "/api/messages"): AUTH,
    ("GET", "/api/messages"): AUTH,
    ("GET", "/api/messages/{}"): AUTH,
    ("POST", "/api/messages/{}/classer"): AUTH,
    ("POST", "/api/messages/{}/valider-categorie"): SELON,
    ("GET", "/api/contestations"): AUTH,
    ("POST", "/api/contestations"): AUTH,
    ("POST", "/api/contestations/{}/cloturer"): VALIDATEUR,
    ("GET", "/api/promesses"): AUTH,
    ("POST", "/api/promesses"): SELON,
    ("POST", "/api/promesses/{}/annuler"): AUTH,
    ("GET", "/api/accords"): AUTH,
    ("POST", "/api/accords"): AUTH,
    ("POST", "/api/accords/{}/accepter"): VALIDATEUR,
    ("POST", "/api/accords/{}/refuser"): VALIDATEUR,
    ("GET", "/api/revue"): AUTH,
    ("GET", "/api/revue/{}"): AUTH,
    ("POST", "/api/revue/{}/resoudre"): SELON,
    ("GET", "/api/journal"): AUTH,
    # Tableau de bord et démonstration
    ("GET", "/api/tableau-de-bord"): AUTH,
    ("GET", "/api/tableau-de-bord/balance-agee"): AUTH,
    ("GET", "/api/evaluation/comparaison-reference"): AUTH,
    ("POST", "/api/admin/reset"): VALIDATEUR,
    ("POST", "/api/admin/date-reference"): VALIDATEUR,
    ("POST", "/api/admin/avancer"): VALIDATEUR,
}
