package com.quietcue.app.domain

import java.util.UUID
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

data class CapturedFingerprint(
    val features: List<Float>,
    val rmsDbfs: Float,
)

object AcousticFingerprint {
    const val SAMPLE_RATE = 16_000
    const val FEATURE_COUNT = 8
    const val MIN_POSITIVE_SAMPLES = 3
    const val RECOMMENDED_POSITIVE_SAMPLES = 6
    const val MAX_POSITIVE_SAMPLES = 30
    val frequencies = intArrayOf(250, 375, 500, 750, 1_000, 1_500, 2_000, 3_000)

    fun fromPcm16(samples: ShortArray): CapturedFingerprint {
        require(samples.isNotEmpty()) { "Cannot fingerprint empty audio" }
        val rms = sqrt(samples.sumOf { sample -> sample.toDouble() * sample } / samples.size) / 32768.0
        val amplitudes = frequencies.map { frequency -> goertzelAmplitude(samples, frequency) }
        val norm = sqrt(amplitudes.sumOf { value -> value * value }).coerceAtLeast(1e-12)
        return CapturedFingerprint(
            features = amplitudes.map { (it / norm).toFloat() },
            rmsDbfs = (20.0 * log10(max(rms, 1e-9))).toFloat(),
        )
    }

    fun similarity(left: List<Float>, right: List<Float>): Float {
        if (left.size != FEATURE_COUNT || right.size != FEATURE_COUNT) return 0f
        val dot = left.indices.sumOf { index -> left[index].toDouble() * right[index] }
        val leftNorm = sqrt(left.sumOf { it.toDouble() * it })
        val rightNorm = sqrt(right.sumOf { it.toDouble() * it })
        return (dot / max(leftNorm * rightNorm, 1e-12)).toFloat().coerceIn(0f, 1f)
    }

    fun enroll(
        name: String,
        description: String,
        priority: AlertPriority,
        positives: List<CapturedFingerprint>,
        background: CapturedFingerprint,
        nowMs: Long = System.currentTimeMillis(),
        confusingSounds: List<CapturedFingerprint> = emptyList(),
    ): SoundDefinition {
        require(positives.size in MIN_POSITIVE_SAMPLES..MAX_POSITIVE_SAMPLES) {
            "Record between $MIN_POSITIVE_SAMPLES and $MAX_POSITIVE_SAMPLES examples"
        }
        require(positives.all { it.rmsDbfs >= -50f }) { "One recording is too quiet; record it again" }
        val averaged = List(FEATURE_COUNT) { index -> positives.map { it.features[index] }.average() }
        val norm = sqrt(averaged.sumOf { it * it }).coerceAtLeast(1e-12)
        val prototype = averaged.map { (it / norm).toFloat() }
        val negativeSamples = listOf(background) + confusingSounds
        val backgroundSimilarity = negativeSamples.maxOf { negative ->
            positives.maxOf { positive -> similarity(positive.features, negative.features) }
        }
        require(backgroundSimilarity < 0.92f) {
            "A background or confusing sound is too similar to an example; replace that recording"
        }
        val threshold = max(0.80f, backgroundSimilarity + 0.04f).coerceAtMost(0.95f)
        val pattern = when (priority) {
            AlertPriority.INFORMATIONAL -> HapticPattern.TWO_SHORT
            AlertPriority.ATTENTION -> HapticPattern.LONG_PULSE
            AlertPriority.EMERGENCY -> HapticPattern.URGENT_REPEAT
        }
        return SoundDefinition(
            id = "custom:${UUID.randomUUID()}",
            displayName = name.trim(),
            description = description.trim().ifBlank { "Sound enrolled with the phone microphone" },
            safetyCritical = priority == AlertPriority.EMERGENCY,
            defaultPriority = priority,
            defaultHapticPattern = pattern,
            defaultHapticStrength = if (priority == AlertPriority.EMERGENCY) {
                HapticStrength.STRONG
            } else {
                HapticStrength.STANDARD
            },
            defaultRequiresAcknowledgement = priority == AlertPriority.EMERGENCY,
            enrollment = SoundEnrollment(
                prototype = prototype,
                prototypes = positives.map(CapturedFingerprint::features),
                sampleRmsDbfs = positives.map(CapturedFingerprint::rmsDbfs),
                similarityThreshold = threshold,
                positiveSampleCount = positives.size,
                backgroundSimilarity = backgroundSimilarity,
                createdAtEpochMs = nowMs,
            ),
        )
    }

    private fun goertzelAmplitude(samples: ShortArray, frequency: Int): Double {
        val coefficient = 2.0 * cos(2.0 * PI * frequency / SAMPLE_RATE)
        var previous = 0.0
        var previousPrevious = 0.0
        samples.forEach { sample ->
            val current = sample + coefficient * previous - previousPrevious
            previousPrevious = previous
            previous = current
        }
        val power = previousPrevious * previousPrevious + previous * previous -
            coefficient * previous * previousPrevious
        return 2.0 * sqrt(max(0.0, power)) / samples.size
    }
}
