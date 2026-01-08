.DEFAULT_GOAL := help

.PHONY: install
install: ## Install the poetry environment and install the pre-commit hooks
	@echo "Creating virtual environment using pyenv and poetry"
	@poetry install
	@poetry run pre-commit install

.PHONY: check
check: ## Run code quality tools
	@echo "Checking Poetry lock file consistency with 'pyproject.toml': Running poetry check --lock"
	@poetry check --lock
	@echo "Linting code: Running pre-commit"
	@poetry run pre-commit run -a

.PHONY: test
test: ## Run unit tests
	@echo "Run unit tests"
	@poetry run pytest

.PHONY: clean
clean: ## Remove generated files
	@rm -fr build dist src/*.egg-info .tox
	@rm -fr .mypy_cache .ruff_cache .vscode
	@rm -f *.json *.png *.csv *.html
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@find src -regex '^.*\(__pycache__\|\.py[co]\)$$' -delete

.PHONY: config
config: ## Create config json file
	@cp config.example config.json

.PHONY: help
help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
