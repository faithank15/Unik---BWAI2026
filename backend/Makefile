PY := .venv/bin/python
VENV := .venv

.PHONY: install run test test-rapide cov lint reset dataset openapi rapport eval-ia eval-ia-test

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -e ".[dev]"

run:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest

test-rapide:
	$(PY) -m pytest -m "not lent and not equivalence"

cov:
	$(PY) -m pytest --cov=app/domain --cov=app/services --cov-report=term-missing

lint:
	$(VENV)/bin/ruff check app tests dataset scripts

reset:
	$(PY) -m app.cli reset

rapport:
	$(PY) -m pytest --junitxml=junit.xml --cov=app/domain --cov=app/services --cov=app/ia --cov-report=json:coverage.json --cov-report=term
	$(PY) scripts/rapport_tests.py

openapi:
	$(PY) scripts/export_openapi.py

dataset:
	$(PY) dataset/generate_dataset.py --seed 20261215 --out dataset/
	$(PY) dataset/tests_coherence.py

eval-ia:
	$(PY) -m app.eval.eval_ia --methode regle --split DEV --sortie rapport_ia_regle_dev.md
	@if grep -q '^LLM_API_KEY=.\+' .env 2>/dev/null; then \
	  $(PY) -m app.eval.eval_ia --methode llm --split DEV --sortie rapport_ia_llm_dev.md; \
	else echo "LLM_API_KEY vide : évaluation du modèle réel ignorée (voir README)."; fi

eval-ia-test:
	$(PY) -m app.eval.eval_ia --methode llm --split TEST --confirmer-gel --sortie rapport_ia_llm_test.md
