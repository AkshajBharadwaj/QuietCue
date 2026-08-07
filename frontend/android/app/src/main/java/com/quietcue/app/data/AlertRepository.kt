package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.ProfileCatalog
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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

    internal fun parseState(json: JSONObject): RuntimeState {
        val hub = json.optJSONObject("hub")
        val profile = json.optJSONObject("active_profile")
        val alertJson = json.optJSONObject("latest_alert")
        return RuntimeState(
            backendConnected = json.optString("status") == "ready",
            audioSourceConnected = hub?.optBoolean("audio_source_connected") == true,
            backendProfileName = profile?.optString("name")?.takeIf(String::isNotBlank),
            latestAlert = alertJson?.let(::parseAlert),
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
}
