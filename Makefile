# --- Variables ---

ENV_FILE=.env
SRC_INIT=src/pbix_atlas/__init__.py

# --- Feature ---

coverage: ## prod-level > 95%
	uv run pytest --cov=src --cov-report=term-missing


mapper: ## Export project structure to JSON
	uv run python3 mapper.py --to-json

codegen: ## Generate a standalone Python pipeline from a .pbix (usage: make codegen FILE=my_report.pbix)
	uv run pbix-atlas-codegen $(FILE) -o $(basename $(FILE))_pipeline.py

format:
	uv run ruff format .

##@ Release

bump-patch: ## Bump patch version (0.2.0 → 0.2.1) in all files
	uv version --bump patch

bump-minor: ## Bump minor version (0.2.0 → 0.3.0)
	uv version --bump minor

bump-major: ## Bump major version (0.2.0 → 1.0.0)
	uv version --bump major

build: ## Build package for PyPI
	uv build

publish: build ## Publish to PyPI (requires UV_PUBLISH_USERNAME/PASSWORD in .env)
	uv publish

mcp-login: ## Login to MCP registry via GitHub
	mcp-publisher login github

mcp-publish: ## Publish to MCP registry (dry-run first, then real)
	mcp-publisher publish --dry-run

release: publish mcp-login mcp-publish ## Full release: build → PyPI → MCP (bump first: make bump-patch)

##@ Maintenance
clean: ## Remove python caches and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .venv .ruff_cache .mypy_cache
	@# Remove legacy VS Code Snap environment injections that break devpod/devbox sessions
	-sed -i '/snap\/code/d' ~/.profile ~/.bashrc ~/.bash_aliases 2>/dev/null


#  Automatically collect all targets with descriptions for .PHONY
ALL_TARGETS := $(shell grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | cut -d: -f1)

.PHONY: $(ALL_TARGETS)
