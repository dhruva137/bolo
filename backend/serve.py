"""Run Bolo on three ports from one process so every door shares the same agent and database.

    python serve.py            # 8000 landing + dashboard + API, 8001 customer chat, 8002 business portal
Env: BOLO_HOST (default 127.0.0.1; Docker uses 0.0.0.0), BOLO_SITE_PORT, BOLO_CUSTOMER_PORT, BOLO_BUSINESS_PORT.
"""
import asyncio
import os

import uvicorn

import config
from app import app


async def main() -> None:
    host = os.environ.get("BOLO_HOST", "127.0.0.1")
    ports = (config.SITE_PORT, config.CUSTOMER_PORT, config.BUSINESS_PORT)
    # Only the first server runs the app's startup/shutdown (scheduler); the others share it.
    servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=p, lifespan="on" if i == 0 else "off", log_level="info"))
               for i, p in enumerate(ports)]
    print(f"Bolo: landing http://localhost:{ports[0]}  customer http://localhost:{ports[1]}  business http://localhost:{ports[2]}")
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
