package com.quietcue.app.phone

import java.io.Closeable
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import java.net.ServerSocket
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketException
import java.net.SocketTimeoutException
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONArray
import org.json.JSONObject

class PhoneInferenceServer(
    private val classifier: PhoneSoundClassifier,
    profileProvider: () -> com.quietcue.app.domain.AlertProfile,
    private val pairingToken: String = "",
    private val port: Int = DEFAULT_PORT,
) : Closeable {
    private val running = AtomicBoolean(false)
    private val inference = PhoneInferenceEngine(classifier)
    private val decisions = PhoneProfileDecisionEngine(profileProvider)
    @Volatile private var socket: ServerSocket? = null

    fun serveForever() {
        check(running.compareAndSet(false, true)) { "Phone inference server is already running" }
        try {
            ServerSocket().use { server ->
                socket = server
                server.reuseAddress = true
                server.bind(InetSocketAddress(port))
                server.soTimeout = 1_000
                PhoneInferenceStatus.update {
                    it.copy(running = true, modelReady = true, provider = classifier.provider, error = null)
                }
                while (running.get()) {
                    try {
                        server.accept().use(::handleClient)
                    } catch (_: SocketTimeoutException) {
                        // Recheck the running flag.
                    } catch (error: SocketException) {
                        if (running.get()) throw error
                    }
                }
            }
        } finally {
            socket = null
            running.set(false)
            PhoneInferenceStatus.update { it.copy(running = false, clientConnected = false) }
        }
    }

    private fun handleClient(client: Socket) {
        client.tcpNoDelay = true
        client.soTimeout = 30_000
        inference.reset()
        val input = DataInputStream(client.getInputStream().buffered())
        val output = DataOutputStream(client.getOutputStream().buffered())
        try {
            val hello = QuietCueWireProtocol.read(input)
            if (hello.kind != "edge_hello") throw IOException("First message must be edge_hello")
            val suppliedToken = hello.body.optString("pairing_token")
            if (pairingToken.isNotEmpty() && suppliedToken != pairingToken) {
                QuietCueWireProtocol.write(
                    output,
                    QuietCueWireMessage(
                        "error",
                        JSONObject().put("code", "pairing_failed").put("message", "Invalid pairing token"),
                    ),
                )
                return
            }
            QuietCueWireProtocol.write(
                output,
                QuietCueWireMessage(
                    "hub_hello",
                    JSONObject()
                        .put("node_id", "quietcue-samsung-hub")
                        .put("kind", "samsung_phone")
                        .put("protocol", 1)
                        .put(
                            "capabilities",
                            JSONArray().put("sound_confirmation").put("phone_onnx_inference"),
                        ),
                ),
            )
            PhoneInferenceStatus.update { it.copy(clientConnected = true, error = null) }

            while (running.get()) {
                val message = QuietCueWireProtocol.read(input)
                when (message.kind) {
                    "audio_chunk" -> QuietCueWireProtocol.write(output, processAudio(message))
                    "heartbeat" -> QuietCueWireProtocol.write(
                        output,
                        QuietCueWireMessage("heartbeat_ack", message.body),
                    )
                    "haptic_result" -> Unit
                    else -> throw IOException("Unsupported message kind: ${message.kind}")
                }
            }
        } catch (_: EOFException) {
            // Probe connections and normal clients close without a final frame.
        } catch (error: IOException) {
            if (running.get()) {
                PhoneInferenceStatus.update { it.copy(error = error.message ?: "Connection failed") }
            }
        } catch (error: IllegalArgumentException) {
            PhoneInferenceStatus.update { it.copy(error = error.message ?: "Invalid audio message") }
            runCatching {
                QuietCueWireProtocol.write(
                    output,
                    QuietCueWireMessage(
                        "error",
                        JSONObject().put("code", "invalid_message").put("message", error.message),
                    ),
                )
            }
        } finally {
            PhoneInferenceStatus.update { it.copy(clientConnected = false) }
        }
    }

    private fun processAudio(message: QuietCueWireMessage): QuietCueWireMessage {
        val body = message.body
        require(body.optInt("sample_rate") == YamnetFeatureExtractor.SAMPLE_RATE) {
            "Phone inference requires 16000 Hz audio"
        }
        require(body.optInt("channels") == 1 && body.optString("encoding") == "pcm_s16le") {
            "Phone inference requires mono pcm_s16le"
        }
        val sequence = body.optInt("sequence", -1)
        val capturedAtMs = body.optLong("captured_at_ms", -1)
        require(sequence >= 0 && capturedAtMs > 0) { "Invalid audio sequence metadata" }

        val totalStarted = System.nanoTime()
        val result = inference.process(message.payload)
        val decision = decisions.decide(result.events, capturedAtMs, sequence)
        val edge = body.optJSONObject("edge_analysis")
        val voiceDetected = edge?.optBoolean("voice_activity") == true || result.speechConfidence >= 0.10
        val events = JSONArray().apply {
            result.events.forEach { event ->
                put(
                    JSONObject()
                        .put("event", event.event)
                        .put("confidence", event.confidence)
                        .put("source_label", event.sourceLabel)
                        .put("category", event.category)
                        .put("pattern", event.pattern)
                        .put("requires_ack", event.requiresAck),
                )
            }
        }
        val predictions = JSONArray().apply {
            result.predictions.forEach { prediction ->
                put(JSONObject().put("label", prediction.label).put("confidence", prediction.confidence))
            }
        }
        val totalMs = (System.nanoTime() - totalStarted) / 1_000_000.0
        val response = JSONObject()
            .put("sequence", sequence)
            .put("events", events)
            .put("voice_detected", voiceDetected)
            .put("speech_confidence", result.speechConfidence)
            .put("transcript", JSONObject.NULL)
            .put("speech_pending", false)
            .put("speech_inference_ms", JSONObject.NULL)
            .put("speech_error", JSONObject.NULL)
            .put("inference_pending", result.pending)
            .put("inference_ms", result.inferenceMs)
            .put("total_ms", totalMs)
            .put("top_predictions", predictions)
            .put("inference_source", if (result.pending) "samsung_buffering" else "samsung_onnx_cpu")
            .put("alerts", decision.alerts)
            .put("suppressed", decision.suppressed)

        val latestEvent = result.events.firstOrNull()?.event
        PhoneInferenceStatus.update {
            it.copy(
                lastEvent = latestEvent ?: it.lastEvent,
                inferenceMs = if (result.pending) it.inferenceMs else result.inferenceMs,
                error = null,
            )
        }
        return QuietCueWireMessage("detection_result", response)
    }

    override fun close() {
        running.set(false)
        socket?.close()
    }

    companion object {
        const val DEFAULT_PORT = 8765
    }
}
