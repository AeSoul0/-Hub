# ==============================================================================
# ÆHub Makefile
# ==============================================================================

PYTHON ?= python

.PHONY: help build up down logs eval eval-baseline demo

help:
	@echo "ÆHub commands:"
	@echo "  make demo          - Start the stack and run one approved task end to end"
	@echo "  make build         - Build all Docker images"
	@echo "  make up            - Start the entire system in detached mode"
	@echo "  make down          - Stop and remove all containers"
	@echo "  make logs          - Tail all logs"
	@echo "  make eval          - Run the offline agent evaluation gate"
	@echo "  make eval-baseline - Re-record evals/baseline.json"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

eval:
	$(PYTHON) evals/run_evals.py --baseline evals/baseline.json

eval-baseline:
	$(PYTHON) evals/run_evals.py --baseline evals/baseline.json --update-baseline

demo:
	$(PYTHON) scripts/demo.py
