# ==============================================================================
# A.U.R.O.R.A. System Makefile (M10)
# ==============================================================================

.PHONY: help build up down logs bench

help:
	@echo "A.U.R.O.R.A. Genesis Commands:"
	@echo "  make build  - Build all Docker images"
	@echo "  make up     - Start the entire system in detached mode"
	@echo "  make down   - Stop and remove all containers"
	@echo "  make logs   - Tail all logs"
	@echo "  make bench  - Run the M9 Benchmark Suite locally"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

bench:
	cd evals && python run_evals.py
