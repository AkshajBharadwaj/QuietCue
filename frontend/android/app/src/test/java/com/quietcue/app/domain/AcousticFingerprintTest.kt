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
        assertEquals(3, sound.enrollment?.prototypes?.size)
        assertEquals(3, sound.enrollment?.sampleRmsDbfs?.size)
        assertEquals(3, sound.enrollment?.positiveSampleCount)
        assertTrue(sound.enrollment!!.similarityThreshold in 0.93f..0.98f)
        assertEquals(4, sound.enrollment.matcherVersion)
    }

    @Test
    fun `enrollment retains varied examples instead of collapsing them`() {
        val positives = listOf(0.20, 0.35, 0.50).map {
            AcousticFingerprint.fromPcm16(tone(1_000, it))
        }
        val background = AcousticFingerprint.fromPcm16(ShortArray(AcousticFingerprint.SAMPLE_RATE))

        val sound = AcousticFingerprint.enroll(
            "Variable buzzer", "Different modes", AlertPriority.ATTENTION, positives, background, 42,
        )

        assertEquals(positives.map(CapturedFingerprint::features), sound.enrollment?.prototypes)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `enrollment rejects unrelated examples`() {
        val positives = listOf(250, 1_000, 3_000).map { AcousticFingerprint.fromPcm16(tone(it)) }
        val background = AcousticFingerprint.fromPcm16(ShortArray(AcousticFingerprint.SAMPLE_RATE))

        AcousticFingerprint.enroll(
            "Mixed sounds", "Not one repeat", AlertPriority.ATTENTION, positives, background, 42,
        )
    }

    @Test
    fun `version four match needs consensus across repeats`() {
        val candidate = listOf(1f, 0f, 0f, 0f, 0f, 0f, 0f, 0f)
        val enrollment = SoundEnrollment(
            prototype = List(3) { (1.0 / kotlin.math.sqrt(3.0)).toFloat() } + List(5) { 0f },
            prototypes = listOf(
                candidate,
                listOf(0f, 1f, 0f, 0f, 0f, 0f, 0f, 0f),
                listOf(0f, 0f, 1f, 0f, 0f, 0f, 0f, 0f),
            ),
            similarityThreshold = 0.9f,
            positiveSampleCount = 3,
            backgroundSimilarity = 0f,
            createdAtEpochMs = 42,
            matcherVersion = 4,
        )

        assertEquals(null, AcousticFingerprint.matchConfidence(candidate, enrollment))
    }

    private fun tone(frequency: Int, amplitude: Double = 0.35): ShortArray =
        ShortArray(AcousticFingerprint.SAMPLE_RATE) { index ->
            (Short.MAX_VALUE * amplitude * sin(2.0 * PI * frequency * index / AcousticFingerprint.SAMPLE_RATE))
                .toInt()
                .toShort()
        }
}
