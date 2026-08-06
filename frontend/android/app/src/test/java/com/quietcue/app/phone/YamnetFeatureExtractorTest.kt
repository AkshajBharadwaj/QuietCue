package com.quietcue.app.phone

import kotlin.math.PI
import kotlin.math.roundToInt
import kotlin.math.sin
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class YamnetFeatureExtractorTest {
    private val extractor = YamnetFeatureExtractor()

    @Test
    fun silenceMatchesQuantizedYamnetFloor() {
        val input = extractor.pcm16ToQuantizedPatch(ByteArray(YamnetFeatureExtractor.WINDOW_BYTES))

        assertEquals(96 * 64, input.remaining())
        while (input.hasRemaining()) assertEquals(0, input.get().toInt() and 0xff)
    }

    @Test
    fun oneKilohertzToneMatchesPythonFrontendFirstFrame() {
        val pcm = ByteArray(YamnetFeatureExtractor.WINDOW_BYTES)
        for (index in 0 until YamnetFeatureExtractor.MIN_WAVEFORM_SAMPLES) {
            val sample = (0.4 * sin(2.0 * PI * 1_000.0 * index / 16_000.0) * 32767.0)
                .roundToInt().toShort().toInt()
            pcm[index * 2] = (sample and 0xff).toByte()
            pcm[index * 2 + 1] = (sample shr 8).toByte()
        }
        val input = extractor.pcm16ToQuantizedPatch(pcm)
        val expected = intArrayOf(
            9, 20, 24, 21, 9, 25, 32, 29, 23, 42, 47, 39, 55, 71, 59, 90,
            105, 122, 181, 225, 224, 172, 112, 103, 74, 73, 53, 52, 40, 36, 30, 24,
        )

        expected.forEach { value ->
            assertTrue(kotlin.math.abs((input.get().toInt() and 0xff) - value) <= 1)
        }
    }
}
