# Auction Houses App - Development Commands

.PHONY: help build up down logs shell db-shell test clean

# Default target
help: ## Show this help message
	@echo "Auction Houses Database Application"
	@echo "=================================="
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Docker operations
build: ## Build Docker containers
	docker-compose build

up: ## Start all services
	docker-compose up -d
	@echo "Services started!"
	@echo "API Docs: http://localhost:8000/docs"
	@echo "API Base: http://localhost:8000/api/v1"

up-backend: ## Start backend services only (no frontend)
	docker-compose up -d postgres redis backend celery_worker celery_beat
	@echo "Backend services started!"

down: ## Stop all services
	docker-compose down

logs: ## View logs from all services
	docker-compose logs -f

logs-api: ## View API logs only
	docker-compose logs -f backend

logs-worker: ## View Celery worker logs
	docker-compose logs -f celery_worker

# Development
shell: ## Access backend container shell
	docker-compose exec backend bash

db-shell: ## Access PostgreSQL shell
	docker-compose exec postgres psql -U auction_user -d auction_houses

db-reset: ## Reset database (WARNING: destroys all data)
	docker-compose down -v
	docker-compose up -d postgres redis
	@echo "Database reset complete"

# Code quality
format: ## Format Python code
	docker-compose exec backend black app/
	docker-compose exec backend isort app/

lint: ## Run linting
	docker-compose exec backend flake8 app/

test: ## Run tests (when implemented)
	docker-compose exec backend pytest

test-api: ## Test API endpoints
	python scripts/test_api.py

# Database operations
db-migrate: ## Run database migrations
	docker-compose exec backend alembic upgrade head

db-seed: ## Seed database with initial data
	@echo "Database seeding handled by init scripts"

# Monitoring
status: ## Check service status
	docker-compose ps

health: ## Check API health
	@curl -s http://localhost:8000/health | python -m json.tool || echo "API not accessible"

# Cleanup
clean: ## Remove containers, images, and volumes
	docker-compose down -v --rmi all
	docker system prune -f

# Quick development cycle
dev: down up-backend logs-api ## Quick restart backend for development

setup: ## Complete setup guide (recommended for first time)
	python quick_start.py

# Production commands (for future use)
prod-build: ## Build for production
	docker-compose -f docker-compose.prod.yml build

prod-up: ## Start production services
	docker-compose -f docker-compose.prod.yml up -d

# Data operations
populate-test-data: ## Populate database with test data
	python scripts/populate_test_data.py

backup-db: ## Backup database (implementation needed)
	@echo "Database backup feature to be implemented"

restore-db: ## Restore database (implementation needed)  
	@echo "Database restore feature to be implemented"