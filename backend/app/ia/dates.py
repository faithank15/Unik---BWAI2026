"""Résolveur de dates en code (document IA, option recommandée).

Le modèle renvoie la date ISO ; ce module recalcule la date des expressions standard avec la
convention du document de données, pour détecter un désaccord (motif DATE_DESACCORD) et mesurer
l'exactitude des dates séparément. Une expression vague (« la semaine prochaine », « après la
paie ») donne None : la date n'est pas assez précise.
"""
import re
from datetime import date, timedelta

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
VAGUES = re.compile(r"la semaine prochaine|après la paie|apres la paie|dès que possible|"
                    r"des que possible|très bientôt|tres bientot|quand j'aurai la trésorerie")


def _mois_suivant(d: date) -> tuple[int, int]:
    return (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)


def candidates(texte: str, reception: date) -> set[date]:
    """Toutes les dates que le texte exprime selon les règles standard."""
    t = texte.lower()
    trouvees: set[date] = set()
    if "aujourd'hui" in t:
        trouvees.add(reception)
    if re.search(r"\bdemain\b", t):
        trouvees.add(reception + timedelta(days=1))
    for m in re.finditer(r"dans (\d+) jours?", t):
        trouvees.add(reception + timedelta(days=int(m.group(1))))
    if re.search(r"lundi prochain|début de semaine prochaine|debut de semaine prochaine", t):
        trouvees.add(reception + timedelta(days=(7 - reception.weekday()) % 7 or 7))
    for m in re.finditer(r"\ble (\d{1,2})\b", t):
        n = int(m.group(1))
        if 1 <= n <= 28:
            d = reception.replace(day=n)
            if d < reception:
                y, mo = _mois_suivant(reception)
                d = date(y, mo, n)
            trouvees.add(d)
    if "fin du mois" in t:
        y, mo = _mois_suivant(reception)
        trouvees.add(date(y, mo, 1) - timedelta(days=1))
    sans = re.sub(r"lundi prochain", "", t)
    for i, j in enumerate(JOURS):
        if re.search(rf"\b{j}\b", sans):
            trouvees.add(reception + timedelta(days=(i - reception.weekday()) % 7 or 7))
    return trouvees


def resoudre_date(texte: str, reception: date) -> date | None:
    """Date promise, ou None si le texte n'en donne pas une seule et précise."""
    if VAGUES.search(texte.lower()):
        return None
    c = candidates(texte, reception)
    return next(iter(c)) if len(c) == 1 else None
