package com.quietcue.app.data

import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartProfileDecisionType
import com.quietcue.app.domain.SmartProfilePolicy
import com.quietcue.app.domain.SmartProfileSuggestion
import java.util.UUID
import kotlinx.coroutines.flow.first

enum class SmartTransitionResultType {
    IGNORED,
    SUGGESTED,
    ACTIVATED,
}

data class SmartTransitionResult(
    val type: SmartTransitionResultType,
    val title: String,
    val message: String,
)

class SmartProfileCoordinator(
    private val profileRepository: ProfileRepository,
    private val smartRepository: SmartProfileRepository,
) {
    suspend fun activateManually(profileId: String) {
        profileRepository.setActive(profileId)
        smartRepository.recordManualOverride()
    }

    suspend fun handleTransition(
        placeId: String,
        transition: PlaceTransition,
        nowEpochMs: Long = System.currentTimeMillis(),
        simulated: Boolean = false,
    ): SmartTransitionResult {
        val state = smartRepository.current()
        val place = state.places.firstOrNull { it.id == placeId }
            ?: return ignored("Unknown smart place")
        val catalog = profileRepository.catalog.first()
        val activeProfileId = catalog.activeProfileId
        val decision = SmartProfilePolicy.decide(
            place = place,
            transition = transition,
            state = state,
            activeProfileId = activeProfileId,
            availableProfileIds = catalog.profiles.mapTo(mutableSetOf()) { it.id },
            nowEpochMs = nowEpochMs,
        )
        val targetProfileId = decision.targetProfileId
        val targetProfile = catalog.profiles.firstOrNull { it.id == targetProfileId }
        if (decision.type == SmartProfileDecisionType.IGNORE || targetProfile == null) {
            smartRepository.recordIgnoredTransition(place, transition, nowEpochMs)
            return ignored("No profile change needed")
        }

        if (decision.type == SmartProfileDecisionType.ACTIVATE) {
            profileRepository.setActive(targetProfile.id)
            smartRepository.recordAutomaticActivation(
                place = place,
                transition = transition,
                previousProfileId = activeProfileId,
                targetProfileName = targetProfile.name,
                nowEpochMs = nowEpochMs,
            )
            return SmartTransitionResult(
                type = SmartTransitionResultType.ACTIVATED,
                title = "QuietCue changed profiles",
                message = "${place.name}: ${targetProfile.name} is now active",
            )
        }

        val suggestion = SmartProfileSuggestion(
            id = UUID.randomUUID().toString(),
            placeId = place.id,
            placeName = place.name,
            targetProfileId = targetProfile.id,
            targetProfileName = targetProfile.name,
            transition = transition,
            createdAtEpochMs = nowEpochMs,
            previousProfileId = if (transition == PlaceTransition.ENTER) activeProfileId else null,
            simulated = simulated,
        )
        smartRepository.publishSuggestion(suggestion)
        return SmartTransitionResult(
            type = SmartTransitionResultType.SUGGESTED,
            title = if (transition == PlaceTransition.ENTER) {
                "Profile suggestion for ${place.name}"
            } else {
                "Leaving ${place.name}?"
            },
            message = "Switch to ${targetProfile.name}?",
        )
    }

    suspend fun acceptSuggestion(always: Boolean): SmartProfileSuggestion? {
        val suggestion = smartRepository.current().suggestion ?: return null
        profileRepository.setActive(suggestion.targetProfileId)
        return smartRepository.acceptSuggestion(always)
    }

    suspend fun dismissSuggestion() = smartRepository.dismissSuggestion()

    private fun ignored(message: String) = SmartTransitionResult(
        type = SmartTransitionResultType.IGNORED,
        title = "Smart profiles",
        message = message,
    )
}
