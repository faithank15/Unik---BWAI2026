"""Aides pour les tests du moteur de relances."""
from tests.aides import compter  # noqa: F401

D0 = "2026-12-15"


def planifier(api, h):
    r = api.post("/api/relances/planifier", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def envoyer(api, h):
    r = api.post("/api/relances/envoyer", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def relances(api, h, **filtres):
    q = "&".join(f"{k}={v}" for k, v in filtres.items())
    r = api.get(f"/api/relances?{q}&limite=200", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["elements"]


def detail(api, h, rid):
    r = api.get(f"/api/relances/{rid}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def relance_du_client(api, h, client, **filtres):
    liste = relances(api, h, client_id=client, **filtres)
    return detail(api, h, liste[0]["id"]) if liste else None


def changer_date(api, h, jour):
    r = api.post("/api/admin/date-reference", headers=h, json={"date": jour})
    assert r.status_code == 200, r.text


def ech_de(conn, facture_id):
    return [r[0] for r in conn.execute(
        "SELECT id FROM echeances WHERE facture_id = ? AND etat = 'ACTIVE' ORDER BY id",
        (facture_id,))]
