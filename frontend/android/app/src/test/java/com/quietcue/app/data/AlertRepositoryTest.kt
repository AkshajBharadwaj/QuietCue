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
                  "discoveries": {
                    "pending_count": 2,
                    "candidates": [{
                      "id": "disc_test",
                      "label": "Vacuum cleaner",
                      "episodes": 4,
                      "first_seen_ms": 1000,
                      "last_seen_ms": 9000,
                      "mean_confidence": 0.72,
                      "max_confidence": 0.88,
                      "profile_names": ["Home"]
                    }]
                  },
                  "latest_alert": {
                    "event_id": "evt_test",
                    "event": "fire_alarm",
                    "confidence": 0.94,
                    "category": "emergency",
                    "pattern": "urgent_repeat",
                    "profile_name": "Home",
                    "source_label": "Fire alarm",
                    "total_after_capture_ms": 41,
                    "requires_ack": true,
                    "simulated": true,
                    "fallback_to_phone": true,
                    "haptic_active": true
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
        assertTrue(state.latestAlert?.fallbackToPhone == true)
        assertTrue(state.latestAlert?.hapticActive == true)
        assertEquals(2, state.pendingDiscoveryCount)
        assertEquals("Vacuum cleaner", state.discoveries.single().label)
        assertEquals(4, state.discoveries.single().episodes)
        assertEquals(listOf("Home"), state.discoveries.single().profileNames)
    }
}
