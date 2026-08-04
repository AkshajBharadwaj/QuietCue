package com.quietcue.app.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileDefaultsTest {
    @Test
    fun `all prescribed built-in profiles are present and complete`() {
        val profiles = ProfileDefaults.all()

        assertEquals(BuiltInProfile.entries.toSet(), profiles.mapNotNull(AlertProfile::builtIn).toSet())
        profiles.forEach { profile ->
            assertEquals(SoundType.entries.toSet(), profile.soundRules.map(SoundRule::sound).toSet())
            assertTrue(ProfileValidator.validate(profile).isEmpty())
        }
    }

    @Test
    fun `emergency profile enables critical sounds with persistent alerts`() {
        val profile = ProfileDefaults.forBuiltIn(BuiltInProfile.EMERGENCY)
        val criticalRules = profile.soundRules.filter { it.sound.safetyCritical }

        assertTrue(criticalRules.isNotEmpty())
        criticalRules.forEach { rule ->
            assertTrue(rule.enabled)
            assertEquals(AlertPriority.EMERGENCY, rule.priority)
            assertEquals(HapticPattern.URGENT_REPEAT, rule.hapticPattern)
            assertTrue(rule.requiresAcknowledgement)
        }
    }

    @Test
    fun `duplicated built-in becomes a deletable custom profile`() {
        val duplicate = ProfileDefaults.duplicate(ProfileDefaults.all().first())

        assertFalse(duplicate.isBuiltIn)
        assertTrue(duplicate.name.endsWith(" copy"))
    }
}
