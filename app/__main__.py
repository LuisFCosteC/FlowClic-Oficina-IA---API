"""`python -m app`: arranca la API con el HOST y PORT del entorno (por defecto 127.0.0.1:4000)."""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    # Sin cabeceras de proxy (el asistente de setup no puede fiarse de X-Forwarded-For) ni
    # cabecera `server:` (S01 #10).
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
