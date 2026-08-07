package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert

class AlertNotificationTracker {
    private var lastAlertId: String? = null

    fun consumeIfNew(alert: DetectedAlert?): DetectedAlert? {
        val eventId = alert?.eventId?.takeIf(String::isNotBlank) ?: return null
        if (eventId == lastAlertId) return null
        lastAlertId = eventId
        return alert
    }

    fun reset() {
        lastAlertId = null
    }
}
