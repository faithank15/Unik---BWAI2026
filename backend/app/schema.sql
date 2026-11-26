-- Schéma SQLite du back-end de recouvrement BWAI 2026 : 23 tables, 3 vues, 2 déclencheurs.
-- Source : spécification du back-end, section 5. Aucun solde ni statut de facture n'est
-- stocké : tout se calcule à partir des vues ci-dessous.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Partie 1 : référentiels et portefeuille ---------------------------------------------
CREATE TABLE sequences (
  nom    TEXT PRIMARY KEY,
  valeur INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE parametres (
  cle         TEXT PRIMARY KEY,
  valeur      TEXT NOT NULL,
  type        TEXT NOT NULL CHECK (type IN ('ENTIER','DECIMAL','BOOLEEN','TEXTE','DATE')),
  description TEXT
);

CREATE TABLE jours_feries (
  date    TEXT PRIMARY KEY,
  libelle TEXT NOT NULL
);

CREATE TABLE utilisateurs (
  id               TEXT PRIMARY KEY,
  nom_utilisateur  TEXT NOT NULL UNIQUE,
  nom_affiche      TEXT NOT NULL,
  role             TEXT NOT NULL CHECK (role IN ('GESTIONNAIRE','VALIDATEUR')),
  mot_de_passe_hash TEXT NOT NULL,
  actif            INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0,1))
);

CREATE TABLE sessions (
  token_hash     TEXT PRIMARY KEY,
  utilisateur_id TEXT NOT NULL REFERENCES utilisateurs(id),
  cree_le        TEXT NOT NULL,
  expire_le      TEXT NOT NULL,
  revoquee       INTEGER NOT NULL DEFAULT 0 CHECK (revoquee IN (0,1))
);

CREATE TABLE clients (
  id             TEXT PRIMARY KEY,
  raison_sociale TEXT NOT NULL UNIQUE,
  secteur        TEXT,
  ville          TEXT,
  email          TEXT,
  whatsapp       TEXT,
  actif          INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0,1))
);

CREATE TABLE preferences_contact (
  client_id            TEXT PRIMARY KEY REFERENCES clients(id),
  canal_prefere        TEXT NOT NULL CHECK (canal_prefere IN ('WHATSAPP','EMAIL')),
  canaux_autorises     TEXT NOT NULL,            -- 'WHATSAPP;EMAIL'
  consentement_relance INTEGER NOT NULL CHECK (consentement_relance IN (0,1)),
  interlocuteur        TEXT,
  jours_a_eviter       TEXT NOT NULL DEFAULT '',     -- 'MARDI;VENDREDI' (lundi à samedi)
  plage_horaire        TEXT NOT NULL DEFAULT 'AUCUNE'
                       CHECK (plage_horaire IN ('MATIN','APRES_MIDI','AUCUNE')),
  provenance           TEXT NOT NULL DEFAULT '{}'    -- JSON : champ -> {source, date}
);

CREATE TABLE imports (
  id          TEXT PRIMARY KEY,
  fichiers    TEXT NOT NULL,                     -- noms des fichiers, JSON
  empreinte   TEXT NOT NULL UNIQUE,              -- SHA-256
  date_import TEXT NOT NULL,
  nb_lignes   INTEGER NOT NULL,
  nb_rejets   INTEGER NOT NULL,
  rapport     TEXT NOT NULL                      -- JSON : liste des rejets
);

CREATE TABLE factures (
  id                   TEXT PRIMARY KEY,
  client_id            TEXT NOT NULL REFERENCES clients(id),
  numero               TEXT NOT NULL,
  date_emission        TEXT NOT NULL,
  montant_ttc          INTEGER NOT NULL CHECK (montant_ttc > 0),
  conditions_paiement  TEXT NOT NULL CHECK (conditions_paiement IN
    ('COMPTANT','15_JOURS','30_JOURS','45_JOURS','60_JOURS','TRANCHES')),
  taux_penalite_retard REAL,
  ref_facture_normalisee TEXT,
  statut_document      TEXT NOT NULL DEFAULT 'VALIDEE'
    CHECK (statut_document IN ('VALIDEE','ANNULEE')),
  import_id            TEXT REFERENCES imports(id),
  UNIQUE (client_id, numero)
);

CREATE TABLE accords_echeancier (
  id          TEXT PRIMARY KEY,
  facture_id  TEXT NOT NULL REFERENCES factures(id),
  date_accord TEXT NOT NULL,
  statut      TEXT NOT NULL CHECK (statut IN ('PROPOSE','ACCEPTE','RESPECTE','ROMPU')),
  nb_tranches INTEGER NOT NULL CHECK (nb_tranches >= 2),
  accepte_par TEXT REFERENCES utilisateurs(id)
);

