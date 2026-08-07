package com.quietcue.app.domain

data class DetectedAlert(
    val eventId: String,
    val event: String,
    val confidence: Float,
    val category: String,
    val pattern: String,
    val profileName: String,
    val sourceLabel: String,
    val totalLatencyMs: Int,
    val requiresAcknowledgement: Boolean,
    val simulated: Boolean,
    val fallbackToPhone: Boolean,
    val hapticActive: Boolean = false,
    val acknowledgedAtMs: Long? = null,
) {
    val displayName: String
        get() = if (event.startsWith("custom:") && sourceLabel.startsWith("enrolled: ")) {
            sourceLabel.removePrefix("enrolled: ")
        } else event
            .split('_')
            .joinToString(" ") { word -> word.replaceFirstChar(Char::uppercase) }
}

data class SoundDiscoveryCandidate(
    val id: String,
    val label: String,
    val episodes: Int,
    val firstSeenMs: Long,
    val lastSeenMs: Long,
    val meanConfidence: Float,
    val maxConfidence: Float,
    val profileNames: List<String>,
)

data class RuntimeState(
    val backendConnected: Boolean = false,
    val audioSourceConnected: Boolean = false,
    val backendProfileName: String? = null,
    val latestAlert: DetectedAlert? = null,
    val discoveries: List<SoundDiscoveryCandidate> = emptyList(),
    val pendingDiscoveryCount: Int = 0,
    val errorMessage: String? = null,
    val stopInProgress: Boolean = false,
)
