"""Création de l'application FastAPI : routes, erreurs homogènes, en-têtes de sécurité."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, dossiers, flux, messages, portefeuille, relances, systeme, tableau
from app.config import Reglages, charger_reglages
from app.errors import ErreurMetier, corps_erreur
from app.ia.adaptateur import Adaptateur
from app.ia.gemini import ClientGemini
from app.jobs import Worker
from app.journal import correlation_courante

journal_technique = logging.getLogger("recouvrement")


def creer_app(reglages: Reglages | None = None, classeur: Adaptateur | None = None) -> FastAPI:
    reglages = reglages or charger_reglages()
    logging.basicConfig(level=reglages.log_level)
    @asynccontextmanager
    async def cycle_de_vie(app: FastAPI):
        worker = None
        if reglages.llm_configure:     # le worker ne démarre que si un LLM est configuré
            worker = Worker(reglages.database_path, app.state.classeur)
            worker.demarrer()
        yield
        if worker:
            worker.arreter()

    app = FastAPI(title="Recouvrement automatique des factures impayées – BWAI 2026",
                  version=systeme.VERSION, lifespan=cycle_de_vie,
                  description="Prototype de démonstration. Tout est simulé.")
    app.state.reglages = reglages
    if classeur is None:
        client = (ClientGemini(reglages.llm_api_key, reglages.llm_modele,
                               reglages.llm_timeout_secondes) if reglages.llm_configure else None)
        classeur = Adaptateur(client, modele=reglages.llm_modele or "non-configure",
                              reessais=reglages.llm_reessais)
    app.state.classeur = classeur
    app.add_middleware(CORSMiddleware, allow_origins=list(reglages.cors_origins),
                       allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Correlation-Id"])

    @app.middleware("http")
    async def entetes(request: Request, call_next):
        cid = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex[:16]
        jeton = correlation_courante.set(cid)
        request.state.correlation_id = cid
        try:
            reponse = await call_next(request)
        finally:
            correlation_courante.reset(jeton)
        reponse.headers["X-Correlation-Id"] = cid
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Cache-Control"] = "no-store"
        return reponse

    def reponse(http: int, code: str, message: str, details, request: Request):
        return JSONResponse(corps_erreur(code, message, details,
                                         getattr(request.state, "correlation_id", None)),
                            status_code=http)

    @app.exception_handler(ErreurMetier)
    async def _metier(request: Request, e: ErreurMetier):
        return reponse(e.http, e.code, e.message, e.details, request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, e: RequestValidationError):
        champs = [{"champ": ".".join(str(x) for x in err["loc"]), "message": err["msg"]}
                  for err in e.errors()]
        return reponse(400, "VALIDATION", "Corps ou paramètres mal formés.",
                       {"champs": champs}, request)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, e: StarletteHTTPException):
        code = {404: "INTROUVABLE", 405: "VALIDATION"}.get(e.status_code, "ERREUR_INTERNE")
        return reponse(e.status_code, code, str(e.detail), {}, request)

    @app.exception_handler(Exception)
    async def _inattendue(request: Request, e: Exception):
        journal_technique.exception("Erreur inattendue")
        return reponse(500, "ERREUR_INTERNE", "Erreur interne du service.", {}, request)

    app.include_router(systeme.routeur)
    app.include_router(portefeuille.routeur)
    app.include_router(flux.routeur)
    app.include_router(relances.routeur)
    app.include_router(messages.routeur)
    app.include_router(dossiers.routeur)
    app.include_router(tableau.routeur)
    app.include_router(admin.routeur)
    return app


app = creer_app()
