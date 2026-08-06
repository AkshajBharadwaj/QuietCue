from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from uno_q.linux.transport.hub_client import (
    Endpoint,
    NoHubAvailable,
    run_microphone_client,
)
from uno_q.linux.transport.hub_selector import HubKind, RoutingPreference


class HubClientReconnectTest(unittest.IsolatedAsyncioTestCase):
    @patch("uno_q.linux.transport.hub_client.asyncio.sleep", new_callable=AsyncMock)
    @patch("uno_q.linux.transport.hub_client.stream_microphone", new_callable=AsyncMock)
    async def test_live_client_retries_after_hub_unavailable(
        self,
        stream_microphone: AsyncMock,
        sleep: AsyncMock,
    ) -> None:
        stream_microphone.side_effect = [NoHubAvailable("offline"), None]

        await run_microphone_client(
            "test-device",
            [Endpoint("pc", HubKind.COPILOT_PC, "127.0.0.1", 8765)],
            RoutingPreference.AUTO,
            "uno-test",
            "token",
            [],
            500,
            None,
            True,
            None,
            reconnect=True,
        )

        self.assertEqual(stream_microphone.await_count, 2)
        sleep.assert_awaited_once_with(1.0)

    @patch("uno_q.linux.transport.hub_client.stream_microphone", new_callable=AsyncMock)
    async def test_no_reconnect_propagates_failure(self, stream_microphone: AsyncMock) -> None:
        stream_microphone.side_effect = NoHubAvailable("offline")

        with self.assertRaises(NoHubAvailable):
            await run_microphone_client(
                "test-device",
                [Endpoint("pc", HubKind.COPILOT_PC, "127.0.0.1", 8765)],
                RoutingPreference.AUTO,
                "uno-test",
                "token",
                [],
                500,
                None,
                True,
                None,
                reconnect=False,
            )


if __name__ == "__main__":
    unittest.main()
