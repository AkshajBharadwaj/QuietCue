from __future__ import annotations

import unittest

from backend.communication.stream_protocol import ProtocolError, WireMessage, decode_message, encode_message


class StreamProtocolTest(unittest.TestCase):
    def test_round_trip_preserves_binary_payload(self) -> None:
        original = WireMessage("audio_chunk", {"sequence": 7}, b"\x00\x01\xff")

        self.assertEqual(decode_message(encode_message(original)), original)

    def test_rejects_invalid_magic(self) -> None:
        frame = bytearray(encode_message(WireMessage("heartbeat", {})))
        frame[:4] = b"NOPE"

        with self.assertRaises(ProtocolError):
            decode_message(bytes(frame))
