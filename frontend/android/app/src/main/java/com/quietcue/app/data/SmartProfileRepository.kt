package com.quietcue.app.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartPlace
import com.quietcue.app.domain.SmartProfilePolicy
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.domain.SmartProfileSuggestion
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.smartProfileDataStore by preferencesDataStore(name = "quietcue_smart_profiles")

class SmartProfileRepository(private val context: Context) {
    private object Keys {
        val stateJson = stringPreferencesKey("state_json")
    }

    val state: Flow<SmartProfileState> = context.smartProfileDataStore.data
        .catch { error ->
            if (error is IOException) emit(emptyPreferences()) else throw error
        }
        .map { preferences -> clean(stateFrom(preferences), System.currentTimeMillis()) }

    suspend fun current(): SmartProfileState = state.first()

    suspend fun savePlace(place: SmartPlace) = mutate { state ->
        val cleaned = place.copy(name = place.name.trim())
        val places = state.places.toMutableList()
        val index = places.indexOfFirst { it.id == cleaned.id }
        if (index >= 0) places[index] = cleaned else places += cleaned
        state.copy(
            places = places.sortedBy { it.name.lowercase() },
            statusMessage = "${cleaned.name} is ready for profile suggestions",
        )
    }

    suspend fun deletePlace(placeId: String) = mutate { state ->
        state.copy(
            places = state.places.filterNot { it.id == placeId },
            suggestion = state.suggestion?.takeUnless { it.placeId == placeId },
            activePlaceId = state.activePlaceId?.takeUnless { it == placeId },
            returnProfileId = state.returnProfileId?.takeUnless { state.activePlaceId == placeId },
            statusMessage = "Place removed",
        )
    }

    suspend fun removeProfile(profileId: String) = mutate { state ->
        val removedPlaceIds = state.places.filter { it.profileId == profileId }.mapTo(mutableSetOf()) { it.id }
        state.copy(
            places = state.places.filterNot { it.profileId == profileId },
            suggestion = state.suggestion?.takeUnless {
                it.targetProfileId == profileId || it.placeId in removedPlaceIds
            },
            activePlaceId = state.activePlaceId?.takeUnless { it in removedPlaceIds },
            returnProfileId = state.returnProfileId?.takeUnless { it == profileId },
        )
    }

    suspend fun setAutoApply(placeId: String, enabled: Boolean) = mutate { state ->
        state.copy(
            places = state.places.map { place ->
                if (place.id == placeId) place.copy(autoApply = enabled) else place
            },
            statusMessage = if (enabled) {
                "Automatic switching enabled for this place"
            } else {
                "This place will ask before switching"
            },
            // Turning this switch on is an explicit instruction. Do not leave
            // a prior manual profile choice silently blocking it for hours,
            // and allow an immediate foreground location reconciliation.
            manualOverrideUntilEpochMs = if (enabled) 0L else state.manualOverrideUntilEpochMs,
            suggestion = state.suggestion?.takeUnless { enabled && it.placeId == placeId },
            lastTransitionKey = state.lastTransitionKey?.takeUnless {
                enabled && it.startsWith("$placeId:")
            },
            lastTransitionAtEpochMs = if (
                enabled && state.lastTransitionKey?.startsWith("$placeId:") == true
            ) {
                0L
            } else {
                state.lastTransitionAtEpochMs
            },
        )
    }

    suspend fun recordManualOverride(nowEpochMs: Long = System.currentTimeMillis()) = mutate { state ->
        state.copy(
            suggestion = null,
            manualOverrideUntilEpochMs = nowEpochMs + SmartProfilePolicy.MANUAL_OVERRIDE_MS,
            statusMessage = "Location automation paused for two hours after your manual choice",
        )
    }

    suspend fun recordIgnoredTransition(
        place: SmartPlace,
        transition: PlaceTransition,
        nowEpochMs: Long,
    ) = mutate { state ->
        state.copy(
            lastTransitionKey = "${place.id}:${transition.name}",
            lastTransitionAtEpochMs = nowEpochMs,
        )
    }

