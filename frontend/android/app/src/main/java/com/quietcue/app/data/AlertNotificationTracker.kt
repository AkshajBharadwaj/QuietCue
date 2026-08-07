package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert

data class AlertNotificationChange(
    val alert: DetectedAlert,
    val previousEventId: String?,
    val shouldCancel: Boolean,
)

class AlertNotificationTracker {
    private var lastAlertId: String? = null
    private var lastHapticActive: Boolean? = null

    fun consumeIfNew(alert: DetectedAlert?): DetectedAlert? {
        return consumeChange(alert)?.alert
    }

    fun consumeChange(alert: DetectedAlert?): AlertNotificationChange? {
        val eventId = alert?.eventId?.takeIf(String::isNotBlank) ?: return null
        if (eventId == lastAlertId && alert.hapticActive == lastHapticActive) return null
        val previousEventId = lastAlertId?.takeIf { it != eventId }
        lastAlertId = eventId
        lastHapticActive = alert.hapticActive
        return AlertNotificationChange(
            alert = alert,
            previousEventId = previousEventId,
            shouldCancel = !alert.hapticActive && alert.acknowledgedAtMs != null,
        )
    }

    fun reset() {
        lastAlertId = null
        lastHapticActive = null
    }
}
