package com.quietcue.app.domain

import kotlin.math.PI
import kotlin.math.sin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AcousticFingerprintTest {
    @Test
    fun `enrollment produces normalized eight-feature prototype`() {
        val positives = listOf(0.30, 0.35, 0.40).map { amplitude ->
            AcousticFingerprint.fromPcm16(tone(1_000, amplitude))
        }
        val background = AcousticFingerprint.fromPcm16(tone(250, amplitude = 0.05))

        val sound = AcousticFingerprint.enroll(
            name = "Apartment buzzer",
            description = "Front door buzzer",
            priority = AlertPriority.ATTENTION,
            positives = positives,
            background = background,
            nowMs = 42,
        )

        assertTrue(sound.id.startsWith("custom:"))
        assertEquals(8, sound.enrollment?.prototype?.size)
        assertEquals(3, sound.enrollment?.positiveSampleCount)
        assertTrue(sound.enrollment!!.similarityThreshold in 0.72f..0.95f)
    }

    private fun tone(frequency: Int, amplitude: Double = 0.35): ShortArray =
        ShortArray(AcousticFingerprint.SAMPLE_RATE) { index ->
            (Short.MAX_VALUE * amplitude * sin(2.0 * PI * frequency * index / AcousticFingerprint.SAMPLE_RATE))
                .toInt()
                .toShort()
        }
}
