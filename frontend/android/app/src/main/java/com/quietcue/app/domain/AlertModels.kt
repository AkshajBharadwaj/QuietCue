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

enum class InferenceDevice(val wireValue: String, val displayName: String) {
    COPILOT_PC("copilot_pc", "PC"),
    SAMSUNG_PHONE("samsung_phone", "Samsung"),
    ;

    companion object {
        fun fromWire(value: String?): InferenceDevice = entries.firstOrNull {
            it.wireValue == value
        } ?: COPILOT_PC
    }
}

data class RuntimeState(
    val backendConnected: Boolean = false,
    val audioSourceConnected: Boolean = false,
    val backendProfileName: String? = null,
    val latestAlert: DetectedAlert? = null,
    val errorMessage: String? = null,
    val stopInProgress: Boolean = false,
    val requestedInferenceDevice: InferenceDevice = InferenceDevice.COPILOT_PC,
    val activeInferenceDevice: InferenceDevice = InferenceDevice.COPILOT_PC,
    val samsungInferenceAvailable: Boolean = false,
    val inferenceSwitchPending: Boolean = false,
    val inferenceRoutingError: String? = null,
)
