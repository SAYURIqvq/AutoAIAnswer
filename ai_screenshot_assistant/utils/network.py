from __future__ import annotations

import ipaddress
import socket


def get_lan_ip() -> str:
    # Prefer a real RFC1918 LAN address from the host. A route-based lookup may
    # select a VPN/TUN adapter (for example Mihomo's 198.18.0.1), which phones
    # on the local network cannot reach.
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        private_networks = (
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
        )
        for network in private_networks:
            for address in addresses:
                if ipaddress.ip_address(address) in network:
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