    suspend fun publishSuggestion(suggestion: SmartProfileSuggestion) = mutate { state ->
        state.copy(
            suggestion = suggestion,
            lastTransitionKey = "${suggestion.placeId}:${suggestion.transition.name}",
            lastTransitionAtEpochMs = suggestion.createdAtEpochMs,
            statusMessage = if (suggestion.transition == PlaceTransition.ENTER) {
                "Arrival detected at ${suggestion.placeName}"
            } else {
                "Departure detected from ${suggestion.placeName}"
            },
        )
    }

    suspend fun recordAutomaticActivation(
        place: SmartPlace,
        transition: PlaceTransition,
        previousProfileId: String,
        targetProfileName: String,
        nowEpochMs: Long,
    ) = mutate { state ->
        state.copy(
            suggestion = null,
            activePlaceId = if (transition == PlaceTransition.ENTER) place.id else null,
            returnProfileId = if (transition == PlaceTransition.ENTER) previousProfileId else null,
            lastTransitionKey = "${place.id}:${transition.name}",
            lastTransitionAtEpochMs = nowEpochMs,
            statusMessage = "Switched to $targetProfileName automatically",
        )
    }

    suspend fun acceptSuggestion(always: Boolean): SmartProfileSuggestion? {
        var accepted: SmartProfileSuggestion? = null
        mutate { state ->
            val suggestion = state.suggestion ?: return@mutate state
            accepted = suggestion
            state.copy(
                places = if (always && suggestion.transition == PlaceTransition.ENTER) {
                    state.places.map { place ->
                        if (place.id == suggestion.placeId) place.copy(autoApply = true) else place
                    }
                } else {
                    state.places
                },
                suggestion = null,
                activePlaceId = if (suggestion.transition == PlaceTransition.ENTER) {
                    suggestion.placeId
                } else {
                    null
                },
                returnProfileId = if (suggestion.transition == PlaceTransition.ENTER) {
                    suggestion.previousProfileId
                } else {
                    null
                },
                manualOverrideUntilEpochMs = 0L,
                statusMessage = if (always && suggestion.transition == PlaceTransition.ENTER) {
                    "Switched to ${suggestion.targetProfileName}; future arrivals will switch automatically"
                } else {
                    "Switched to ${suggestion.targetProfileName}"
                },
            )
        }
        return accepted
    }

    suspend fun dismissSuggestion() = mutate { state ->
        state.copy(suggestion = null, statusMessage = "Location suggestion dismissed")
    }

    suspend fun clearStatus() = mutate { state -> state.copy(statusMessage = null) }

    private suspend fun mutate(transform: (SmartProfileState) -> SmartProfileState) {
        context.smartProfileDataStore.edit { preferences ->
            val current = clean(stateFrom(preferences), System.currentTimeMillis())
            preferences[Keys.stateJson] = SmartProfileJsonCodec.encode(transform(current))
        }
    }

    private fun stateFrom(preferences: Preferences): SmartProfileState = preferences[Keys.stateJson]
        ?.let { runCatching { SmartProfileJsonCodec.decode(it) }.getOrNull() }
        ?: SmartProfileState()

    private fun clean(state: SmartProfileState, nowEpochMs: Long): SmartProfileState {
        val suggestion = state.suggestion?.takeIf {
            nowEpochMs - it.createdAtEpochMs < SmartProfilePolicy.SUGGESTION_EXPIRY_MS
        }
        // Earlier builds defaulted real places to a room-scale 15 m radius,
        // which normal fused-location accuracy cannot trigger reliably. Migrate
        // only that exact legacy default; preserve deliberate custom radii and
        // the 15 m demo-only fixture.
        val places = state.places.map { place ->
            if (!place.demoOnly && place.radiusMeters == LEGACY_DEFAULT_RADIUS_METERS) {
                place.copy(radiusMeters = RELIABLE_DEFAULT_RADIUS_METERS)
            } else {
                place
            }
        }
        return if (suggestion === state.suggestion && places == state.places) {
            state
        } else {
            state.copy(suggestion = suggestion, places = places)
        }
    }

    companion object {
        private const val LEGACY_DEFAULT_RADIUS_METERS = 15f
        private const val RELIABLE_DEFAULT_RADIUS_METERS = 150f
    }
}
