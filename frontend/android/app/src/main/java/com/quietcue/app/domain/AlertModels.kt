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
) {
    val displayName: String
        get() = if (event.startsWith("custom:") && sourceLabel.startsWith("enrolled: ")) {
            sourceLabel.removePrefix("enrolled: ")
        } else event
            .split('_')
            .joinToString(" ") { word -> word.replaceFirstChar(Char::uppercase) }
}

data class RuntimeState(
    val backendConnected: Boolean = false,
    val audioSourceConnected: Boolean = false,
    val backendProfileName: String? = null,
    val latestAlert: DetectedAlert? = null,
    val errorMessage: String? = null,
)
