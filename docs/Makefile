# Makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD  ?= sphinx-build
SOURCEDIR    = .
BUILDDIR     = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Custom targets for common operations

clean:
	@echo "Removing everything under '$(BUILDDIR)'..."
	@rm -rf $(BUILDDIR)

html-fast:
	@echo "Building HTML documentation (fast mode)..."
	@$(SPHINXBUILD) -b html -W --keep-going $(SOURCEDIR) $(BUILDDIR)/html

html-strict:
	@echo "Building HTML documentation (strict mode)..."
	@$(SPHINXBUILD) -b html -W -E -a $(SOURCEDIR) $(BUILDDIR)/html

serve:
	@echo "Starting documentation server at http://localhost:8000"
	@cd $(BUILDDIR)/html && python -m http.server 8000

live: html-fast
	@echo "Building and serving documentation..."
	@cd $(BUILDDIR)/html && python -m http.server 8000

linkcheck:
	@echo "Checking external links..."
	@$(SPHINXBUILD) -b linkcheck $(SOURCEDIR) $(BUILDDIR)/linkcheck

coverage:
	@echo "Checking documentation coverage..."
	@$(SPHINXBUILD) -b coverage $(SOURCEDIR) $(BUILDDIR)/coverage
	@echo "Coverage report available at $(BUILDDIR)/coverage/python.txt"