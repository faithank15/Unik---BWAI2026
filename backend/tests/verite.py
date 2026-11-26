"""Lecture de la vérité terrain du jeu de données (jamais modifiée pour faire passer un test)."""
import csv
import json
from pathlib import Path

DATASET = Path(__file__).resolve().parent.parent / "dataset"


def lire_csv(rel: str) -> list[dict[str, str]]:
    with (DATASET / rel).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def lire_scenario(code: str) -> dict:
    return json.loads((DATASET / "verite_terrain" / "scenarios" / f"{code}.json")
                      .read_text(encoding="utf-8"))


def signaler(ecarts: list[str], nb_compares: int, titre: str) -> None:
    """Échoue avec la liste des objets en écart (identifiant, attendu, obtenu)."""
    assert not ecarts, (f"{titre} : {len(ecarts)} écart(s) sur {nb_compares} objets comparés\n"
                        + "\n".join(ecarts[:25]))
