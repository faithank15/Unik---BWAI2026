"""Messages entrants et intégration de l'IA (spécification, section 9).

Le back-end reçoit le message, appelle le classifieur EN DEHORS de toute transaction, puis écrit
le résultat et applique l'action dans une transaction. L'IA classe ; le code décide ; la
personne tranche. Indisponibilité du LLM : le message reste « à classer », le reste du système
continue, et la classification peut se faire à la main (mode dégradé).
"""
import sqlite3
from datetime import date
from decimal import Decimal

from app import clock
from app.db import prochain_id, transaction
from app.domain.calendrier import nom_jour
from app.domain.imports import lire_date
from app.errors import AccesRefuse, Introuvable, RegleMetier, Validation
from app.ia import validation as val
from app.ia.adaptateur import Adaptateur, Indisponible, nettoyer_texte
from app.ia.decision import Decision, ParametresDecision, decider
from app.journal import IA, Acteur, journaliser
from app.parametres import lire_booleen, lire_decimal, lire_entier
from app.services import dossiers
from app.services import relances as svc_relances
from app.services.revue import ouvrir_revue

CANAUX = ("WHATSAPP", "EMAIL")
LONGUEUR_MAX_CONTENU = 5000


# ---- réception --------------------------------------------------------------------------
def recevoir_message(conn: sqlite3.Connection, client_id: str, canal: str, contenu: str,
                     facture_citee: str | None, reference_externe: str | None,
                     acteur: Acteur) -> tuple[dict, bool]:
    """Simule l'arrivée d'un message. Créé au statut A_CLASSER ; les relances concernées sont
    aussitôt suspendues (annulation immédiate). `reference_externe` rend l'appel idempotent.
    Retourne (message, créé)."""
    if canal not in CANAUX:
        raise Validation("canal doit valoir WHATSAPP ou EMAIL.")
    if not contenu.strip() or len(contenu) > LONGUEUR_MAX_CONTENU:
        raise Validation("Le contenu est obligatoire (5 000 caractères au plus).")
    with transaction(conn):
        if reference_externe:
            ex = conn.execute("SELECT * FROM messages_entrants WHERE reference_externe = ?",
                              (reference_externe,)).fetchone()
            if ex:
                return dict(ex), False
        if conn.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone() is None:
            raise Introuvable(f"Client {client_id} introuvable.")
        facture_id = None
        if facture_citee:
            f = conn.execute("SELECT id FROM factures WHERE client_id = ? AND numero = ?",
                             (client_id, facture_citee)).fetchone()
            facture_id = f[0] if f else None            # sinon ignorée
        mid = prochain_id(conn, "MSG")
        reception = f"{clock.date_reference(conn).isoformat()}T{clock.maintenant()[11:]}"
        conn.execute("INSERT INTO messages_entrants(id, client_id, canal, date_reception, "
                     "contenu, reference_externe, facture_citee_id, statut_traitement) "
                     "VALUES (?,?,?,?,?,?,?,'A_CLASSER')",
                     (mid, client_id, canal, reception, contenu, reference_externe, facture_id))
        journaliser(conn, "MESSAGE_RECU", "MESSAGE", mid, acteur=acteur,
                    apres={"client_id": client_id, "canal": canal, "facture_citee_id": facture_id},
                    details={"extrait": contenu[:200]})
        svc_relances.annuler_injustifiees(conn, client_id, acteur)
        return dict(conn.execute("SELECT * FROM messages_entrants WHERE id = ?", (mid,)
                                 ).fetchone()), True


# ---- classification ---------------------------------------------------------------------
def _factures_ouvertes(conn: sqlite3.Connection, client_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT f.id, f.numero FROM factures f JOIN v_factures_solde v ON v.facture_id = f.id "
        "WHERE f.client_id = ? AND f.statut_document = 'VALIDEE' AND v.solde > 0 ORDER BY f.id",
        (client_id,)).fetchall()


