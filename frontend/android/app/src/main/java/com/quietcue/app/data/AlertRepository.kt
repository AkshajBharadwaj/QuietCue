package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.SoundDiscoveryCandidate
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

class AlertRepository(
    private val stateUrl: String = "http://127.0.0.1:8787/api/state",
) {
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

    suspend fun updateDiscovery(candidateId: String, action: String) = withContext(Dispatchers.IO) {
        require(action == "dismiss" || action == "taught") { "Unsupported discovery action" }
        val encodedId = URLEncoder.encode(candidateId, Charsets.UTF_8.name())
        val state = URL(stateUrl)
        val endpoint = URL(state.protocol, state.host, state.port, "/api/discoveries/$encodedId")
        val document = JSONObject().put("action", action).toString().toByteArray(Charsets.UTF_8)
        val connection = endpoint.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 1_000
            connection.readTimeout = 1_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setFixedLengthStreamingMode(document.size)
            connection.outputStream.use { it.write(document) }
            check(connection.responseCode == HttpURLConnection.HTTP_OK) {
                "Discovery action returned HTTP ${connection.responseCode}"
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
        val discoveryJson = json.optJSONObject("discoveries")
        val candidateJson = discoveryJson?.optJSONArray("candidates")
        val discoveries = buildList {
            if (candidateJson != null) {
                repeat(candidateJson.length()) { index ->
                    candidateJson.optJSONObject(index)?.let { add(parseDiscovery(it)) }
                }
            }
        }
        return RuntimeState(
            backendConnected = json.optString("status") == "ready",
            audioSourceConnected = hub?.optBoolean("audio_source_connected") == true,
            backendProfileName = profile?.optString("name")?.takeIf(String::isNotBlank),
            latestAlert = alertJson?.let(::parseAlert),
            discoveries = discoveries,
            pendingDiscoveryCount = discoveryJson?.optInt("pending_count", 0) ?: 0,
        )
    }

    private fun parseDiscovery(json: JSONObject): SoundDiscoveryCandidate {
        val profileJson = json.optJSONArray("profile_names")
        val profileNames = buildList {
            if (profileJson != null) {
                repeat(profileJson.length()) { index ->
                    profileJson.optString(index).takeIf(String::isNotBlank)?.let(::add)
                }
            }
        }
        return SoundDiscoveryCandidate(
            id = json.optString("id"),
            label = json.optString("label", "Unknown sound"),
            episodes = json.optInt("episodes", 0),
            firstSeenMs = json.optLong("first_seen_ms", 0),
            lastSeenMs = json.optLong("last_seen_ms", 0),
            meanConfidence = json.optDouble("mean_confidence", 0.0).toFloat(),
            maxConfidence = json.optDouble("max_confidence", 0.0).toFloat(),
            profileNames = profileNames,
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
    )
}
