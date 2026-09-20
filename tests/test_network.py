from ai_screenshot_assistant.utils.network import prefer_lan_ip


def test_prefer_lan_ip_skips_vpn_fake_ip() -> None:
    assert prefer_lan_ip(["198.18.0.1", "192.168.1.8"]) == "192.168.1.8"


def test_prefer_lan_ip_ranks_home_lan_first() -> None:
    assert prefer_lan_ip(["10.0.0.2", "192.168.0.12", "172.16.1.4"]) == "192.168.0.12"


def test_prefer_lan_ip_ignores_link_local_and_loopback() -> None:
    assert prefer_lan_ip(["127.0.0.1", "169.254.12.3", "10.8.0.2"]) == "10.8.0.2"


def test_prefer_lan_ip_falls_back_when_only_unusable() -> None:
    assert prefer_lan_ip(["198.18.0.1", "127.0.0.1"]) == "127.0.0.1"