def construire_entree(conn: sqlite3.Connection, m: sqlite3.Row) -> dict:
    """Minimisation : texte (tronqué, sans caractères de contrôle), canal, date, jour de la
    semaine et numéros des factures ouvertes. Ni nom, ni courriel, ni téléphone, ni montant."""
    return {"message_id": m["id"], "texte": nettoyer_texte(m["contenu"]), "canal": m["canal"],
            "date_reception": m["date_reception"],
            "jour_semaine": nom_jour(date.fromisoformat(m["date_reception"][:10])),
            "factures_ouvertes": [f["numero"] for f in _factures_ouvertes(conn, m["client_id"])]}


def _parametres_decision(conn: sqlite3.Connection) -> ParametresDecision:
    return ParametresDecision(
        seuil_sensible=Decimal(str(lire_decimal(conn, "seuil_confiance_sensible"))),
        seuil_prudent=Decimal(str(lire_decimal(conn, "seuil_confiance_prudent"))),
        plafond_promesse_jours=lire_entier(conn, "plafond_promesse_jours"))


def _facture_identifiable(conn: sqlite3.Connection, m: sqlite3.Row,
                          res: val.Resultat) -> str | None:
    """Facture visée : celle que le modèle cite (validée), sinon celle du message, sinon la
    seule facture ouverte du client."""
    ouvertes = _factures_ouvertes(conn, m["client_id"])
    if res.facture_citee:
        for f in ouvertes:
            if f["numero"] == res.facture_citee:
                return f["id"]
    if m["facture_citee_id"] and any(f["id"] == m["facture_citee_id"] for f in ouvertes):
        return m["facture_citee_id"]
    return ouvertes[0]["id"] if len(ouvertes) == 1 else None


def lire_message(conn: sqlite3.Connection, message_id: str) -> dict:
    m = conn.execute("SELECT * FROM messages_entrants WHERE id = ?", (message_id,)).fetchone()
    if m is None:
        raise Introuvable(f"Message {message_id} introuvable.")
    d = dict(m)
    d["copie_demandee"] = None if m["copie_demandee"] is None else bool(m["copie_demandee"])
    p = conn.execute("SELECT id FROM promesses_paiement WHERE message_source_id = ? "
                     "ORDER BY id", (message_id,)).fetchone()
    c = conn.execute("SELECT id FROM contestations WHERE message_source_id = ? ORDER BY id",
                     (message_id,)).fetchone()
    d["promesse_id"], d["contestation_id"] = (p[0] if p else None), (c[0] if c else None)
    d["revues"] = [dict(r) for r in conn.execute(
        "SELECT id, type, statut, motif FROM file_revue WHERE objet_type = 'MESSAGE' AND "
        "objet_id = ? ORDER BY id", (message_id,))]
    return d


def classer_message(conn: sqlite3.Connection, message_id: str, classeur: Adaptateur,
                    acteur: Acteur = IA) -> dict:
    """Classe un message (idempotent par version de consigne) et applique la décision.

    Jamais de transaction ouverte pendant l'appel au LLM : on lit, on appelle, puis on ouvre une
    transaction pour écrire."""
    m = conn.execute("SELECT * FROM messages_entrants WHERE id = ?", (message_id,)).fetchone()
    if m is None:
        raise Introuvable(f"Message {message_id} introuvable.")
    if m["statut_traitement"] != "A_CLASSER" and m["modele_version"] and \
            m["modele_version"].endswith(classeur.modele_version.split("@")[-1]):
        return {**lire_message(conn, message_id), "deja_classe": True}
    entree = construire_entree(conn, m)
    simulation = lire_booleen(conn, "simulation_llm_indisponible")
    try:
        res = classeur.classer(entree, simulation_indisponible=simulation)
    except Indisponible as e:
        with transaction(conn):
            journaliser(conn, "MESSAGE_A_CLASSER", "MESSAGE", message_id, acteur=acteur,
                        details={"raison": str(e)})
        return {**lire_message(conn, message_id), "deja_classe": False}
    with transaction(conn):
        m = conn.execute("SELECT * FROM messages_entrants WHERE id = ?", (message_id,)
                         ).fetchone()
        if m["statut_traitement"] != "A_CLASSER":       # un autre traitement est passé avant
            return {**lire_message(conn, message_id), "deja_classe": True}
        facture_id = _facture_identifiable(conn, m, res)
        dec = decider(res, _parametres_decision(conn), facture_id is not None,
                      clock.date_reference(conn))
        _appliquer(conn, m, res, dec, facture_id, classeur.modele_version, acteur)
    return {**lire_message(conn, message_id), "deja_classe": False}


def _appliquer(conn: sqlite3.Connection, m: sqlite3.Row, res: val.Resultat, dec: Decision,
               facture_id: str | None, modele_version: str, acteur: Acteur) -> None:
    mid = m["id"]
    conn.execute(
        "UPDATE messages_entrants SET statut_traitement = ?, categorie_ia = ?, confiance = ?, "
        "copie_demandee = ?, date_promise_extraite = ?, montant_promis = ?, decision_ia = ?, "
        "motif_revue = ?, justification = ?, modele_version = ?, classe_le = ?, "
        "facture_citee_id = COALESCE(?, facture_citee_id) WHERE id = ?",
        (dec.statut_message, res.categorie, res.confiance, int(res.copie_demandee),
         res.date_promise.isoformat() if res.date_promise else None, res.montant_promis,
         dec.decision_ia, dec.motif_revue, res.justification, modele_version,
         clock.maintenant(), facture_id, mid))
    if res.motif_repli:
        journaliser(conn, "CLASSIFICATION_REPLI", "MESSAGE", mid, acteur=acteur,
                    details={"motif": res.motif_repli})
    for type_, motif in dec.revues:
        ouvrir_revue(conn, type_, "MESSAGE", mid, m["client_id"], motif, acteur)
    effet = None
    if dec.creer == "PROMESSE":
        p = dossiers.creer_promesse_tx(conn, facture_id, res.date_promise, res.montant_promis,
                                       dec.origine_promesse, acteur, mid)
        effet = {"promesse_id": p["id"]}
    elif dec.creer == "CONTESTATION":
        c, _ = dossiers.ouvrir_contestation_tx(
            conn, facture_id, res.justification or "Contestation signalée par message", acteur,
            message_source_id=mid)
        effet = {"contestation_id": c["id"]}
    journaliser(conn, "MESSAGE_CLASSE", "MESSAGE", mid, acteur=acteur,
                apres={"categorie": res.categorie, "confiance": res.confiance,
                       "statut": dec.statut_message},
                details={"modele_version": modele_version, "decision": dec.decision_ia,
                         "motif_revue": dec.motif_revue, "effet": effet,
                         "drapeaux": list(res.drapeaux)})
    svc_relances.annuler_injustifiees(conn, m["client_id"], acteur)


