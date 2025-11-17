# GALILEO V2.0 - Makefile
# Production-ready build and development automation

.PHONY: help dev-up dev-down test-all test-py test-rs lint format clean install build docs

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

##@ General

help: ## Display this help message
	@echo "$(BLUE)GALILEO V2.0 - Build System$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

dev-up: ## Start all development services (Docker Compose)
	@echo "$(GREEN)Starting development environment...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "  - API: http://localhost:8000"
	@echo "  - UI: http://localhost:3000"
	@echo "  - Grafana: http://localhost:3001"
	@echo "  - MinIO: http://localhost:9001"
	@make _wait-for-services

dev-down: ## Stop all development services
	@echo "$(YELLOW)Stopping development environment...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

dev-logs: ## Tail logs from all services
	docker-compose logs -f

dev-restart: dev-down dev-up ## Restart development environment

_wait-for-services: ## Wait for services to be ready
	@echo "$(BLUE)Waiting for services to be ready...$(NC)"
	@timeout 60 bash -c 'until docker-compose exec -T db pg_isready -U galileo 2>/dev/null; do sleep 1; done' || true
	@echo "$(GREEN)✓ Database ready$(NC)"

##@ Testing

test-all: test-py test-rs ## Run all tests (Python + Rust)

test-py: ## Run Python tests
	@echo "$(BLUE)Running Python tests...$(NC)"
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html --cov-report=xml
	@echo "$(GREEN)✓ Python tests passed$(NC)"

test-rs: ## Run Rust tests
	@echo "$(BLUE)Running Rust tests...$(NC)"
	cargo test --all-features
	@echo "$(GREEN)✓ Rust tests passed$(NC)"

test-bench: ## Run benchmark suite
	@echo "$(BLUE)Running benchmark suite...$(NC)"
	python bench.py --suite all --report html
	@echo "$(GREEN)✓ Benchmarks complete$(NC)"

test-unit: ## Run unit tests only
	pytest tests/unit/ -v

test-integration: ## Run integration tests only
	pytest tests/integration/ -v --slow

test-security: ## Run security tests
	@echo "$(BLUE)Running security tests...$(NC)"
	pytest tests/security/ -v
	bandit -r . -ll -x tests/
	@echo "$(GREEN)✓ Security tests passed$(NC)"

##@ Code Quality

lint: lint-py lint-rs ## Run all linters

lint-py: ## Lint Python code
	@echo "$(BLUE)Linting Python...$(NC)"
	ruff check .
	mypy .
	@echo "$(GREEN)✓ Python linting passed$(NC)"

lint-rs: ## Lint Rust code
	@echo "$(BLUE)Linting Rust...$(NC)"
	cargo clippy --all-targets --all-features -- -D warnings
	@echo "$(GREEN)✓ Rust linting passed$(NC)"

format: format-py format-rs ## Format all code

format-py: ## Format Python code
	@echo "$(BLUE)Formatting Python...$(NC)"
	black .
	ruff check --fix .
	@echo "$(GREEN)✓ Python formatted$(NC)"

format-rs: ## Format Rust code
	@echo "$(BLUE)Formatting Rust...$(NC)"
	cargo fmt --all
	@echo "$(GREEN)✓ Rust formatted$(NC)"

check: lint test-all ## Run all checks (lint + test)

##@ Build

install: install-py install-rs ## Install all dependencies

install-py: ## Install Python dependencies
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	pip install -e ".[dev,ml,control]"
	pip install -r requirements.txt
	@echo "$(GREEN)✓ Python dependencies installed$(NC)"

install-rs: ## Install/build Rust components
	@echo "$(BLUE)Building Rust components...$(NC)"
	cargo build --release
	@echo "$(GREEN)✓ Rust build complete$(NC)"

build: build-py build-rs ## Build all components

build-py: ## Build Python packages
	@echo "$(BLUE)Building Python packages...$(NC)"
	python -m build
	@echo "$(GREEN)✓ Python packages built$(NC)"

build-rs: ## Build Rust release binaries
	@echo "$(BLUE)Building Rust release...$(NC)"
	cargo build --release --all-features
	@echo "$(GREEN)✓ Rust release built$(NC)"

build-ui: ## Build UI production bundle
	@echo "$(BLUE)Building UI...$(NC)"
	cd ui && npm install && npm run build
	@echo "$(GREEN)✓ UI built$(NC)"

build-docker: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker-compose build
	@echo "$(GREEN)✓ Docker images built$(NC)"

##@ Documentation

docs: ## Build documentation
	@echo "$(BLUE)Building documentation...$(NC)"
	mkdocs build
	@echo "$(GREEN)✓ Documentation built$(NC)"
	@echo "  Open: docs/site/index.html"

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Serving documentation at http://localhost:8080$(NC)"
	mkdocs serve -a localhost:8080

