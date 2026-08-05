package com.quietcue.app.domain

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileTextAgentTest {
    @Test
    fun `agent creates reviewable library profile and preserves safety alerts`() {
        val result = LocalProfileTextAgent().generate(
            description = "I'm entering a crowded library. Ignore phones, but alert me to fire alarms. My name is Akshaj",
            activeProfile = ProfileDefaults.all().first(),
            soundLibrary = SoundLibrary.builtIns(),
        )
        val rules = result.profile.soundRules.associateBy(SoundRule::soundId)

        assertTrue(result.profile.name.contains("Library"))
        assertTrue(rules.getValue(SoundType.FIRE_ALARM.id).enabled)
        assertFalse(rules.getValue(SoundType.PHONE_RINGING.id).enabled)
        assertTrue(result.profile.phraseTriggers.any { it.contains("Akshaj", ignoreCase = true) })
        assertFalse(result.profile.isBuiltIn)
    }
}
