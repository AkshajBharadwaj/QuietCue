package com.quietcue.app.phone

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class QuietCueWireProtocolTest {
    @Test
    fun roundTripPreservesBinaryPcm() {
        val output = ByteArrayOutputStream()
        val expected = QuietCueWireMessage(
            "audio_chunk",
            JSONObject().put("sequence", 7).put("encoding", "pcm_s16le"),
            byteArrayOf(0, 1, -1, 42),
        )

        QuietCueWireProtocol.write(DataOutputStream(output), expected)
        val decoded = QuietCueWireProtocol.read(DataInputStream(ByteArrayInputStream(output.toByteArray())))

        assertEquals(expected.kind, decoded.kind)
        assertEquals(7, decoded.body.getInt("sequence"))
        assertArrayEquals(expected.payload, decoded.payload)
    }
}
