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

cover:
	coverage erase
	coverage run --include=$(DIR)/* -m pytest
	coverage report -m

check:
	make lint && make type

run:
	python tests/main.py
