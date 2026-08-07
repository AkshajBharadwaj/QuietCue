package com.quietcue.app.domain

import java.util.UUID

enum class PlaceTransition {
    ENTER,
    EXIT,
}

data class SmartPlace(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val radiusMeters: Float = 15f,
    val profileId: String,
    val enabled: Boolean = true,
    val autoApply: Boolean = false,
    val demoOnly: Boolean = false,
) {
    init {
        require(name.isNotBlank()) { "Give the place a name" }
        require(latitude in -90.0..90.0) { "Invalid latitude" }
        require(longitude in -180.0..180.0) { "Invalid longitude" }
        require(radiusMeters in 15f..1_000f) { "Place radius must be between 15 and 1,000 meters" }
        require(profileId.isNotBlank()) { "Choose a profile" }
    }
}

data class SmartProfileSuggestion(
    val id: String,
    val placeId: String,
    val placeName: String,
    val targetProfileId: String,
    val targetProfileName: String,
    val transition: PlaceTransition,
    val createdAtEpochMs: Long,
    val previousProfileId: String? = null,
    val simulated: Boolean = false,
)

data class SmartProfileState(
    val places: List<SmartPlace> = emptyList(),
    val suggestion: SmartProfileSuggestion? = null,
    val manualOverrideUntilEpochMs: Long = 0L,
    val activePlaceId: String? = null,
    val returnProfileId: String? = null,
    val lastTransitionKey: String? = null,
    val lastTransitionAtEpochMs: Long = 0L,
    val statusMessage: String? = null,
) {
    fun manualOverrideActive(nowEpochMs: Long): Boolean = manualOverrideUntilEpochMs > nowEpochMs
}

enum class SmartProfileDecisionType {
    IGNORE,
    SUGGEST,
    ACTIVATE,
}

data class SmartProfileDecision(
    val type: SmartProfileDecisionType,
    val targetProfileId: String? = null,
)

object SmartProfilePolicy {
    const val MANUAL_OVERRIDE_MS = 2 * 60 * 60 * 1_000L
    const val DUPLICATE_TRANSITION_MS = 5 * 60 * 1_000L
    const val SUGGESTION_EXPIRY_MS = 6 * 60 * 60 * 1_000L

    fun decide(
        place: SmartPlace,
        transition: PlaceTransition,
        state: SmartProfileState,
        activeProfileId: String,
        availableProfileIds: Set<String>,
        nowEpochMs: Long,
    ): SmartProfileDecision {
        if (!place.enabled) return SmartProfileDecision(SmartProfileDecisionType.IGNORE)
        val transitionKey = "${place.id}:${transition.name}"
        if (
            state.lastTransitionKey == transitionKey &&
            nowEpochMs - state.lastTransitionAtEpochMs in 0 until DUPLICATE_TRANSITION_MS
        ) {
            return SmartProfileDecision(SmartProfileDecisionType.IGNORE)
        }

        val targetProfileId = when (transition) {
            PlaceTransition.ENTER -> place.profileId
            PlaceTransition.EXIT -> state.returnProfileId?.takeIf { state.activePlaceId == place.id }
        } ?: return SmartProfileDecision(SmartProfileDecisionType.IGNORE)

        if (targetProfileId !in availableProfileIds || targetProfileId == activeProfileId) {
            return SmartProfileDecision(SmartProfileDecisionType.IGNORE)
        }
        val canApplyAutomatically = place.autoApply && !state.manualOverrideActive(nowEpochMs)
        return SmartProfileDecision(
            type = if (canApplyAutomatically) {
                SmartProfileDecisionType.ACTIVATE
            } else {
                SmartProfileDecisionType.SUGGEST
            },
            targetProfileId = targetProfileId,
        )
    }
}
