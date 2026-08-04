package com.quietcue.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileValidatorTest {
    @Test
    fun `profile must keep at least one sound enabled`() {
        val profile = ProfileDefaults.all().first().let { original ->
            original.copy(soundRules = original.soundRules.map { it.copy(enabled = false) })
        }

        assertTrue(ProfileValidator.validate(profile).any { it.contains("at least one sound") })
    }

    @Test
    fun `time parser accepts twelve and twenty-four hour input`() {
        assertEquals(22 * 60, parseTime("10:00 PM"))
        assertEquals(7 * 60 + 30, parseTime("07:30"))
        assertEquals(0, parseTime("12:00 am"))
        assertEquals("10:00 PM", formatTime(22 * 60))
    }

    @Test
    fun `time parser rejects impossible input`() {
        assertEquals(null, parseTime("25:00"))
        assertEquals(null, parseTime("10:75 PM"))
        assertEquals(null, parseTime("bedtime"))
    }
}