CREATE TABLE echeances (
  id            TEXT PRIMARY KEY,
  facture_id    TEXT NOT NULL REFERENCES factures(id),
  rang          INTEGER NOT NULL CHECK (rang >= 1),
  date_echeance TEXT NOT NULL,
  montant_du    INTEGER NOT NULL CHECK (montant_du > 0),
  etat          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (etat IN ('ACTIVE','REMPLACEE')),
  accord_id     TEXT REFERENCES accords_echeancier(id)
);

CREATE TABLE avoirs (
  id         TEXT PRIMARY KEY,
  facture_id TEXT NOT NULL REFERENCES factures(id),
  date_avoir TEXT NOT NULL,
  montant    INTEGER NOT NULL CHECK (montant > 0),
  motif      TEXT NOT NULL
);

CREATE TABLE paiements (
  id                TEXT PRIMARY KEY,
  client_id         TEXT REFERENCES clients(id),   -- vide : paiement non identifiable
  date_paiement     TEXT NOT NULL,
  montant           INTEGER NOT NULL CHECK (montant > 0),
  mode              TEXT NOT NULL CHECK (mode IN
    ('MOBILE_MONEY','VIREMENT','ESPECES','CHEQUE')),
  reference_externe TEXT NOT NULL,
  source            TEXT NOT NULL DEFAULT 'SIMULE' CHECK (source = 'SIMULE'),
  statut            TEXT NOT NULL DEFAULT 'RECU' CHECK (statut = 'RECU'),
  UNIQUE (mode, reference_externe)
);

CREATE TABLE affectations (
  id               TEXT PRIMARY KEY,
  echeance_id      TEXT NOT NULL REFERENCES echeances(id),
  paiement_id      TEXT REFERENCES paiements(id),
  avoir_id         TEXT REFERENCES avoirs(id),
  montant_affecte  INTEGER NOT NULL CHECK (montant_affecte > 0),
  mode             TEXT NOT NULL CHECK (mode IN ('INDIQUEE','AUTO_ANCIENNETE')),
  date_affectation TEXT NOT NULL,
  CHECK ((paiement_id IS NOT NULL) + (avoir_id IS NOT NULL) = 1)
);

CREATE INDEX idx_factures_client    ON factures(client_id);
CREATE INDEX idx_echeances_facture  ON echeances(facture_id);
CREATE INDEX idx_echeances_date     ON echeances(date_echeance);
CREATE INDEX idx_affectations_ech   ON affectations(echeance_id);
CREATE INDEX idx_paiements_client   ON paiements(client_id);

-- Partie 2 : dossiers, relances, messages, revue et journal -----------------------------
CREATE TABLE messages_entrants (
  id                   TEXT PRIMARY KEY,
  client_id            TEXT NOT NULL REFERENCES clients(id),
  canal                TEXT NOT NULL CHECK (canal IN ('WHATSAPP','EMAIL')),
  date_reception       TEXT NOT NULL,
  contenu              TEXT NOT NULL,
  reference_externe    TEXT UNIQUE,
  facture_citee_id     TEXT REFERENCES factures(id),
  statut_traitement    TEXT NOT NULL DEFAULT 'A_CLASSER'
    CHECK (statut_traitement IN ('A_CLASSER','CLASSE','EN_REVUE','TRAITE')),
  categorie_ia         TEXT CHECK (categorie_ia IN ('DEJA_PAYE','PROMESSE_PAIEMENT',
    'CONTESTATION','DEMANDE_ECHEANCIER','DEMANDE_DELAI','DEMANDE_COPIE_FACTURE',
    'AUTRE_INCERTAIN')),
  confiance            REAL,
  copie_demandee       INTEGER CHECK (copie_demandee IN (0,1)),
  date_promise_extraite TEXT,
  montant_promis       INTEGER,
  decision_ia          TEXT CHECK (decision_ia IN ('AUTO','REVUE')),
  motif_revue          TEXT,
  justification        TEXT,
  modele_version       TEXT,
  categorie_validee    TEXT CHECK (categorie_validee IN ('DEJA_PAYE','PROMESSE_PAIEMENT',
    'CONTESTATION','DEMANDE_ECHEANCIER','DEMANDE_DELAI','DEMANDE_COPIE_FACTURE',
    'AUTRE_INCERTAIN')),
  valide_par           TEXT REFERENCES utilisateurs(id),
  classe_le            TEXT
);

