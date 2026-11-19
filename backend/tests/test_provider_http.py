"""Provider timeouts and retries with an in-memory HTTP transport."""
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from provider_http import request


class ProviderHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def fixture_request(self, codes, **kwargs):
        seen = []

        def serve(req):
            seen.append(req)
            status = codes[len(seen) - 1]
            return httpx.Response(status, headers={"Retry-After": "0"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            with patch("provider_http.asyncio.sleep", new_callable=AsyncMock):
                try:
                    await request(client, "POST", "https://test.invalid/", **kwargs)
                except httpx.HTTPStatusError:
                    pass
        self.assertTrue(all(0 < seconds <= 25 for req in seen for seconds in req.extensions["timeout"].values()))
        return len(seen)

    async def test_retry_inference_once(self):
        self.assertEqual(await self.fixture_request([503, 200], replay_safe=True), 2)
        self.assertEqual(await self.fixture_request([503, 503, 200], replay_safe=True), 2)

    async def test_never_replay_uncertain_side_effect(self):
        self.assertEqual(await self.fixture_request([503, 200]), 1)

    async def test_retry_explicit_rate_limit(self):
        self.assertEqual(await self.fixture_request([429, 200]), 2)

    async def test_no_retry_on_bad_credentials(self):
        self.assertEqual(await self.fixture_request([401, 200], replay_safe=True), 1)
