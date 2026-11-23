"""¿La petición viene directamente de esta máquina? (asistente de setup y documentación).

No basta con `request.client.host`: detrás de un proxy inverso todas las peticiones parecen
locales. Por eso se rechaza cualquier petición con cabeceras de proxy o con un `Host` que no sea
localhost/127.0.0.1. Además, uvicorn se arranca con `--no-proxy-headers`.
"""

from fastapi import Request

LOCAL_HOSTS = frozenset({"127.0.0.1", "::1"})
LOCAL_HOST_HEADERS = frozenset({"localhost", "127.0.0.1", "[::1]", "::1"})
PROXY_HEADERS = ("forwarded", "x-real-ip")


def is_local_request(request: Request) -> bool:
    host = request.client.host if request.client else None
    if host not in LOCAL_HOSTS:
        return False
    headers = request.headers
    if any(h in headers for h in PROXY_HEADERS) or any(
        k.startswith("x-forwarded-") for k in headers
    ):
        return False
    authority = headers.get("host", "")
    hostname = authority if authority.endswith("]") else authority.rsplit(":", 1)[0]
    return hostname.lower() in LOCAL_HOST_HEADERS
