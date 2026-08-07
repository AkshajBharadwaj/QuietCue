package com.quietcue.app.data

import com.quietcue.app.domain.DetectedAlert
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

class AlertNotificationTrackerTest {
    @Test
    fun `consumes each new alert once`() {
        val tracker = AlertNotificationTracker()
        val alert = sampleAlert("evt-1")

        assertSame(alert, tracker.consumeIfNew(alert))
        assertNull(tracker.consumeIfNew(alert))
        assertNull(tracker.consumeIfNew(null))
    }

    @Test
    fun `allows a different alert id after the first one`() {
        val tracker = AlertNotificationTracker()
        val first = sampleAlert("evt-1")
        val second = sampleAlert("evt-2")

        assertSame(first, tracker.consumeIfNew(first))
        assertSame(second, tracker.consumeIfNew(second))
    }

    private fun sampleAlert(eventId: String) = DetectedAlert(
        eventId = eventId,
        event = "fire_alarm",
        confidence = 0.97f,
        category = "emergency",
        pattern = "urgent_repeat",
        profileName = "Home",
        sourceLabel = "mic",
        totalLatencyMs = 84,
        requiresAcknowledgement = true,
        simulated = false,
        fallbackToPhone = false,
    )
}
