"""The web server listens on all interfaces when WEBSERVER_IP is automatic or not this machine's (#1390, #1576)."""
import logging

import netifaces
import pytest

import arm.config.config as cfg
from arm import runui

LAN_IP = "192.0.2.10"  # TEST-NET-1 (RFC 5737)
OTHER_IP = "198.51.100.7"  # TEST-NET-2, not one of ours


@pytest.fixture
def interfaces(monkeypatch):
    """Pretend this machine has a loopback interface and, unless cleared, one LAN address."""
    addresses = {"lo": {netifaces.AF_INET: [{"addr": "127.0.0.1"}]},
                 "eth0": {netifaces.AF_INET: [{"addr": LAN_IP}],
                          netifaces.AF_INET6: [{"addr": "fe80::1%eth0"}]}}
    monkeypatch.setattr(netifaces, "interfaces", lambda: list(addresses))
    monkeypatch.setattr(netifaces, "ifaddresses", lambda name: addresses[name])
    monkeypatch.setattr(runui, "is_docker", lambda: False)
    return addresses


def _host(monkeypatch, value):
    monkeypatch.setitem(cfg.arm_config, "WEBSERVER_IP", value)
    return runui.get_host()


def test_auto_listens_on_all_interfaces(monkeypatch, interfaces):
    assert _host(monkeypatch, "x.x.x.x") == "0.0.0.0"


def test_auto_before_the_network_is_up_does_not_pick_loopback(monkeypatch, interfaces):
    del interfaces["eth0"]
    assert _host(monkeypatch, "x.x.x.x") == "0.0.0.0"


def test_docker_listens_on_all_interfaces(monkeypatch, interfaces):
    monkeypatch.setattr(runui, "is_docker", lambda: True)
    assert _host(monkeypatch, LAN_IP) == "0.0.0.0"


def test_local_address_is_used(monkeypatch, interfaces):
    assert _host(monkeypatch, LAN_IP) == LAN_IP


def test_address_of_another_machine_falls_back_with_an_error(monkeypatch, interfaces, caplog):
    with caplog.at_level(logging.ERROR):
        assert _host(monkeypatch, OTHER_IP) == "0.0.0.0"
    assert f"WEBSERVER_IP '{OTHER_IP}' is not an address of this machine" in caplog.text
