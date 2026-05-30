from __future__ import annotations

import uvicorn

from arranger.config import load_settings

settings = load_settings()
uvicorn.run("arranger.main:app", host=settings.app.bind_host, port=settings.app.bind_port)
