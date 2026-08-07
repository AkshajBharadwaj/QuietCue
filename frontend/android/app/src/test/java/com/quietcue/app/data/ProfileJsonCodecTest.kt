package com.quietcue.app.data

import com.quietcue.app.domain.CustomHapticPattern
import com.quietcue.app.domain.CustomHapticStep
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.ProfileDefaults
import org.junit.Assert.assertEquals
import org.junit.Test

class ProfileJsonCodecTest {
    @Test
    fun `profile collection survives persistence round trip`() {
        val profiles = ProfileDefaults.all() + ProfileDefaults.newCustom()

        val restored = ProfileJsonCodec.decode(ProfileJsonCodec.encode(profiles))

        assertEquals(profiles, restored)
    }

    @Test
    fun `blank input decodes to an empty collection`() {
        assertEquals(emptyList<Any>(), ProfileJsonCodec.decode(""))
    }

    @Test
    fun `enrolled sound rule remains enabled after profile round trip`() {
        val enrolledRule = ProfileDefaults.fallbackRule("custom:door-buzzer").copy(enabled = true)
        val profile = ProfileDefaults.newCustom().let { draft ->
            draft.copy(soundRules = draft.soundRules + enrolledRule)
        }

        val restored = ProfileJsonCodec.decode(ProfileJsonCodec.encode(listOf(profile))).single()

        assertEquals(enrolledRule, restored.soundRules.single { it.soundId == enrolledRule.soundId })
    }

    @Test
    fun `touch recorded haptic survives persistence round trip`() {
        val custom = CustomHapticPattern(
            name = "Knock knock",
            steps = listOf(CustomHapticStep(420, 180), CustomHapticStep(650, 200)),
        )
        val profile = ProfileDefaults.newCustom().let { draft ->
            draft.copy(
                soundRules = draft.soundRules.mapIndexed { index, rule ->
                    if (index == 0) {
                        rule.copy(
                            hapticPattern = HapticPattern.CUSTOM,
                            customHapticPattern = custom,
                        )
                    } else {
                        rule
                    }
                },
            )
        }

        val restored = ProfileJsonCodec.decode(ProfileJsonCodec.encode(listOf(profile))).single()

        assertEquals(custom, restored.soundRules.first().customHapticPattern)
        assertEquals(HapticPattern.CUSTOM, restored.soundRules.first().hapticPattern)
    }
}
