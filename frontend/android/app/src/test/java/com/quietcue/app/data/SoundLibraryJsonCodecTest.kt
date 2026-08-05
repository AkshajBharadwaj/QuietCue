package com.quietcue.app.data

import com.quietcue.app.domain.AcousticFingerprint
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.CapturedFingerprint
import org.junit.Assert.assertEquals
import org.junit.Test

class SoundLibraryJsonCodecTest {
    @Test
    fun `enrolled sound survives persistence round trip`() {
        val positives = listOf(0.98f, 0.99f, 1f).map { scale ->
            CapturedFingerprint(listOf(scale, 0f, 0f, 0f, 0f, 0f, 0f, 0f), -20f)
        }
        val background = CapturedFingerprint(listOf(0f, 1f, 0f, 0f, 0f, 0f, 0f, 0f), -30f)
        val sound = AcousticFingerprint.enroll("Buzzer", "Door buzzer", AlertPriority.ATTENTION, positives, background, 42)

        val restored = SoundLibraryJsonCodec.decode(SoundLibraryJsonCodec.encode(listOf(sound)))

        assertEquals(listOf(sound), restored)
    }
}
