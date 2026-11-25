# ==============================================================================
# ÆHub Makefile
# ==============================================================================

PYTHON ?= python

.PHONY: help setup build up down logs secrets eval eval-baseline demo

help:
	@echo "ÆHub commands:"
	@echo "  make setup         - Keys into the OS keyring, working folder (first run)"
	@echo "  make demo          - Start the stack and run one approved task end to end"
	@echo "  make build         - Build all Docker images"
	@echo "  make up            - Start the system with the keys from the keyring"
	@echo "  make down          - Stop and remove all containers"
	@echo "  make secrets       - Which keys are set (never their values)"
	@echo "  make logs          - Tail all logs"
	@echo "  make eval          - Run the offline agent evaluation gate"
	@echo "  make eval-baseline - Re-record evals/baseline.json"

build:
	docker compose build

setup:
	$(PYTHON) scripts/aehub.py setup

up:
	$(PYTHON) scripts/aehub.py up

down:
	$(PYTHON) scripts/aehub.py down

secrets:
	$(PYTHON) scripts/aehub.py secrets

logs:
	docker compose logs -f

eval:
	$(PYTHON) evals/run_evals.py --baseline evals/baseline.json

eval-baseline:
	$(PYTHON) evals/run_evals.py --baseline evals/baseline.json --update-baseline

demo:
	$(PYTHON) scripts/demo.py