def traiter_a_classer(conn: sqlite3.Connection, classeur: Adaptateur, limite: int = 20) -> int:
    """Corps du worker : reprend les messages A_CLASSER, du plus ancien au plus récent, dès que
    l'API répond. S'arrête au premier message resté en attente (API toujours indisponible)."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM messages_entrants WHERE statut_traitement = 'A_CLASSER' "
        "ORDER BY date_reception, id LIMIT ?", (limite,))]
    faits = 0
    for mid in ids:
        res = classer_message(conn, mid, classeur)
        if res["statut_traitement"] == "A_CLASSER":
            break
        faits += 1
    return faits


# ---- validation humaine -----------------------------------------------------------------
def valider_categorie(conn: sqlite3.Connection, message_id: str, categorie: str,
                      acteur: Acteur, role: str, date_promise: str | None = None,
                      montant_promis: int | None = None, facture_id: str | None = None,
                      commentaire: str | None = None) -> dict:
    """Classement humain, applique l'action de la catégorie validée avec les paramètres choisis
    (une promesse au-delà du plafond est permise à un VALIDATEUR). Fonctionne aussi pour un
    message A_CLASSER : c'est le mode dégradé manuel."""
    if categorie not in val.CATEGORIES:
        raise Validation(f"Catégorie inconnue : {categorie}.", {"valeurs": list(val.CATEGORIES)})
    with transaction(conn):
        m = conn.execute("SELECT * FROM messages_entrants WHERE id = ?", (message_id,)
                         ).fetchone()
        if m is None:
            raise Introuvable(f"Message {message_id} introuvable.")
        if m["statut_traitement"] == "TRAITE":
            raise RegleMetier("MESSAGE_DEJA_TRAITE", "Ce message a déjà été traité.")
        ouvertes = _factures_ouvertes(conn, m["client_id"])
        cible = facture_id or m["facture_citee_id"] or (
            ouvertes[0]["id"] if len(ouvertes) == 1 else None)
        if cible and not any(f["id"] == cible for f in ouvertes):
            raise RegleMetier("FACTURE_NON_OUVERTE", "La facture visée n'est pas ouverte.")
        effet = None
        if categorie in val.CATEGORIES_AVEC_DATE and date_promise:
            d = lire_date(date_promise)
            if d is None:
                raise Validation("date_promise doit être une date AAAA-MM-JJ.")
            if not cible:
                raise RegleMetier("FACTURE_NON_IDENTIFIABLE", "Précisez facture_id.")
            ref = clock.date_reference(conn)
            if d < ref:
                raise RegleMetier("DATE_PASSEE", "La date promise précède la date de référence.")
            if (d - ref).days > lire_entier(conn, "plafond_promesse_jours") \
                    and role != "VALIDATEUR":
                raise AccesRefuse("Au-delà du plafond, seul un VALIDATEUR peut valider.",
                                  {"role_requis": "VALIDATEUR"})
            p = dossiers.creer_promesse_tx(
                conn, cible, d, montant_promis,
                "PROMESSE" if categorie == "PROMESSE_PAIEMENT" else "DELAI", acteur, message_id)
            effet = {"promesse_id": p["id"]}
        elif categorie == "CONTESTATION" and cible:
            c, _ = dossiers.ouvrir_contestation_tx(
                conn, cible, commentaire or "Contestation validée par une personne", acteur,
                message_source_id=message_id)
            effet = {"contestation_id": c["id"]}
        conn.execute("UPDATE messages_entrants SET categorie_validee = ?, valide_par = ?, "
                     "statut_traitement = 'TRAITE', classe_le = COALESCE(classe_le, ?), "
                     "facture_citee_id = COALESCE(facture_citee_id, ?) WHERE id = ?",
                     (categorie, acteur.id, clock.maintenant(), cible, message_id))
        for (rid,) in conn.execute("SELECT id FROM file_revue WHERE objet_type = 'MESSAGE' AND "
                                   "objet_id = ? AND statut = 'OUVERTE'",
                                   (message_id,)).fetchall():
            conn.execute("UPDATE file_revue SET statut = 'RESOLUE', decision = ?, "
                         "commentaire = ?, decideur = ?, resolu_le = ? WHERE id = ?",
                         (f"CATEGORIE_VALIDEE_{categorie}", commentaire, acteur.id,
                          clock.maintenant(), rid))
            journaliser(conn, "REVUE_RESOLUE", "REVUE", rid, acteur=acteur,
                        apres={"decision": f"CATEGORIE_VALIDEE_{categorie}"})
        if categorie == "DEJA_PAYE":
            # Jamais de marquage automatique comme payé : la vérification passe par les routes
            # de paiement habituelles ; la revue VERIF_PAIEMENT est résolue avec le message.
            pass
        journaliser(conn, "MESSAGE_VALIDE", "MESSAGE", message_id, acteur=acteur,
                    avant={"statut": m["statut_traitement"], "categorie_ia": m["categorie_ia"]},
                    apres={"categorie_validee": categorie},
                    details={"commentaire": commentaire, "effet": effet})
        svc_relances.annuler_injustifiees(conn, m["client_id"], acteur)
    return lire_message(conn, message_id)


