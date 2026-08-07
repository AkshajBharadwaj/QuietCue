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
            assertEquals(SoundType.entries.map(SoundType::id).toSet(), profile.soundRules.map(SoundRule::soundId).toSet())
            assertTrue(ProfileValidator.validate(profile).isEmpty())
        }
    }

    @Test
    fun `emergency profile enables critical sounds with persistent alerts`() {
        val profile = ProfileDefaults.forBuiltIn(BuiltInProfile.EMERGENCY)
        val criticalIds = SoundLibrary.builtIns().filter(SoundDefinition::safetyCritical).map(SoundDefinition::id).toSet()
        val criticalRules = profile.soundRules.filter { it.soundId in criticalIds }

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

    @Test
    fun `speech defaults match the intended contexts`() {
        val work = ProfileDefaults.forBuiltIn(BuiltInProfile.WORK_SCHOOL)
        val sleep = ProfileDefaults.forBuiltIn(BuiltInProfile.SLEEP_NIGHT)

        assertEquals(SpeechMode.ALWAYS_ON, work.speechMode)
        assertTrue("front desk" in work.phraseTriggers)
        assertEquals(SpeechMode.OFF, sleep.speechMode)
    }
}
