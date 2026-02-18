
.PHONY: install setup-server run-server run-client test clean

install:
	bash install.sh

setup:
	cp .env.example .env
	pip install -r requirements.txt

run:
	python3 client/app.py

test:
	pytest server/tests
	pytest client/tests

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache
