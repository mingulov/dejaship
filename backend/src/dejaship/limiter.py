import ipaddress

from fastapi import Request
from slowapi import Limiter

from dejaship.config import settings


def _is_trusted_proxy(host: str | None) -> bool:
    if not host or not settings.TRUST_PROXY_HEADERS:
        return False

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    cidrs = [cidr.strip() for cidr in settings.TRUSTED_PROXY_CIDRS.split(",") if cidr.strip()]
    return any(address in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def get_client_ip(request: Request) -> str:
    """Extract client IP with optional trusted proxy support.

    Proxy headers are only honored when the immediate peer is trusted.
    """
    peer_host = request.client.host if request.client else None

    if _is_trusted_proxy(peer_host):
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return peer_host or "testclient"


limiter = Limiter(key_func=get_client_ip)
