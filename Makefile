.DEFAULT_GOAL := fmt
DIR = freddie

fmt:
	isort --recursive $(DIR)
	black $(DIR)

type:
	mypy $(DIR)

lint:
	isort --recursive --check-only --diff $(DIR)
	black --check $(DIR)
	flake8 $(DIR)

test:
	pytest -vv

cov:
	pytest --cov=$(DIR) --cov-report term:skip-covered

check:
	make lint && make type

run:
	python tests/main.py
