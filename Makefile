# Twilio Demo Makefile

# Python virtual environment path
PYTHON = ./venv/bin/python
PIP = ./venv/bin/pip


# Environment variables
export TWILIO_ACCOUNT_SID=your_account_sid
export TWILIO_AUTH_TOKEN=your_auth_token
export TWILIO_NUMBER=your_twilio_phone_number
export PALABRA_CLIENT_ID=your_client_id
export PALABRA_CLIENT_SECRET=your_client_secret
export HOST=your_host
export OPERATOR_NUMBER=operator_phone_number
export PORT=7839
export SOURCE_LANGUAGE=en
export TARGET_LANGUAGE=pl

# Default target
.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make run        - Run the server"
	@echo "  make dev        - Run with development dependencies"
	@echo "  make clean      - Clean up virtual environment"
	@echo "  make format     - Format code with black and isort"
	@echo "  make check      - Run all code quality checks"

# Install dependencies
.PHONY: install
install:
	@echo "Creating virtual environment..."
	python -m venv venv
	@echo "Installing dependencies..."
	$(PIP) install -e .
	@echo "Installation complete!"

# Install development dependencies
.PHONY: dev
dev: install
	@echo "Installing development dependencies..."
	$(PIP) install -e ".[lint]"
	@echo "Development setup complete!"

# Run the server
.PHONY: run
run:
	@echo "Starting Twilio Demo server..."
	$(PYTHON) main.py

# Clean up
.PHONY: clean
clean:
	@echo "Removing virtual environment..."
	rm -rf venv
	@echo "Cleanup complete!"

# Code formatting
.PHONY: format
format:
	@echo "Formatting code..."
	$(PYTHON) -m ruff check --select I --fix .
	$(PYTHON) -m ruff check .

# All code quality checks
.PHONY: check
check: format
	@echo "All checks completed!"
