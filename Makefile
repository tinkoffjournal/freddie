.DEFAULT_GOAL := format

format:
	isort --recursive .
	black .

check:
	isort --recursive --check-only --diff .
	black --check .
	flake8 --config=flake8.ini
