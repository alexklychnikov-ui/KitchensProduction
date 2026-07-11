from __future__ import annotations

import uvicorn

from .app import create_app
from .config import load_admin_settings


def main() -> None:
    settings = load_admin_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
