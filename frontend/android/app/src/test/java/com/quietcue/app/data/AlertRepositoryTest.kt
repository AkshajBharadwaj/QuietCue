package com.quietcue.app.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AlertRepositoryTest {
    @Test
    fun parsesHubAndLatestAlert() {
        val state = AlertRepository().parseState(
            JSONObject(
                """
                {
                  "status": "ready",
                  "active_profile": {"id": "home", "name": "Home"},
                  "hub": {"audio_source_connected": true},
                  "latest_alert": {
                    "event_id": "evt_test",
                    "event": "fire_alarm",
                    "confidence": 0.94,
                    "category": "emergency",
                    "pattern": "urgent_repeat",
                    "profile_name": "Home",
                    "total_after_capture_ms": 41,
                    "requires_ack": true,
                    "simulated": true
                  }
                }
                """.trimIndent(),
            ),
        )

        assertTrue(state.backendConnected)
        assertTrue(state.audioSourceConnected)
        assertEquals("Home", state.backendProfileName)
        assertEquals("Fire Alarm", state.latestAlert?.displayName)
        assertEquals(41, state.latestAlert?.totalLatencyMs)
    }
}
