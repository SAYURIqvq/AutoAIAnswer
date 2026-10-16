from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys


_LAN_NETWORKS = (
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
)


def _is_lan_address(address: str) -> bool:
    try:
        return any(ipaddress.ip_address(address) in network for network in _LAN_NETWORKS)
    except ValueError:
        return False


def _mac_lan_ip() -> str | None:
    # Hostname and default route can both point at a VPN tunnel. Prefer the
    # physical Ethernet/Wi-Fi interfaces used by phones on the local network.
    if sys.platform != "darwin":
        return None
    interfaces = [name for _, name in socket.if_nameindex() if name.startswith("en")]
    for interface in sorted(interfaces, key=lambda name: (name != "en0", name)):
        try:
            result = subprocess.run(
                ["/sbin/ifconfig", interface], capture_output=True, text=True, timeout=2, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for address in re.findall(r"\binet (\d{1,3}(?:\.\d{1,3}){3})\b", result.stdout):
            if _is_lan_address(address):
                return address
    return None


def get_lan_ip() -> str:
    # Prefer a real RFC1918 LAN address from the host. A route-based lookup may
    # select a VPN/TUN adapter (for example Mihomo's 198.18.0.1), which phones
    # on the local network cannot reach.
    mac_address = _mac_lan_ip()
    if mac_address:
        return mac_address
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        for address in addresses:
            if _is_lan_address(address):
                return address
    except (OSError, ValueError):
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def first_available_port(preferred: int, host: str = "0.0.0.0") -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No available port starting at {preferred}")
