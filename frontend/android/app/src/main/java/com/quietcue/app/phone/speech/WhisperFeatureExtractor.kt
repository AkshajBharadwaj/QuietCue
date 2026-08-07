package com.quietcue.app.phone.speech

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/** OpenAI/Hugging Face Whisper 80-band Slaney log-mel frontend. */
class WhisperFeatureExtractor {
    private val hann = DoubleArray(WINDOW_SAMPLES) { index ->
        0.5 - 0.5 * cos(2.0 * PI * index / WINDOW_SAMPLES)
    }
    private val melWeights = buildMelWeights()
    private val chirpCos = DoubleArray(WINDOW_SAMPLES) { index ->
        cos(PI * (index.toLong() * index % (WINDOW_SAMPLES * 2L)) / WINDOW_SAMPLES)
    }
    private val chirpSin = DoubleArray(WINDOW_SAMPLES) { index ->
        sin(PI * (index.toLong() * index % (WINDOW_SAMPLES * 2L)) / WINDOW_SAMPLES)
    }
    private val convolutionSize = 1 shl 10
    private val kernelReal = DoubleArray(convolutionSize)
    private val kernelImaginary = DoubleArray(convolutionSize)
    private val workReal = DoubleArray(convolutionSize)
    private val workImaginary = DoubleArray(convolutionSize)

    init {
        kernelReal[0] = chirpCos[0]
        kernelImaginary[0] = chirpSin[0]
        for (index in 1 until WINDOW_SAMPLES) {
            kernelReal[index] = chirpCos[index]
            kernelImaginary[index] = chirpSin[index]
            kernelReal[convolutionSize - index] = chirpCos[index]
            kernelImaginary[convolutionSize - index] = chirpSin[index]
        }
        fftRadix2(kernelReal, kernelImaginary, inverse = false)
    }

    @Synchronized
    fun pcm16ToLogMel(pcm: ByteArray): FloatBuffer {
        require(pcm.isNotEmpty() && pcm.size % 2 == 0) { "PCM16 must contain complete samples" }
        val waveform = FloatArray(MAX_AUDIO_SAMPLES)
        val sampleCount = min(pcm.size / 2, waveform.size)
        for (index in 0 until sampleCount) {
            val low = pcm[index * 2].toInt() and 0xff
            val high = pcm[index * 2 + 1].toInt()
            waveform[index] = ((high shl 8) or low).toShort() / 32768.0f
        }

        val features = FloatArray(MEL_BANDS * MEL_FRAMES)
        var maximumLogEnergy = Double.NEGATIVE_INFINITY
        for (frame in 0 until MEL_FRAMES) {
            val start = frame * HOP_SAMPLES - WINDOW_SAMPLES / 2
            workReal.fill(0.0)
            workImaginary.fill(0.0)
            for (sample in 0 until WINDOW_SAMPLES) {
                val value = reflectedSample(waveform, start + sample) * hann[sample]
                workReal[sample] = value * chirpCos[sample]
                workImaginary[sample] = -value * chirpSin[sample]
            }
            fftRadix2(workReal, workImaginary, inverse = false)
            for (index in workReal.indices) {
                val real = workReal[index] * kernelReal[index] - workImaginary[index] * kernelImaginary[index]
                val imaginary = workReal[index] * kernelImaginary[index] + workImaginary[index] * kernelReal[index]
                workReal[index] = real
                workImaginary[index] = imaginary
            }
            fftRadix2(workReal, workImaginary, inverse = true)

            for (band in 0 until MEL_BANDS) {
                var energy = 0.0
                for (bin in 0..WINDOW_SAMPLES / 2) {
                    val real = workReal[bin] * chirpCos[bin] + workImaginary[bin] * chirpSin[bin]
                    val imaginary = -workReal[bin] * chirpSin[bin] + workImaginary[bin] * chirpCos[bin]
                    energy += (real * real + imaginary * imaginary) * melWeights[band][bin]
                }
                val logEnergy = log10(max(energy, LOG_FLOOR))
                features[band * MEL_FRAMES + frame] = logEnergy.toFloat()
                maximumLogEnergy = max(maximumLogEnergy, logEnergy)
            }
        }

        val clampFloor = maximumLogEnergy - 8.0
        val output = ByteBuffer.allocateDirect(features.size * Float.SIZE_BYTES)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
        features.forEach { value ->
            output.put(((max(value.toDouble(), clampFloor) + 4.0) / 4.0).toFloat())
        }
        output.flip()
        return output
    }

    private fun reflectedSample(waveform: FloatArray, index: Int): Double {
        val reflected = when {
            index < 0 -> -index
            index >= waveform.size -> waveform.size * 2 - 2 - index
            else -> index
        }
        return waveform[reflected.coerceIn(0, waveform.lastIndex)].toDouble()
    }

    private fun buildMelWeights(): Array<DoubleArray> {
        val frequencyBins = DoubleArray(WINDOW_SAMPLES / 2 + 1) { index ->
            index * SAMPLE_RATE.toDouble() / WINDOW_SAMPLES
        }
        val minimumMel = hertzToSlaneyMel(0.0)
        val maximumMel = hertzToSlaneyMel(SAMPLE_RATE / 2.0)
        val melEdges = DoubleArray(MEL_BANDS + 2) { index ->
            minimumMel + (maximumMel - minimumMel) * index / (MEL_BANDS + 1)
        }
        val frequencyEdges = melEdges.map(::slaneyMelToHertz)
        return Array(MEL_BANDS) { band ->
            val lower = frequencyEdges[band]
            val center = frequencyEdges[band + 1]
            val upper = frequencyEdges[band + 2]
            val normalization = 2.0 / (upper - lower)
            DoubleArray(frequencyBins.size) { bin ->
                val rising = (frequencyBins[bin] - lower) / (center - lower)
                val falling = (upper - frequencyBins[bin]) / (upper - center)
                max(0.0, min(rising, falling)) * normalization
            }
        }
    }

    private fun hertzToSlaneyMel(frequency: Double): Double = if (frequency < 1_000.0) {
        frequency / MEL_LINEAR_SPACING
    } else {
        MEL_LOG_THRESHOLD + ln(frequency / 1_000.0) / MEL_LOG_STEP
    }

    private fun slaneyMelToHertz(mel: Double): Double = if (mel < MEL_LOG_THRESHOLD) {
        MEL_LINEAR_SPACING * mel
    } else {
        1_000.0 * kotlin.math.exp(MEL_LOG_STEP * (mel - MEL_LOG_THRESHOLD))
    }

    private fun fftRadix2(real: DoubleArray, imaginary: DoubleArray, inverse: Boolean) {
        val size = real.size
        var reversed = 0
        for (index in 1 until size) {
            var bit = size shr 1
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
        while (length <= size) {
            val angle = (if (inverse) 2.0 else -2.0) * PI / length
            val rootReal = cos(angle)
            val rootImaginary = sin(angle)
            var block = 0
            while (block < size) {
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
        if (inverse) {
            for (index in real.indices) {
                real[index] /= size
                imaginary[index] /= size
            }
        }
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        const val MAX_AUDIO_SAMPLES = 30 * SAMPLE_RATE
        const val WINDOW_SAMPLES = 400
        const val HOP_SAMPLES = 160
        const val MEL_BANDS = 80
        const val MEL_FRAMES = 3_000
        private const val LOG_FLOOR = 1e-10
        private const val MEL_LINEAR_SPACING = 200.0 / 3.0
        private const val MEL_LOG_THRESHOLD = 15.0
        private val MEL_LOG_STEP = ln(6.4) / 27.0
    }
}
