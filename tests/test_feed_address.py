"""Calendar addresses: only HTTPS, never into the home network (as the app's feedUrl)."""

import ipaddress

import pytest

from custom_components.orgaia.protocol.ics import feed_url, is_private_host, is_private_ip


def test_https_only() -> None:
    assert feed_url("webcal://example.org/abfall.ics") == "https://example.org/abfall.ics"
    assert feed_url("http://schule.example.org/plan.ics") == "https://schule.example.org/plan.ics"
    assert feed_url("kein link") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1/x.ics",
        "https://10.0.0.5/a",
        "https://127.0.0.1/a",
        "https://localhost/a",
        "https://homeassistant.local/a",
        "https://[::1]/a",
        "https://[fd00::1]/a",
        "https://169.254.169.254/latest",
        "https://172.20.0.1/a",
        "https://fritz.box/a",
        "https://nas.fritz.box/a",
        "https://100.64.0.1/a",
    ],
)
def test_home_network_refused(url: str) -> None:
    assert feed_url(url) is None


def test_public_addresses() -> None:
    assert feed_url("https://172.32.0.1/a") == "https://172.32.0.1/a"
    assert not is_private_host("calendar.google.com")
    assert is_private_ip(ipaddress.ip_address("::ffff:192.168.0.1"))
    assert not is_private_ip(ipaddress.ip_address("93.184.216.34"))