CREATE TABLE contestations (
  id                TEXT PRIMARY KEY,
  facture_id        TEXT NOT NULL REFERENCES factures(id),
  echeance_id       TEXT REFERENCES echeances(id),
  motif             TEXT NOT NULL,
  message_source_id TEXT REFERENCES messages_entrants(id),
  date_ouverture    TEXT NOT NULL,
  statut            TEXT NOT NULL CHECK (statut IN ('OUVERTE','CLOTUREE')),
  date_cloture      TEXT,
  resolution        TEXT
);

CREATE TABLE promesses_paiement (
  id                TEXT PRIMARY KEY,
  client_id         TEXT NOT NULL REFERENCES clients(id),
  facture_id        TEXT NOT NULL REFERENCES factures(id),
  date_promise      TEXT NOT NULL,
  montant_promis    INTEGER,
  message_source_id TEXT REFERENCES messages_entrants(id),
  origine           TEXT NOT NULL DEFAULT 'PROMESSE'
    CHECK (origine IN ('PROMESSE','DELAI','MANUELLE')),
  statut            TEXT NOT NULL CHECK (statut IN ('EN_COURS','TENUE','NON_TENUE','ANNULEE'))
);

CREATE TABLE traitements_lot (
  id             TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK (type IN ('PLANIFICATION','ENVOI')),
  date_reference TEXT NOT NULL,
  statut         TEXT NOT NULL CHECK (statut IN ('EN_COURS','TERMINE','INTERROMPU')),
  debut          TEXT NOT NULL,
  fin            TEXT,
  nb_total       INTEGER NOT NULL DEFAULT 0,
  nb_traites     INTEGER NOT NULL DEFAULT 0,
  details        TEXT
);

CREATE TABLE relances (
  id              TEXT PRIMARY KEY,
  client_id       TEXT NOT NULL REFERENCES clients(id),
  canal           TEXT NOT NULL CHECK (canal IN ('WHATSAPP','EMAIL')),
  etape           TEXT NOT NULL CHECK (etape IN ('P','R1','R2','R3','GROUPE')),
  date_prevue     TEXT NOT NULL,
  date_envoi      TEXT,
  statut          TEXT NOT NULL CHECK (statut IN ('PLANIFIEE','EN_ATTENTE_VALIDATION',
                    'ENVOYEE_SIM','ANNULEE','SAUTEE','ABSORBEE')),
  motif           TEXT,
  contenu         TEXT,
  valide_par      TEXT REFERENCES utilisateurs(id),
  cle_idempotence TEXT NOT NULL UNIQUE,
  traitement_id   TEXT REFERENCES traitements_lot(id),
  origine         TEXT NOT NULL DEFAULT 'AUTOMATIQUE'
                  CHECK (origine IN ('AUTOMATIQUE','MANUELLE')),
  demandee_par    TEXT REFERENCES utilisateurs(id)   -- relance manuelle : le gestionnaire
);

-- Rédactions de courriels générées par le LLM, réutilisées pour tous les clients concernés
-- (cas, étape, canal, version de consigne). Un humain peut les relire avant le gel.
CREATE TABLE redactions (
  cle            TEXT PRIMARY KEY,
  cas            TEXT NOT NULL,
  ton            TEXT NOT NULL,
  canal          TEXT NOT NULL,
  nb_factures    TEXT NOT NULL CHECK (nb_factures IN ('UNE','PLUSIEURS')),
  version        TEXT NOT NULL,
  modele_version TEXT NOT NULL,
  objet          TEXT NOT NULL,
  introduction   TEXT NOT NULL,
  conclusion     TEXT NOT NULL,
  ton_applique   TEXT NOT NULL,
  statut         TEXT NOT NULL DEFAULT 'A_RELIRE' CHECK (statut IN ('A_RELIRE','RELUE')),
  cree_le        TEXT NOT NULL
);

CREATE TABLE relance_lignes (
  relance_id                 TEXT NOT NULL REFERENCES relances(id),
  echeance_id                TEXT NOT NULL REFERENCES echeances(id),
  etape_echeance             TEXT NOT NULL CHECK (etape_echeance IN ('P','R1','R2','R3')),
  solde_au_moment_de_l_envoi INTEGER,
  PRIMARY KEY (relance_id, echeance_id)
);

