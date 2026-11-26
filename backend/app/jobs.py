"""Worker de classification : toutes les deux secondes, reprend les messages A_CLASSER les plus
anciens. Démarré avec l'application seulement si un LLM est configuré."""
import logging
import threading

from app.db import connecter
from app.ia.adaptateur import Adaptateur
from app.services.messages import traiter_a_classer

journal_technique = logging.getLogger("recouvrement.worker")


class Worker:
    def __init__(self, chemin_base: str, classeur: Adaptateur, periode: float = 2.0):
        self._chemin, self._classeur, self._periode = chemin_base, classeur, periode
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._boucle, daemon=True, name="classification")

    def demarrer(self) -> None:
        self._thread.start()

    def arreter(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _boucle(self) -> None:
        while not self._stop.wait(self._periode):
            try:
                conn = connecter(self._chemin)
                try:
                    traiter_a_classer(conn, self._classeur)
                finally:
                    conn.close()
            except Exception:  # noqa: BLE001 - le worker ne doit jamais mourir
                journal_technique.exception("Erreur du worker de classification")
