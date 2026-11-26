"""Commandes en ligne : `python -m app.cli reset`."""
import argparse
import sys

from app.config import charger_reglages
from app.errors import ErreurMetier
from app.services.reset import reinitialiser


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.cli")
    ap.add_argument("commande", choices=["reset"])
    ap.add_argument("--vide", action="store_true", help="ne charge pas le jeu de données")
    a = ap.parse_args(argv)
    try:
        if a.commande == "reset":
            res = reinitialiser(charger_reglages(), charger=not a.vide)
            print(f"Base réinitialisée : {res['base']}")
    except ErreurMetier as e:
        print(f"Erreur : {e.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