CREATE TABLE envois_simules (
  id          TEXT PRIMARY KEY,
  relance_id  TEXT NOT NULL UNIQUE REFERENCES relances(id),
  canal       TEXT NOT NULL,
  destinataire TEXT NOT NULL,
  objet       TEXT,
  contenu     TEXT NOT NULL,
  horodatage  TEXT NOT NULL,
  plage_horaire TEXT                                 -- préférence du client au moment de l'envoi
);

CREATE TABLE file_revue (
  id                      TEXT PRIMARY KEY,
  type                    TEXT NOT NULL CHECK (type IN ('GROS_MONTANT','LITIGE','INCERTAIN',
    'ESCALADE','PAIEMENT_AMBIGU','CANAL_INVALIDE','CONSENTEMENT_ABSENT','VERIF_PAIEMENT',
    'PROMESSE_A_VALIDER','DEMANDE_ECHEANCIER','DEMANDE_COPIE')),
  objet_type              TEXT NOT NULL CHECK (objet_type IN ('RELANCE','MESSAGE','PAIEMENT',
    'ECHEANCE','FACTURE','CLIENT')),
  objet_id                TEXT NOT NULL,
  client_id               TEXT REFERENCES clients(id),
  priorite                INTEGER NOT NULL DEFAULT 0,
  statut                  TEXT NOT NULL DEFAULT 'OUVERTE' CHECK (statut IN ('OUVERTE','RESOLUE')),
  motif                   TEXT,
  decision                TEXT,
  commentaire             TEXT,
  decideur                TEXT REFERENCES utilisateurs(id),
  date_reference_creation TEXT NOT NULL,
  cree_le                 TEXT NOT NULL,
  resolu_le               TEXT,
  UNIQUE (type, objet_type, objet_id)
);

CREATE TABLE journal (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  horodatage     TEXT NOT NULL,
  date_reference TEXT NOT NULL,
  acteur_type    TEXT NOT NULL CHECK (acteur_type IN ('SYSTEME','IA','UTILISATEUR')),
  acteur_id      TEXT,
  type_evenement TEXT NOT NULL,
  objet_type     TEXT,
  objet_id       TEXT,
  avant          TEXT,
  apres          TEXT,
  details        TEXT,
  correlation_id TEXT
);

CREATE INDEX idx_journal_objet     ON journal(objet_type, objet_id);
CREATE INDEX idx_journal_corr      ON journal(correlation_id);
CREATE INDEX idx_relances_client   ON relances(client_id, canal);
CREATE INDEX idx_messages_client   ON messages_entrants(client_id, statut_traitement);

-- Partie 3 : vues de calcul et protection du journal --------------------------------------
CREATE VIEW v_affecte_echeance AS
SELECT echeance_id, SUM(montant_affecte) AS affecte
FROM affectations
GROUP BY echeance_id;

CREATE VIEW v_echeances_calc AS
SELECT e.id AS echeance_id, e.facture_id, e.rang, e.date_echeance, e.montant_du, e.etat,
       e.accord_id,
       COALESCE(a.affecte, 0) AS affecte,
       e.montant_du - COALESCE(a.affecte, 0) AS solde,
       CASE WHEN e.etat = 'ACTIVE'
             AND e.montant_du - COALESCE(a.affecte, 0) > 0
             AND e.date_echeance < (SELECT valeur FROM parametres WHERE cle = 'date_reference')
            THEN CAST(julianday((SELECT valeur FROM parametres WHERE cle = 'date_reference'))
                      - julianday(e.date_echeance) AS INTEGER)
            ELSE 0 END AS retard_jours
FROM echeances e
LEFT JOIN v_affecte_echeance a ON a.echeance_id = e.id;

CREATE VIEW v_factures_solde AS
SELECT f.id AS facture_id, f.client_id, f.montant_ttc, f.statut_document,
       COALESCE(SUM(CASE WHEN c.etat = 'ACTIVE' THEN c.solde END), 0)   AS solde,
       COALESCE(SUM(CASE WHEN c.etat = 'ACTIVE' THEN c.affecte END), 0) AS affecte,
       COALESCE(MAX(c.retard_jours), 0)                                  AS retard_max
FROM factures f
LEFT JOIN v_echeances_calc c ON c.facture_id = f.id
GROUP BY f.id;

CREATE TRIGGER journal_pas_de_modification BEFORE UPDATE ON journal
BEGIN SELECT RAISE(ABORT, 'Le journal est en ajout seulement'); END;

CREATE TRIGGER journal_pas_de_suppression BEFORE DELETE ON journal
BEGIN SELECT RAISE(ABORT, 'Le journal est en ajout seulement'); END;
