package com.quietcue.app.phone.speech

import kotlin.math.PI
import kotlin.math.sin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class WhisperFeatureExtractorTest {
    @Test
    fun `silence produces the whisper log floor`() {
        val features = WhisperFeatureExtractor().pcm16ToLogMel(ByteArray(16_000 * 2))

        assertEquals(WhisperFeatureExtractor.MEL_BANDS * WhisperFeatureExtractor.MEL_FRAMES, features.remaining())
        while (features.hasRemaining()) assertEquals(-1.5f, features.get(), 0.0001f)
    }

    @Test
    fun `tone produces finite nonconstant features`() {
        val fixture = javaClass.classLoader?.getResourceAsStream("whisper_reference/mel_points.json")
            ?.bufferedReader()?.use { JSONObject(it.readText()) }
            ?: error("Whisper mel reference fixture is missing")
        val sampleRate = fixture.getInt("sample_rate")
        val sampleCount = fixture.getInt("duration_samples")
        val frequency = fixture.getDouble("tone_hz")
        val amplitude = fixture.getInt("amplitude_pcm16")
        val pcm = ByteArray(sampleCount * 2)
        repeat(sampleCount) { index ->
            val sample = (sin(2.0 * PI * frequency * index / sampleRate) * amplitude).toInt().toShort()
            pcm[index * 2] = (sample.toInt() and 0xff).toByte()
            pcm[index * 2 + 1] = (sample.toInt() shr 8).toByte()
        }

        val features = WhisperFeatureExtractor().pcm16ToLogMel(pcm)
        val tolerance = fixture.getDouble("tolerance").toFloat()
        val points = fixture.getJSONArray("points")
        for (pointIndex in 0 until points.length()) {
            val point = points.getJSONObject(pointIndex)
            val index = point.getInt("band") * WhisperFeatureExtractor.MEL_FRAMES + point.getInt("frame")
            assertEquals("feature[$index]", point.getDouble("value").toFloat(), features.get(index), tolerance)
        }
        var minimum = Float.POSITIVE_INFINITY
        var maximum = Float.NEGATIVE_INFINITY
        while (features.hasRemaining()) {
            val value = features.get()
            assertTrue(value.isFinite())
            minimum = minOf(minimum, value)
            maximum = maxOf(maximum, value)
        }
        assertTrue(maximum - minimum > 0.5f)
    }
}
