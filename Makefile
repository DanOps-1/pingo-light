PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
COMPLETIONS_DIR_BASH ?= $(PREFIX)/share/bash-completion/completions
COMPLETIONS_DIR_ZSH ?= $(PREFIX)/share/zsh/site-functions
COMPLETIONS_DIR_FISH ?= $(PREFIX)/share/fish/vendor_completions.d

.PHONY: install uninstall test lint completions help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install bingo-light to $(BINDIR)
	@install -d $(DESTDIR)$(BINDIR)
	@install -m 755 bingo-light $(DESTDIR)$(BINDIR)/bingo-light
	@echo "Installed to $(DESTDIR)$(BINDIR)/bingo-light"

uninstall: ## Remove bingo-light from $(BINDIR)
	@rm -f $(DESTDIR)$(BINDIR)/bingo-light
	@echo "Removed $(DESTDIR)$(BINDIR)/bingo-light"

completions: ## Install shell completions (bash, zsh, fish)
	@install -d $(DESTDIR)$(COMPLETIONS_DIR_BASH) 2>/dev/null && \
		install -m 644 completions/bingo-light.bash $(DESTDIR)$(COMPLETIONS_DIR_BASH)/bingo-light && \
		echo "Installed bash completions" || true
	@install -d $(DESTDIR)$(COMPLETIONS_DIR_ZSH) 2>/dev/null && \
		install -m 644 completions/bingo-light.zsh $(DESTDIR)$(COMPLETIONS_DIR_ZSH)/_bingo-light && \
		echo "Installed zsh completions" || true
	@install -d $(DESTDIR)$(COMPLETIONS_DIR_FISH) 2>/dev/null && \
		install -m 644 completions/bingo-light.fish $(DESTDIR)$(COMPLETIONS_DIR_FISH)/bingo-light.fish && \
		echo "Installed fish completions" || true

test: ## Run test suite
	@./tests/test.sh

lint: ## Run shellcheck (if installed)
	@command -v shellcheck >/dev/null 2>&1 && shellcheck bingo-light || echo "shellcheck not found, skipping"
