package com.quietcue.app.phone

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.ln
import kotlin.math.ln1p
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

/** Numpy-free YAMNet frontend matching backend/inference/audio_features.py. */
class YamnetFeatureExtractor {
    private val hann = FloatArray(WINDOW_SAMPLES) { index ->
        (0.5 - 0.5 * cos(2.0 * PI * index / WINDOW_SAMPLES)).toFloat()
    }
    private val melWeights = buildMelWeights()

    fun pcm16ToQuantizedPatch(pcm: ByteArray): ByteBuffer {
        require(pcm.isNotEmpty() && pcm.size % 2 == 0) { "PCM16 must contain complete samples" }
        val waveform = FloatArray(MIN_WAVEFORM_SAMPLES)
        val sampleCount = min(pcm.size / 2, waveform.size)
        for (index in 0 until sampleCount) {
            val low = pcm[index * 2].toInt() and 0xff
            val high = pcm[index * 2 + 1].toInt()
            waveform[index] = ((high shl 8) or low).toShort() / 32768.0f
        }

        val output = ByteBuffer.allocateDirect(PATCH_FRAMES * MEL_BANDS)
            .order(ByteOrder.nativeOrder())
        val real = DoubleArray(FFT_LENGTH)
        val imaginary = DoubleArray(FFT_LENGTH)
        val magnitudes = FloatArray(FFT_LENGTH / 2 + 1)
        for (frame in 0 until PATCH_FRAMES) {
            real.fill(0.0)
            imaginary.fill(0.0)
            val start = frame * HOP_SAMPLES
            for (sample in 0 until WINDOW_SAMPLES) {
                real[sample] = (waveform[start + sample] * hann[sample]).toDouble()
            }
            fft(real, imaginary)
            for (bin in magnitudes.indices) {
                magnitudes[bin] = hypot(real[bin], imaginary[bin]).toFloat()
            }
            for (band in 0 until MEL_BANDS) {
                var energy = 0.0f
                for (bin in magnitudes.indices) {
                    energy += magnitudes[bin] * melWeights[bin][band]
                }
                val feature = ln((energy + LOG_OFFSET).toDouble()).toFloat()
                val quantized = (feature / INPUT_SCALE).roundToInt() + INPUT_ZERO_POINT
                output.put(quantized.coerceIn(0, 255).toByte())
            }
        }
        output.flip()
        return output
    }

    private fun buildMelWeights(): Array<FloatArray> {
        val spectrogramMels = DoubleArray(FFT_LENGTH / 2 + 1) { index ->
            hertzToMel(index * SAMPLE_RATE.toDouble() / FFT_LENGTH)
        }
        val minMel = hertzToMel(MEL_MIN_HZ)
        val maxMel = hertzToMel(MEL_MAX_HZ)
        val edges = DoubleArray(MEL_BANDS + 2) { index ->
            minMel + (maxMel - minMel) * index / (MEL_BANDS + 1)
        }
        return Array(spectrogramMels.size) { bin ->
            FloatArray(MEL_BANDS) { band ->
                val up = (spectrogramMels[bin] - edges[band]) / (edges[band + 1] - edges[band])
                val down = (edges[band + 2] - spectrogramMels[bin]) /
                    (edges[band + 2] - edges[band + 1])
                max(0.0, min(up, down)).toFloat()
            }
        }
    }

    private fun fft(real: DoubleArray, imaginary: DoubleArray) {
        var reversed = 0
        for (index in 1 until FFT_LENGTH) {
            var bit = FFT_LENGTH shr 1
            while (reversed and bit != 0) {
                reversed = reversed xor bit
                bit = bit shr 1
            }
            reversed = reversed xor bit
            if (index < reversed) {
                val realSwap = real[index]
                real[index] = real[reversed]
                real[reversed] = realSwap
                val imaginarySwap = imaginary[index]
                imaginary[index] = imaginary[reversed]
                imaginary[reversed] = imaginarySwap
            }
        }

        var length = 2
        while (length <= FFT_LENGTH) {
            val angle = -2.0 * PI / length
            val rootReal = cos(angle)
            val rootImaginary = sin(angle)
            var block = 0
            while (block < FFT_LENGTH) {
                var currentReal = 1.0
                var currentImaginary = 0.0
                for (offset in 0 until length / 2) {
                    val even = block + offset
                    val odd = even + length / 2
                    val oddReal = real[odd] * currentReal - imaginary[odd] * currentImaginary
                    val oddImaginary = real[odd] * currentImaginary + imaginary[odd] * currentReal
                    real[odd] = real[even] - oddReal
                    imaginary[odd] = imaginary[even] - oddImaginary
                    real[even] += oddReal
                    imaginary[even] += oddImaginary
                    val nextReal = currentReal * rootReal - currentImaginary * rootImaginary
                    currentImaginary = currentReal * rootImaginary + currentImaginary * rootReal
                    currentReal = nextReal
                }
                block += length
            }
            length = length shl 1
        }
    }

    private fun hertzToMel(frequency: Double): Double = 1127.0 * ln1p(frequency / 700.0)

    companion object {
        const val SAMPLE_RATE = 16_000
        const val WINDOW_SAMPLES = 400
        const val HOP_SAMPLES = 160
        const val FFT_LENGTH = 512
        const val MEL_BANDS = 64
        const val PATCH_FRAMES = 96
        const val MIN_WAVEFORM_SAMPLES = 15_600
        const val WINDOW_BYTES = MIN_WAVEFORM_SAMPLES * 2
        const val HOP_BYTES = 8_000 * 2
        const val MEL_MIN_HZ = 125.0
        const val MEL_MAX_HZ = 7_500.0
        const val LOG_OFFSET = 0.001f
        const val INPUT_SCALE = 0.04793788492679596f
        const val INPUT_ZERO_POINT = 144
    }
}
