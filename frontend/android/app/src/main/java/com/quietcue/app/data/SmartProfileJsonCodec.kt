package com.quietcue.app.data

import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartPlace
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.domain.SmartProfileSuggestion
import org.json.JSONArray
import org.json.JSONObject

object SmartProfileJsonCodec {
    private const val VERSION = 1

    fun encode(state: SmartProfileState): String = JSONObject()
        .put("version", VERSION)
        .put("places", JSONArray().apply { state.places.forEach { put(encodePlace(it)) } })
        .put("suggestion", state.suggestion?.let(::encodeSuggestion) ?: JSONObject.NULL)
        .put("manualOverrideUntilEpochMs", state.manualOverrideUntilEpochMs)
        .put("activePlaceId", state.activePlaceId ?: JSONObject.NULL)
        .put("returnProfileId", state.returnProfileId ?: JSONObject.NULL)
        .put("lastTransitionKey", state.lastTransitionKey ?: JSONObject.NULL)
        .put("lastTransitionAtEpochMs", state.lastTransitionAtEpochMs)
        .put("statusMessage", state.statusMessage ?: JSONObject.NULL)
        .toString()

    fun decode(value: String): SmartProfileState {
        if (value.isBlank()) return SmartProfileState()
        val json = JSONObject(value)
        val placesJson = json.optJSONArray("places")
        val places = buildList {
            if (placesJson != null) {
                for (index in 0 until placesJson.length()) {
                    placesJson.optJSONObject(index)?.let { placeJson ->
                        runCatching { decodePlace(placeJson) }.getOrNull()?.let(::add)
                    }
                }
            }
        }
        val suggestion = json.optJSONObject("suggestion")?.let { suggestionJson ->
            runCatching { decodeSuggestion(suggestionJson) }.getOrNull()
        }
        return SmartProfileState(
            places = places,
            suggestion = suggestion,
            manualOverrideUntilEpochMs = json.optLong("manualOverrideUntilEpochMs", 0L),
            activePlaceId = json.optionalString("activePlaceId"),
            returnProfileId = json.optionalString("returnProfileId"),
            lastTransitionKey = json.optionalString("lastTransitionKey"),
            lastTransitionAtEpochMs = json.optLong("lastTransitionAtEpochMs", 0L),
            statusMessage = json.optionalString("statusMessage"),
        )
    }

    private fun encodePlace(place: SmartPlace): JSONObject = JSONObject()
        .put("id", place.id)
        .put("name", place.name)
        .put("latitude", place.latitude)
        .put("longitude", place.longitude)
        .put("radiusMeters", place.radiusMeters.toDouble())
        .put("profileId", place.profileId)
        .put("enabled", place.enabled)
        .put("autoApply", place.autoApply)
        .put("demoOnly", place.demoOnly)

    private fun decodePlace(json: JSONObject): SmartPlace = SmartPlace(
        id = json.getString("id"),
        name = json.getString("name"),
        latitude = json.getDouble("latitude"),
        longitude = json.getDouble("longitude"),
        radiusMeters = json.optDouble("radiusMeters", 15.0).toFloat().coerceIn(15f, 1_000f),
        profileId = json.getString("profileId"),
        enabled = json.optBoolean("enabled", true),
        autoApply = json.optBoolean("autoApply", false),
        demoOnly = json.optBoolean("demoOnly", false),
    )

    private fun encodeSuggestion(suggestion: SmartProfileSuggestion): JSONObject = JSONObject()
        .put("id", suggestion.id)
        .put("placeId", suggestion.placeId)
        .put("placeName", suggestion.placeName)
        .put("targetProfileId", suggestion.targetProfileId)
        .put("targetProfileName", suggestion.targetProfileName)
        .put("transition", suggestion.transition.name)
        .put("createdAtEpochMs", suggestion.createdAtEpochMs)
        .put("previousProfileId", suggestion.previousProfileId ?: JSONObject.NULL)
        .put("simulated", suggestion.simulated)

    private fun decodeSuggestion(json: JSONObject): SmartProfileSuggestion = SmartProfileSuggestion(
        id = json.getString("id"),
        placeId = json.getString("placeId"),
        placeName = json.getString("placeName"),
        targetProfileId = json.getString("targetProfileId"),
        targetProfileName = json.getString("targetProfileName"),
        transition = PlaceTransition.valueOf(json.getString("transition")),
        createdAtEpochMs = json.getLong("createdAtEpochMs"),
        previousProfileId = json.optionalString("previousProfileId"),
        simulated = json.optBoolean("simulated", false),
    )

    private fun JSONObject.optionalString(key: String): String? =
        optString(key).takeIf { it.isNotBlank() && it != "null" }
}