docs-deploy: ## Deploy documentation to GitHub Pages
	@echo "$(BLUE)Deploying documentation...$(NC)"
	mkdocs gh-deploy --force
	@echo "$(GREEN)✓ Documentation deployed$(NC)"

##@ Database

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running migrations...$(NC)"
	alembic upgrade head
	@echo "$(GREEN)✓ Migrations applied$(NC)"

db-reset: ## Reset database (WARNING: deletes all data)
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose exec db psql -U galileo -c "DROP DATABASE IF EXISTS galileo;"; \
		docker-compose exec db psql -U galileo -c "CREATE DATABASE galileo;"; \
		make db-migrate; \
		echo "$(GREEN)✓ Database reset$(NC)"; \
	fi

db-shell: ## Open database shell
	docker-compose exec db psql -U galileo galileo

##@ Utilities

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/ dist/ *.egg-info
	rm -rf target/ Cargo.lock
	rm -rf ui/dist/ ui/.next/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)✓ Clean complete$(NC)"

seed: ## Load seed data
	@echo "$(BLUE)Loading seed data...$(NC)"
	python scripts/seed_data.py
	@echo "$(GREEN)✓ Seed data loaded$(NC)"

shell: ## Open Python shell with imports
	@echo "$(BLUE)Opening Python shell...$(NC)"
	python -i -c "import numpy as np; import matplotlib.pyplot as plt; from sim import *; from inversion import *; from ml import *"

##@ CI/CD

ci: lint test-all ## Run CI checks locally
	@echo "$(GREEN)✓ CI checks passed$(NC)"

sbom: ## Generate Software Bill of Materials
	@echo "$(BLUE)Generating SBOM...$(NC)"
	syft dir:. -o spdx-json > sbom.json
	@echo "$(GREEN)✓ SBOM generated: sbom.json$(NC)"

sbom-sign: sbom ## Sign SBOM with cosign
	@echo "$(BLUE)Signing SBOM...$(NC)"
	cosign sign-blob --key cosign.key sbom.json > sbom.json.sig
	@echo "$(GREEN)✓ SBOM signed$(NC)"

scan-trivy: ## Scan for vulnerabilities with Trivy
	@echo "$(BLUE)Scanning with Trivy...$(NC)"
	trivy fs --security-checks vuln,config .
	@echo "$(GREEN)✓ Trivy scan complete$(NC)"

scan-codeql: ## Run CodeQL analysis
	@echo "$(BLUE)Running CodeQL...$(NC)"
	codeql database create codeql-db --language=python,javascript
	codeql database analyze codeql-db --format=sarif-latest --output=codeql-results.sarif
	@echo "$(GREEN)✓ CodeQL analysis complete$(NC)"

##@ Git

commit: format lint ## Format, lint, and prepare for commit
	@echo "$(GREEN)✓ Ready to commit$(NC)"
	git status

push: ci ## Run CI and push to remote
	@echo "$(BLUE)Running pre-push checks...$(NC)"
	@make ci
	@echo "$(GREEN)✓ All checks passed. Pushing...$(NC)"
	git push -u origin $$(git branch --show-current)

##@ Release

version-bump-patch: ## Bump patch version
	@echo "$(BLUE)Bumping patch version...$(NC)"
	bump2version patch

version-bump-minor: ## Bump minor version
	@echo "$(BLUE)Bumping minor version...$(NC)"
	bump2version minor

version-bump-major: ## Bump major version
	@echo "$(BLUE)Bumping major version...$(NC)"
	bump2version major

release: ci build docs ## Create release (CI + build + docs)
	@echo "$(GREEN)✓ Release ready$(NC)"
	@echo "  Next: git tag v$(VERSION) && git push --tags"

##@ Monitoring

monitor: ## Open monitoring dashboards
	@echo "$(BLUE)Opening monitoring dashboards...$(NC)"
	@echo "  Grafana: http://localhost:3001"
	@echo "  Prometheus: http://localhost:9090"
	xdg-open http://localhost:3001 2>/dev/null || open http://localhost:3001 || echo "Open http://localhost:3001 manually"

logs-api: ## Tail API logs
	docker-compose logs -f api

logs-db: ## Tail database logs
	docker-compose logs -f db

logs-worker: ## Tail Celery worker logs
	docker-compose logs -f worker

##@ Profiling

profile-py: ## Profile Python performance
	@echo "$(BLUE)Profiling Python...$(NC)"
	python -m cProfile -o profile.stats scripts/benchmark.py
	python -m pstats profile.stats

profile-rs: ## Profile Rust performance
	@echo "$(BLUE)Profiling Rust...$(NC)"
	cargo build --release --features profiling
	valgrind --tool=callgrind target/release/galileo
	kcachegrind callgrind.out.* &

benchmark-rs: ## Run Rust benchmarks with Criterion
	@echo "$(BLUE)Running Rust benchmarks...$(NC)"
	cargo bench
	@echo "$(GREEN)✓ Benchmarks complete. Open target/criterion/report/index.html$(NC)"
