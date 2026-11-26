"""Client HTTP du LLM (Gemini). Isolé dans l'adaptateur ; remplacé par un faux dans les tests.

Appel `generateContent` en JSON, température nulle, sortie contrainte par un schéma (document IA,
section 3), réflexion réduite pour limiter la latence. Les erreurs HTTP (503 « forte demande »,
429 quota, délai dépassé) remontent comme exceptions : l'adaptateur les réessaie puis met le
message en file « à classer ». La clé n'est lue que par ce client et n'apparaît jamais dans un
message d'erreur.
"""
import httpx

from app.domain.redaction import TONS
from app.ia.adaptateur import construire_prompt, construire_prompt_redaction
from app.ia.validation import CATEGORIES

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "categorie": {"type": "STRING", "enum": list(CATEGORIES)},
        "confiance": {"type": "NUMBER"},
        "copie_demandee": {"type": "BOOLEAN"},
        "date_promise": {"type": "STRING", "nullable": True},
        "montant_promis": {"type": "INTEGER", "nullable": True},
        "facture_citee": {"type": "STRING", "nullable": True},
        "justification": {"type": "STRING"},
    },
    "required": ["categorie", "confiance", "copie_demandee", "date_promise", "montant_promis",
                 "facture_citee", "justification"],
}


SCHEMA_REDACTION = {
    "type": "OBJECT",
    "properties": {
        "objet": {"type": "STRING"},
        "introduction": {"type": "STRING"},
        "conclusion": {"type": "STRING"},
        "ton_applique": {"type": "STRING", "enum": list(TONS)},
    },
    "required": ["objet", "introduction", "conclusion", "ton_applique"],
}


JETONS_SORTIE_REDACTION = 4096


class ReponseVide(Exception):
    """Le modèle n'a renvoyé aucun texte exploitable (blocage, coupure, réponse vide)."""


class ClientGemini:
    def __init__(self, cle_api: str, modele: str, timeout: float = 15.0,
                 niveau_reflexion: str | None = "low", max_jetons_sortie: int = 1024):
        self._cle, self._modele, self._timeout = cle_api, modele, timeout
        self._reflexion, self._max = niveau_reflexion, max_jetons_sortie
        self.dernier_usage: dict | None = None     # jetons de la dernière réponse (coûts)

    def _corps(self, prompt: str, schema: dict, max_jetons: int | None = None) -> dict:
        config: dict = {"temperature": 0, "maxOutputTokens": max_jetons or self._max,
                        "responseMimeType": "application/json", "responseSchema": schema}
        if self._reflexion:
            config["thinkingConfig"] = {"thinkingLevel": self._reflexion}
        return {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}

    def corps(self, entree: dict) -> dict:
        return self._corps(construire_prompt(entree), SCHEMA)

    def corps_redaction(self, contexte: dict) -> dict:
        # La réflexion du modèle consomme ~1 000 jetons avant la réponse : une limite de 1 024
        # tronquait le JSON (mesuré sur 40 combinaisons). La rédaction demande une marge large.
        return self._corps(construire_prompt_redaction(contexte), SCHEMA_REDACTION,
                           max(self._max, JETONS_SORTIE_REDACTION))

    def classer(self, entree: dict) -> str:
        return self._appeler(self.corps(entree))

    def rediger(self, contexte: dict) -> str:
        return self._appeler(self.corps_redaction(contexte))

    def _appeler(self, corps: dict) -> str:
        try:
            r = httpx.post(URL.format(modele=self._modele), timeout=self._timeout,
                           headers={"x-goog-api-key": self._cle}, json=corps)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # le détail de l'erreur ne contient jamais la clé (elle est dans un en-tête)
            raise RuntimeError(f"HTTP {e.response.status_code} : "
                               f"{e.response.text[:200]}") from None
        data = r.json()
        self.dernier_usage = data.get("usageMetadata")
        parties = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        texte = "".join(p.get("text", "") for p in parties if not p.get("thought"))
        if not texte.strip():
            raison = (data.get("candidates") or [{}])[0].get("finishReason", "inconnue")
            raise ReponseVide(f"réponse vide (finishReason={raison})")
        return texte
