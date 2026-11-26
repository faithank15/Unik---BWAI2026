import socket

import pytest

from tests.conftest import ReseauInterdit


def test_A7_les_connexions_sortantes_echouent():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(ReseauInterdit):
        s.connect(("93.184.216.34", 80))
    s.close()


def test_httpx_ne_sort_pas():
    import httpx
    with pytest.raises(Exception) as e:
        httpx.get("http://example.com", timeout=1)
    assert "réseau" in str(e.value).lower() or "ReseauInterdit" in repr(e.value)
