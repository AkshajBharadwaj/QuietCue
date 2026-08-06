package com.quietcue.app.phone

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import org.json.JSONObject

data class QuietCueWireMessage(
    val kind: String,
    val body: JSONObject,
    val payload: ByteArray = byteArrayOf(),
)

object QuietCueWireProtocol {
    private val magic = byteArrayOf('Q'.code.toByte(), 'C'.code.toByte(), '0'.code.toByte(), '1'.code.toByte())
    const val MAX_JSON_BYTES = 64 * 1024
    const val MAX_PAYLOAD_BYTES = 1024 * 1024

    @Throws(IOException::class)
    fun read(input: DataInputStream): QuietCueWireMessage {
        val receivedMagic = ByteArray(4)
        input.readFully(receivedMagic)
        if (!receivedMagic.contentEquals(magic)) throw IOException("Unrecognized QuietCue protocol magic")
        val jsonLength = input.readInt()
        val payloadLength = input.readInt()
        if (jsonLength !in 2..MAX_JSON_BYTES) throw IOException("Invalid JSON length: $jsonLength")
        if (payloadLength !in 0..MAX_PAYLOAD_BYTES) throw IOException("Invalid payload length: $payloadLength")

        val jsonBytes = ByteArray(jsonLength)
        val payload = ByteArray(payloadLength)
        input.readFully(jsonBytes)
        input.readFully(payload)
        val document = try {
            JSONObject(jsonBytes.toString(Charsets.UTF_8))
        } catch (error: RuntimeException) {
            throw IOException("Message JSON is invalid", error)
        }
        val kind = document.optString("kind")
        val body = document.optJSONObject("body")
        if (kind.isBlank() || body == null) throw IOException("Message requires kind and object body")
        return QuietCueWireMessage(kind, body, payload)
    }

    @Throws(IOException::class)
    fun write(output: DataOutputStream, message: QuietCueWireMessage) {
        require(message.kind.isNotBlank()) { "Message kind cannot be empty" }
        val jsonBytes = JSONObject()
            .put("kind", message.kind)
            .put("body", message.body)
            .toString()
            .toByteArray(Charsets.UTF_8)
        require(jsonBytes.size <= MAX_JSON_BYTES) { "Message JSON is too large" }
        require(message.payload.size <= MAX_PAYLOAD_BYTES) { "Message payload is too large" }
        output.write(magic)
        output.writeInt(jsonBytes.size)
        output.writeInt(message.payload.size)
        output.write(jsonBytes)
        output.write(message.payload)
        output.flush()
    }

    fun isCleanDisconnect(error: Throwable): Boolean = error is EOFException
}
