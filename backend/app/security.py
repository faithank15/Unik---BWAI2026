"""Mots de passe, sessions opaques et rôles.

Mots de passe hachés avec hashlib.scrypt (sel de 16 octets, format
`scrypt$n$r$p$sel$empreinte`), comparés avec hmac.compare_digest. Le jeton de session est
opaque (32 octets aléatoires) ; seule son empreinte SHA-256 est stockée.
"""
import hashlib
import hmac
import secrets
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app import clock
from app.db import prochain_id, transaction
from app.errors import AccesRefuse, NonAuthentifie, TropDeTentatives
from app.journal import journaliser, utilisateur

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
ROLES = {"GESTIONNAIRE": 1, "VALIDATEUR": 2}

FENETRE_ECHECS_S = 300
MAX_ECHECS = 5
BLOCAGE_S = 300
_echecs: dict[str, list[float]] = defaultdict(list)
_bloque_jusqua: dict[str, float] = {}


def reinitialiser_limiteur() -> None:
    _echecs.clear()
    _bloque_jusqua.clear()


def hacher(mot_de_passe: str) -> str:
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(mot_de_passe.encode(), salt=sel, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                       maxmem=64 * 1024 * 1024)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${sel.hex()}${h.hex()}"


def verifier(mot_de_passe: str, hash_stocke: str) -> bool:
    try:
        _, n, r, p, sel, attendu = hash_stocke.split("$")
        h = hashlib.scrypt(mot_de_passe.encode(), salt=bytes.fromhex(sel), n=int(n), r=int(r),
                           p=int(p), maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h.hex(), attendu)


def empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


@dataclass(frozen=True)
class Utilisateur:
    id: str
    nom_utilisateur: str
    nom_affiche: str
    role: str


def creer_utilisateur(conn: sqlite3.Connection, nom: str, affiche: str, role: str,
                      mot_de_passe: str) -> str:
    uid = prochain_id(conn, "USR")
    conn.execute("INSERT INTO utilisateurs(id, nom_utilisateur, nom_affiche, role, "
                 "mot_de_passe_hash) VALUES (?,?,?,?,?)",
                 (uid, nom, affiche, role, hacher(mot_de_passe)))
    return uid


def _limiter(nom: str) -> None:
    maintenant = clock.instant()
    if _bloque_jusqua.get(nom, 0) > maintenant:
        raise TropDeTentatives("Trop de tentatives de connexion : réessayer dans quelques "
                               "minutes.")


def _noter_echec(nom: str) -> None:
    maintenant = clock.instant()
    recents = [t for t in _echecs[nom] if maintenant - t < FENETRE_ECHECS_S]
    recents.append(maintenant)
    _echecs[nom] = recents
    if len(recents) >= MAX_ECHECS:
        _bloque_jusqua[nom] = maintenant + BLOCAGE_S


def connexion(conn: sqlite3.Connection, nom: str, mot_de_passe: str,
              ttl_heures: int) -> tuple[str, str, Utilisateur]:
    """Vérifie le mot de passe et ouvre une session. Retourne (jeton, expire_le, utilisateur).
    Message identique pour un identifiant inconnu et un mauvais mot de passe."""
    _limiter(nom)
    ligne = conn.execute("SELECT * FROM utilisateurs WHERE nom_utilisateur = ? AND actif = 1",
                         (nom,)).fetchone()
    # Un hachage est calculé même si l'utilisateur n'existe pas (temps constant).
    factice = "scrypt$16384$8$1$" + "00" * 16 + "$" + "00" * 64
    ok = verifier(mot_de_passe, ligne["mot_de_passe_hash"] if ligne else factice)
    if not ligne or not ok:
        _noter_echec(nom)
        with transaction(conn):
            journaliser(conn, "CONNEXION_ECHEC", "UTILISATEUR", None,
                        details={"nom_utilisateur": nom[:50]})
        raise NonAuthentifie("Identifiant ou mot de passe incorrect.")
    _echecs.pop(nom, None)
    jeton = secrets.token_urlsafe(32)
    cree = clock.maintenant_dt()
    expire = (cree + timedelta(hours=ttl_heures)).isoformat(timespec="seconds")
    u = Utilisateur(ligne["id"], ligne["nom_utilisateur"], ligne["nom_affiche"], ligne["role"])
    with transaction(conn):
        conn.execute("INSERT INTO sessions(token_hash, utilisateur_id, cree_le, expire_le) "
                     "VALUES (?,?,?,?)", (empreinte_jeton(jeton),
                                          u.id, cree.isoformat(timespec="seconds"), expire))
        journaliser(conn, "CONNEXION", "UTILISATEUR", u.id, acteur=utilisateur(u.id))
    return jeton, expire, u


def deconnexion(conn: sqlite3.Connection, jeton: str, u: Utilisateur) -> None:
    with transaction(conn):
        conn.execute("UPDATE sessions SET revoquee = 1 WHERE token_hash = ?",
                     (empreinte_jeton(jeton),))
        journaliser(conn, "DECONNEXION", "UTILISATEUR", u.id, acteur=utilisateur(u.id))


def utilisateur_du_jeton(conn: sqlite3.Connection, jeton: str | None) -> Utilisateur:
    """401 si le jeton est absent, inconnu, expiré ou révoqué."""
    if not jeton:
        raise NonAuthentifie("Jeton d'accès absent.")
    ligne = conn.execute(
        "SELECT s.expire_le, s.revoquee, u.* FROM sessions s "
        "JOIN utilisateurs u ON u.id = s.utilisateur_id "
        "WHERE s.token_hash = ? AND u.actif = 1", (empreinte_jeton(jeton),)).fetchone()
    if ligne is None or ligne["revoquee"]:
        raise NonAuthentifie("Jeton d'accès invalide ou révoqué.")
    if datetime.fromisoformat(ligne["expire_le"]) <= clock.maintenant_dt():
        raise NonAuthentifie("Jeton d'accès expiré.")
    return Utilisateur(ligne["id"], ligne["nom_utilisateur"], ligne["nom_affiche"],
                       ligne["role"])


def verifier_role(conn: sqlite3.Connection, u: Utilisateur, minimal: str, route: str) -> None:
    """403 et événement ACCES_REFUSE si le rôle est insuffisant."""
    if ROLES[u.role] < ROLES[minimal]:
        with transaction(conn):
            journaliser(conn, "ACCES_REFUSE", "ROUTE", route, acteur=utilisateur(u.id),
                        details={"role": u.role, "role_requis": minimal})
        raise AccesRefuse(f"Cette action exige le rôle {minimal}.",
                          {"role_requis": minimal})


PREFIXES_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def neutraliser_formule(valeur: object) -> object:
    """Protection contre l'injection de formules à l'export CSV : toute valeur texte commençant
    par =, +, - ou @ est préfixée d'une apostrophe. Les nombres ne sont pas modifiés."""
    if isinstance(valeur, str) and valeur.startswith(PREFIXES_FORMULE):
        return "'" + valeur
    return valeur
