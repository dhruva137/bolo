"""Bounded provider requests. Only replay a sent request when doing so is safe."""
import asyncio
import time

import httpx

TIMEOUT = httpx.Timeout(25, connect=5, pool=5)


def _retry_delay(error: httpx.HTTPError, replay_safe: bool) -> float | None:
    # Connect and pool failures happen before the request reaches the provider.
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return 0.25
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        if response.status_code != 429 and not (replay_safe and response.status_code in {408, 500, 502, 503, 504}):
            return None
        # When asked to wait longer than the demo can tolerate, let the caller fall back.
        delay = response.headers.get("Retry-After")
        if delay is None:
            return 0.25
        return float(delay) if delay.isdecimal() and len(delay) <= 2 and int(delay) <= 2 else None
    if replay_safe and isinstance(error, (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError)):
        return 0.25
    return None


async def request(client: httpx.AsyncClient, method: str, url: str, *, replay_safe: bool = False,
                  **kwargs) -> httpx.Response:
    """Try once and retry once if appropriate. Use byte-backed multipart uploads for replay."""
    kwargs.setdefault("timeout", TIMEOUT)
    try:
        return (await client.request(method, url, **kwargs)).raise_for_status()
    except httpx.HTTPError as error:
        delay = _retry_delay(error, replay_safe or method.upper() in {"GET", "HEAD"})
        if delay is None:
            raise
        await asyncio.sleep(delay)
    return (await client.request(method, url, **kwargs)).raise_for_status()


def inference_post(url: str, **kwargs) -> httpx.Response:
    """Synchronous counterpart for the existing JSON planner."""
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            return client.post(url, **kwargs).raise_for_status()
        except httpx.HTTPError as error:
            delay = _retry_delay(error, replay_safe=True)
            if delay is None:
                raise
            time.sleep(delay)
        return client.post(url, **kwargs).raise_for_status()
