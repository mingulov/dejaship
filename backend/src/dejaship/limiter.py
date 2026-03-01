from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    """Extract real client IP, Cloudflare-aware.

    Cloudflare Tunnel sets CF-Connecting-IP to the true client IP.
    Falls back to X-Forwarded-For, then direct connection, then 'testclient'.
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "testclient"


limiter = Limiter(key_func=get_client_ip)
