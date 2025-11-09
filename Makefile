PY=python3.11

.PHONY: setup env run seed lint fmt precommit docker

setup: env install precommit seed
	@echo "Setup complete."

env:
	@test -d .venv || $(PY) -m venv .venv
	@. .venv/bin/activate; pip install --upgrade pip

install:
	@. .venv/bin/activate; pip install -r requirements.txt

precommit:
	@. .venv/bin/activate; pre-commit install || true

run:
	@. .venv/bin/activate; STREAMLIT_SERVER_PORT=$${STREAMLIT_SERVER_PORT:-8501} streamlit run streamlit_app/0_Home.py

seed:
	@. .venv/bin/activate; $(PY) scripts/seed_data.py

lint:
	@. .venv/bin/activate; ruff check .

fmt:
	@. .venv/bin/activate; ruff check . --fix; black .

docker:
	docker compose up --build

