from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys


_PRIVATE_NETWORKS = (
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
)
_SKIP_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),  # Clash/Mihomo fake-ip
    ipaddress.ip_network("100.64.0.0/10"),
)


def _usable_private_ipv4(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    if parsed.version != 4:
        return False
    if any(parsed in network for network in _SKIP_NETWORKS):
        return False
    return any(parsed in network for network in _PRIVATE_NETWORKS)


def _unique(addresses: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for address in addresses:
        if address in seen:
            continue
        seen.add(address)
        unique.append(address)
    return unique


def _hostname_ipv4() -> list[str]:
    try:
        return list(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        return []


def _route_ipv4() -> list[str]:
    found: list[str] = []
    for probe in ("8.8.8.8", "1.1.1.1", "223.5.5.5"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((probe, 80))
            found.append(sock.getsockname()[0])
        except OSError:
            continue
        finally:
            sock.close()
    return found


def _os_ipv4() -> list[str]:
    kwargs: dict[str, object] = {
        "text": True,
        "timeout": 2,
        "stderr": subprocess.DEVNULL,
        "errors": "ignore",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = ["ipconfig"]
        pattern = r"(\d+\.\d+\.\d+\.\d+)"
    elif sys.platform == "darwin":
        command = ["/sbin/ifconfig", "-a"]
        pattern = r"\binet (\d+\.\d+\.\d+\.\d+)\b"
    else:
        command = ["/sbin/ip", "-4", "-o", "addr"]
        pattern = r"inet (\d+\.\d+\.\d+\.\d+)"
    try:
        output = subprocess.check_output(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(pattern, str(output))


def candidate_ipv4() -> list[str]:
    return _unique([*_hostname_ipv4(), *_os_ipv4(), *_route_ipv4()])


def prefer_lan_ip(addresses: list[str]) -> str:
    usable = [address for address in addresses if _usable_private_ipv4(address)]
    for network in _PRIVATE_NETWORKS:
        for address in usable:
            if ipaddress.ip_address(address) in network:
                return address
    return "127.0.0.1"


def get_lan_ip() -> str:
    # Prefer a real RFC1918 LAN address. Route lookup may select a VPN/TUN
    # adapter (for example Mihomo's 198.18.0.1), which phones cannot reach.
    return prefer_lan_ip(candidate_ipv4())


def first_available_port(preferred: int, host: str = "0.0.0.0") -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No available port starting at {preferred}")
