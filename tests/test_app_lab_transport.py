from __future__ import annotations

import subprocess
import sys
import unittest

from uno_q.linux.rpc_client import AppLabBridgeHapticTransport


_FAKE_WORKER = r"""
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    method = request["method"]
    if method == "health_check":
        result = '{"ok":true,"pattern":"none"}'
    elif method == "get_firmware_version":
        result = "quietcue-test/1.0"
    elif method == "get_button_state":
        result = False
    elif method == "echo":
        result = request["args"]
    else:
        result = True
    print(json.dumps({"ok": True, "result": result}), flush=True)
"""


def _local_process_factory(_: list[str], **kwargs: object) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-u", "-c", _FAKE_WORKER], **kwargs)


class AppLabBridgeHapticTransportTest(unittest.TestCase):
    def make_transport(self, **kwargs: object) -> AppLabBridgeHapticTransport:
        transport = AppLabBridgeHapticTransport(
            "quietcue-test",
            process_factory=_local_process_factory,
            **kwargs,
        )
        self.addCleanup(transport.close)
        return transport

    def test_bridge_arguments_are_json_safe_and_result_is_returned(self) -> None:
        transport = self.make_transport()

        result = transport._call("echo", "urgent_repeat", 255, 0)

        self.assertEqual(result, ["urgent_repeat", 255, 0])

    def test_health_json_is_decoded(self) -> None:
        transport = self.make_transport()

        self.assertTrue(transport.health_check())
        self.assertEqual(transport.firmware_version(), "quietcue-test/1.0")

    def test_worker_is_reused_across_calls(self) -> None:
        starts = 0

        def process_factory(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
            nonlocal starts
            starts += 1
            return _local_process_factory(command, **kwargs)

        transport = AppLabBridgeHapticTransport(
            "quietcue-test",
            process_factory=process_factory,
        )
        self.addCleanup(transport.close)

        self.assertFalse(transport.get_button_state())
        self.assertTrue(transport.play_haptic("two_short", 100, 1))
        self.assertTrue(transport.play_custom_haptic("300,100;500,200", 230, 1))
        self.assertEqual(starts, 1)

    def test_running_container_is_auto_detected(self) -> None:
        commands: list[list[str]] = []

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "quietcue-haptics-main-1\n", "")

        transport = AppLabBridgeHapticTransport(
            command_runner=run,
            process_factory=_local_process_factory,
        )
        self.addCleanup(transport.close)

        self.assertFalse(transport.get_button_state())
        self.assertEqual(commands[0][1], "ps")


if __name__ == "__main__":
    unittest.main()
