# Passerelle vers le back-end : `make test` à la racine équivaut à `make -C backend test`.
# Le futur front-end vivra dans frontend/ avec son propre Makefile ou ses scripts npm.
CIBLES := install run test test-rapide cov lint reset dataset openapi rapport eval-ia eval-ia-test

.PHONY: $(CIBLES)

$(CIBLES):
	$(MAKE) -C backend $@