def lister_messages(conn: sqlite3.Connection, statut: str | None = None,
                    categorie: str | None = None, client_id: str | None = None) -> list[dict]:
    cond, args = [], []
    if statut:
        cond.append("statut_traitement = ?")
        args.append(statut)
    if categorie:
        cond.append("COALESCE(categorie_validee, categorie_ia) = ?")
        args.append(categorie)
    if client_id:
        cond.append("client_id = ?")
        args.append(client_id)
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    return [{"id": r["id"], "client_id": r["client_id"], "canal": r["canal"],
             "date_reception": r["date_reception"], "statut_traitement": r["statut_traitement"],
             "categorie_ia": r["categorie_ia"], "confiance": r["confiance"],
             "categorie_validee": r["categorie_validee"], "extrait": r["contenu"][:80]}
            for r in conn.execute("SELECT * FROM messages_entrants" + where + " ORDER BY id",
                                  args)]


def resoudre_revue_manuelle(conn: sqlite3.Connection, revue_id: str, decision: str,
                            commentaire: str | None, acteur: Acteur, role: str) -> dict:
    """`POST /api/revue/{id}/resoudre` n'enregistre que la décision et le commentaire : sert aux
    résolutions « sans suite » et à documenter une escalade."""
    reserve = {"ESCALADE", "LITIGE", "GROS_MONTANT", "DEMANDE_ECHEANCIER"}
    with transaction(conn):
        r = conn.execute("SELECT * FROM file_revue WHERE id = ?", (revue_id,)).fetchone()
        if r is None:
            raise Introuvable(f"Entrée de revue {revue_id} introuvable.")
        if r["type"] in reserve and role != "VALIDATEUR":
            raise AccesRefuse(f"Cette revue ({r['type']}) exige le rôle VALIDATEUR.",
                              {"role_requis": "VALIDATEUR"})
        if r["statut"] == "RESOLUE":
            raise RegleMetier("REVUE_DEJA_RESOLUE", "Cette entrée est déjà résolue.")
        if not decision.strip():
            raise Validation("La décision est obligatoire.")
        conn.execute("UPDATE file_revue SET statut = 'RESOLUE', decision = ?, commentaire = ?, "
                     "decideur = ?, resolu_le = ? WHERE id = ?",
                     (decision, commentaire, acteur.id, clock.maintenant(), revue_id))
        journaliser(conn, "REVUE_RESOLUE", "REVUE", revue_id, acteur=acteur,
                    avant={"statut": "OUVERTE"}, apres={"statut": "RESOLUE", "decision": decision},
                    details={"commentaire": commentaire})
        if r["objet_type"] == "MESSAGE" and r["type"] in ("VERIF_PAIEMENT", "DEMANDE_COPIE",
                                                          "INCERTAIN", "PROMESSE_A_VALIDER",
                                                          "DEMANDE_ECHEANCIER", "LITIGE"):
            autres = conn.execute("SELECT COUNT(*) FROM file_revue WHERE objet_type='MESSAGE' "
                                  "AND objet_id = ? AND statut = 'OUVERTE'",
                                  (r["objet_id"],)).fetchone()[0]
            if autres == 0:
                conn.execute("UPDATE messages_entrants SET statut_traitement = 'TRAITE' WHERE "
                             "id = ? AND statut_traitement = 'EN_REVUE'", (r["objet_id"],))
                svc_relances.annuler_injustifiees(conn, r["client_id"], acteur)
        return dict(conn.execute("SELECT * FROM file_revue WHERE id = ?", (revue_id,)
                                 ).fetchone())
