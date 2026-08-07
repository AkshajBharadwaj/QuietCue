package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert
import com.quietcue.app.domain.CapturedFingerprint
import com.quietcue.app.domain.EnrollmentCapture
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.InferenceDevice
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.ProfileCatalog
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

class AlertRepository(
    private val stateUrl: String = "http://127.0.0.1:8787/api/state",
) {
    private val stopUrl: URL
        get() {
            val state = URL(stateUrl)
            return URL(state.protocol, state.host, state.port, "/api/haptics/stop")
        }

    suspend fun syncProfile(catalog: ProfileCatalog, memoryBank: MemoryBank = MemoryBank()) = withContext(Dispatchers.IO) {
        val document = ProfileSyncJsonCodec.encode(catalog, memoryBank).toByteArray(Charsets.UTF_8)
        val connection = URL(stateUrl).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "PUT"
            connection.connectTimeout = 1_000
            connection.readTimeout = 1_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setFixedLengthStreamingMode(document.size)
            connection.outputStream.use { it.write(document) }
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "Profile sync returned HTTP ${connection.responseCode}"
            }
            connection.inputStream.close()
        } finally {
            connection.disconnect()
        }
    }

    suspend fun fetchState(): RuntimeState = withContext(Dispatchers.IO) {
        val connection = URL(stateUrl).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 1_000
            connection.readTimeout = 1_000
            connection.setRequestProperty("Accept", "application/json")
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "QuietCue hub returned HTTP ${connection.responseCode}"
            }
            parseState(JSONObject(connection.inputStream.bufferedReader().use { it.readText() }))
        } finally {
            connection.disconnect()
        }
    }

    suspend fun stopHaptic(eventId: String) = withContext(Dispatchers.IO) {
        val document = JSONObject().put("event_id", eventId).toString().toByteArray(Charsets.UTF_8)
        val connection = stopUrl.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 1_000
            connection.readTimeout = 1_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setFixedLengthStreamingMode(document.size)
            connection.outputStream.use { it.write(document) }
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "Stop vibration returned HTTP ${connection.responseCode}"
            }
            connection.inputStream.close()
        } finally {
            connection.disconnect()
        }
    }

    suspend fun setInferenceDevice(device: InferenceDevice) = withContext(Dispatchers.IO) {
        requestJson(
            method = "POST",
            path = "/api/inference/device",
            document = JSONObject().put("device", device.wireValue),
        )
    }

    suspend fun captureEnrollmentSession(durationMs: Int = 10_000): EnrollmentCapture =
        withContext(Dispatchers.IO) {
            require(durationMs in 4_000..15_000)
            requestJson(
                method = "POST",
                path = "/api/enrollment/start",
                document = JSONObject().put("duration_ms", durationMs),
            )
            val deadlineMs = System.currentTimeMillis() + durationMs + 15_000L
            while (System.currentTimeMillis() < deadlineMs) {
                val status = requestJson("GET", "/api/enrollment/status")
                when (status.optString("state")) {
                    "complete" -> return@withContext parseEnrollmentCapture(status)
                    "error" -> error(status.optString("error", "Enrollment capture failed"))
                    "recording" -> delay(250)
                    else -> error("The QuietCue hub did not start enrollment")
                }
            }
            runCatching { requestJson("POST", "/api/enrollment/cancel") }
            error("No live Arduino microphone audio reached the enrollment session")
        }

    internal fun parseState(json: JSONObject): RuntimeState {
        val hub = json.optJSONObject("hub")
        val profile = json.optJSONObject("active_profile")
        val alertJson = json.optJSONObject("latest_alert")
        val inference = json.optJSONObject("inference")
        return RuntimeState(
            backendConnected = json.optString("status") == "ready",
            audioSourceConnected = hub?.optBoolean("audio_source_connected") == true,
            backendProfileName = profile?.optString("name")?.takeIf(String::isNotBlank),
            latestAlert = alertJson?.let(::parseAlert),
            requestedInferenceDevice = InferenceDevice.fromWire(
                inference?.optString("requested_device"),
            ),
            activeInferenceDevice = InferenceDevice.fromWire(
                inference?.optString("active_device"),
            ),
            samsungInferenceAvailable = inference?.optBoolean("samsung_available") == true,
            inferenceSwitchPending = inference?.optBoolean("switch_pending") == true,
            inferenceRoutingError = inference?.takeUnless { it.isNull("error") }
                ?.optString("error")
                ?.takeIf(String::isNotBlank),
        )
    }

    private fun parseAlert(json: JSONObject): DetectedAlert = DetectedAlert(
        eventId = json.optString("event_id"),
        event = json.optString("event", "unknown_event"),
        confidence = json.optDouble("confidence", 0.0).toFloat(),
        category = json.optString("category", "informational"),
        pattern = json.optString("pattern", "none"),
        profileName = json.optString("profile_name", "Unknown profile"),
        sourceLabel = json.optString("source_label"),
        totalLatencyMs = json.optInt("total_after_capture_ms", 0),
        requiresAcknowledgement = json.optBoolean("requires_ack", false),
        simulated = json.optBoolean("simulated", true),
        fallbackToPhone = json.optBoolean("fallback_to_phone", false),
        hapticActive = json.optBoolean("haptic_active", false),
        acknowledgedAtMs = json.optLong("acknowledged_at_ms").takeIf {
            !json.isNull("acknowledged_at_ms")
        },
    )

    private fun parseEnrollmentCapture(json: JSONObject): EnrollmentCapture {
        val positivesJson = json.optJSONArray("positives") ?: JSONArray()
        val positives = buildList {
            for (index in 0 until positivesJson.length()) {
                positivesJson.optJSONObject(index)?.let(::parseFingerprint)?.let(::add)
            }
        }
        val background = json.optJSONObject("background")?.let(::parseFingerprint)
            ?: error("The enrollment session did not capture background audio")
        return EnrollmentCapture(
            positives = positives,
            background = background,
            speechRejectedMs = json.optInt("speech_rejected_ms", 0),
        )
    }

    private fun parseFingerprint(json: JSONObject): CapturedFingerprint? {
        val featuresJson = json.optJSONArray("features") ?: return null
        if (featuresJson.length() != 8) return null
        return CapturedFingerprint(
            features = List(featuresJson.length()) { featuresJson.optDouble(it).toFloat() },
            rmsDbfs = json.optDouble("rms_dbfs", -180.0).toFloat(),
        )
    }

    private fun requestJson(
        method: String,
        path: String,
        document: JSONObject? = null,
    ): JSONObject {
        val state = URL(stateUrl)
        val endpoint = URL(state.protocol, state.host, state.port, path)
        val payload = document?.toString()?.toByteArray(Charsets.UTF_8)
        val connection = endpoint.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 1_000
            connection.readTimeout = 1_000
            connection.setRequestProperty("Accept", "application/json")
            if (payload != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.setFixedLengthStreamingMode(payload.size)
                connection.outputStream.use { it.write(payload) }
            }
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "QuietCue hub request returned HTTP ${connection.responseCode}"
            }
            return JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally {
            connection.disconnect()
        }
    }
}
