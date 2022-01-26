.DEFAULT_GOAL := fmt
DIR = freddie
VENV = venv

fmt:
	isort $(DIR)
	black $(DIR)

type:
	mypy $(DIR)

lint:
	isort --check-only --diff $(DIR)
	black --check $(DIR)
	flake8 $(DIR)

test:
	pytest -vv

cov:
	pytest --cov=$(DIR) --cov-report term-missing:skip-covered

check:
	make lint && make type

run:
	python -m tests.main run

db:
	python -m tests.main create-db

dev:
	python3 -m venv $(VENV) --clear --upgrade-deps
	$(VENV)/bin/pip install flit
	$(VENV)/bin/flit install --env --symlink
