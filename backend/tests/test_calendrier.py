from datetime import date

from app.domain.calendrier import est_jour_ouvre, nom_jour, prochain_jour_ouvre

FERIES = {date(2026, 12, 25), date(2027, 1, 1)}


def test_K01_dimanche_non_ouvre():
    assert not est_jour_ouvre(date(2026, 12, 20), FERIES)


def test_K02_samedi_ouvre():
    assert est_jour_ouvre(date(2026, 12, 19), FERIES)


def test_K03_jour_ferie_non_ouvre():
    assert not est_jour_ouvre(date(2026, 12, 25), set(FERIES))


def test_K04_report_au_prochain_jour_ouvre():
    assert prochain_jour_ouvre(date(2026, 12, 20), FERIES) == date(2026, 12, 21)


def test_ouvre_se_retourne_lui_meme():
    assert prochain_jour_ouvre(date(2026, 12, 15), FERIES) == date(2026, 12, 15)


def test_K06_fin_d_annee():
    assert prochain_jour_ouvre(date(2026, 12, 25), FERIES) == date(2026, 12, 26)
    assert prochain_jour_ouvre(date(2027, 1, 1), FERIES) == date(2027, 1, 2)


def test_ferie_suivi_d_un_dimanche():
    assert prochain_jour_ouvre(date(2027, 1, 10), {date(2027, 1, 10)}) == date(2027, 1, 11)


def test_nom_jour():
    assert nom_jour(date(2026, 12, 15)) == "mardi"
