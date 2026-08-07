package com.quietcue.app.phone.speech

import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.SpeechMode
import com.quietcue.app.domain.SpeechModel
import com.quietcue.app.domain.SpeechSettings
import com.quietcue.app.phone.PhoneMappedEvent
import java.io.Closeable
import java.util.concurrent.ExecutorService
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

data class SpeechGateResult(
    val event: PhoneMappedEvent? = null,
    val pending: Boolean = false,
    val listening: Boolean = false,
    val modelLoaded: Boolean = false,
    val inferenceMs: Double? = null,
    val error: String? = null,
)

object SpeechTriggerResolver {
    fun enabled(profile: AlertProfile, settings: SpeechSettings): Boolean =
        profile.speechMode == SpeechMode.ALWAYS_ON ||
            profile.speechMode == SpeechMode.INHERIT && settings.enabled

    fun phrases(
        bank: MemoryBank,
        profile: AlertProfile,
        additionalPhrases: List<String> = emptyList(),
    ): List<String> = buildList {
        val settings = bank.speechSettings
        addAll(settings.globalPhrases)
        if (settings.listenForIdentity) {
            bank.identity?.let { identity ->
                add(identity.displayName)
                add(identity.pronunciation)
                addAll(identity.aliases)
                addAll(identity.recognitionPhrases)
            }
        }
        if (settings.listenForPeople) {
            bank.people.forEach { person ->
                add(person.name)
                addAll(person.aliases)
            }
        }
        addAll(profile.phraseTriggers)
        addAll(additionalPhrases)
    }.map(String::trim).filter(String::isNotEmpty).distinctBy(String::lowercase)
}

class SpeechGate(
    private val transcriberFactory: (SpeechModel) -> PhoneTranscriber,
    executor: ExecutorService? = null,
    private val minAudioMs: Int = 1_000,
    private val endOfUtteranceMs: Int = 500,
    private val maxAudioMs: Int = 4_000,
    private val overlapMs: Int = 250,
) : Closeable {
    private data class Recognition(
        val generation: Long,
        val match: PhraseMatch?,
        val inferenceMs: Double,
        val error: String? = null,
    )

    private val ownsExecutor = executor == null
    private val executor = executor ?: java.util.concurrent.Executors.newSingleThreadExecutor { task ->
        Thread(task, "quietcue-phone-speech")
    }
    private val buffer = ArrayList<Byte>()
    private var future: Future<Recognition>? = null
    private var wasVoice = false
    private var noiseFloor = 0.005
    private var generation = 0L
    private var requestedModel: SpeechModel? = null
    private var requestedConfiguration: String? = null
    private var loadedModel: SpeechModel? = null
    private var transcriber: PhoneTranscriber? = null
    private var lastError: String? = null

    init {
        require(200 <= endOfUtteranceMs && endOfUtteranceMs <= minAudioMs && minAudioMs <= maxAudioMs)
        require(overlapMs in 0 until minAudioMs)
    }

    @Synchronized
    fun update(
        pcm: ByteArray,
        speechConfidence: Double,
        edgeVoiceDetected: Boolean,
        bank: MemoryBank,
        profile: AlertProfile,
        additionalPhrases: List<String> = emptyList(),
    ): SpeechGateResult {
        require(pcm.isNotEmpty() && pcm.size % 2 == 0) { "PCM16 must contain complete samples" }
        val settings = bank.speechSettings
        if (!SpeechTriggerResolver.enabled(profile, settings)) {
            resetLocked(clearRequestedConfiguration = true)
            return SpeechGateResult(modelLoaded = loadedModel == settings.model)
        }
        val phrases = SpeechTriggerResolver.phrases(bank, profile, additionalPhrases)
        if (phrases.isEmpty()) {
            resetLocked(clearRequestedConfiguration = true)
            return SpeechGateResult(modelLoaded = loadedModel == settings.model)
        }
        val configuration = buildString {
            append(profile.id).append('|')
            append(profile.speechMode.name).append('|')
            append(settings.model.name).append('|')
            append(settings.sensitivity).append('|')
            phrases.forEach { append(it.lowercase()).append('\u0000') }
        }
        if (requestedConfiguration != null && requestedConfiguration != configuration) {
            resetLocked(clearRequestedConfiguration = true)
        }
        requestedConfiguration = configuration
        requestedModel = settings.model

        val completed = takeCompleted()
        if (completed != null) {
            lastError = completed.error
        }
        val rms = rms(pcm)
        val voiceDetected = (edgeVoiceDetected || speechConfidence >= SPEECH_CONFIDENCE_THRESHOLD) &&
            rms >= maxOf(MINIMUM_RMS, noiseFloor * NOISE_MULTIPLIER)
        if (!voiceDetected && !edgeVoiceDetected && speechConfidence < SPEECH_CONFIDENCE_THRESHOLD) {
            noiseFloor = noiseFloor * 0.95 + rms * 0.05
        }
        if (voiceDetected) {
            pcm.forEach(buffer::add)
            trimBuffer()
        }
        val durationMs = buffer.size / 2 * 1_000 / SAMPLE_RATE
        val utteranceEnded = wasVoice && !voiceDetected
        val shouldSubmit = durationMs >= minAudioMs ||
            utteranceEnded && durationMs >= endOfUtteranceMs
        if (future == null && shouldSubmit && lastError == null) {
            submit(settings, phrases)
        } else if (utteranceEnded && durationMs < endOfUtteranceMs) {
            buffer.clear()
        }
        wasVoice = voiceDetected
        return SpeechGateResult(
            event = completed?.match?.let { match ->
                PhoneMappedEvent(
                    event = "name_called",
                    confidence = match.confidence,
                    sourceLabel = "phrase: \"${match.phrase}\"",
                    category = "attention",
                    pattern = "long_pulse",
                    requiresAck = false,
                )
            },
            pending = future != null,
            listening = voiceDetected,
            modelLoaded = loadedModel == settings.model,
            inferenceMs = completed?.inferenceMs,
            error = lastError,
        )
    }

    @Synchronized
    fun reset() = resetLocked(clearRequestedConfiguration = true)

    override fun close() {
        val toClose: PhoneTranscriber?
        synchronized(this) {
            resetLocked(clearRequestedConfiguration = true)
            toClose = transcriber
            transcriber = null
            loadedModel = null
        }
        if (ownsExecutor) {
            executor.shutdownNow()
            executor.awaitTermination(1, TimeUnit.SECONDS)
        }
        toClose?.close()
    }

    private fun submit(settings: SpeechSettings, phrases: List<String>) {
        val audio = ByteArray(buffer.size) { index -> buffer[index] }
        val overlapBytes = bytesForMs(overlapMs)
        val retained = if (overlapBytes == 0) emptyList() else buffer.takeLast(minOf(overlapBytes, buffer.size))
        buffer.clear()
        buffer.addAll(retained)
        val submittedGeneration = generation
        future = executor.submit<Recognition> {
            val started = System.nanoTime()
            try {
                val activeTranscriber = transcriberFor(settings.model)
                val transcript = activeTranscriber.transcribe(audio)
                val match = transcript?.let { PhraseMatcher.find(it, phrases, settings.sensitivity) }
                Recognition(
                    generation = submittedGeneration,
                    match = match,
                    inferenceMs = (System.nanoTime() - started) / 1_000_000.0,
                )
            } catch (error: Throwable) {
                Recognition(
                    generation = submittedGeneration,
                    match = null,
                    inferenceMs = (System.nanoTime() - started) / 1_000_000.0,
                    error = "${error.javaClass.simpleName}: ${error.message}",
                )
            }
        }
    }

    private fun takeCompleted(): Recognition? {
        val active = future ?: return null
        if (!active.isDone) return null
        future = null
        return runCatching { active.get() }.getOrNull()?.takeIf { it.generation == generation }
    }

    private fun transcriberFor(model: SpeechModel): PhoneTranscriber {
        synchronized(this) {
            if (loadedModel == model && transcriber != null) return requireNotNull(transcriber)
            transcriber?.close()
            return transcriberFactory(model).also {
                transcriber = it
                loadedModel = model
            }
        }
    }

    private fun resetLocked(clearRequestedConfiguration: Boolean) {
        generation += 1
        buffer.clear()
        future?.cancel(true)
        future = null
        wasVoice = false
        noiseFloor = 0.005
        lastError = null
        if (clearRequestedConfiguration) {
            requestedModel = null
            requestedConfiguration = null
        }
    }

    private fun trimBuffer() {
        val maximumBytes = bytesForMs(maxAudioMs)
        if (buffer.size <= maximumBytes) return
        val retained = buffer.takeLast(maximumBytes)
        buffer.clear()
        buffer.addAll(retained)
    }

    private fun rms(pcm: ByteArray): Double {
        var squared = 0.0
        var samples = 0
        var index = 0
        while (index < pcm.size) {
            val low = pcm[index].toInt() and 0xff
            val high = pcm[index + 1].toInt()
            val value = ((high shl 8) or low).toShort() / 32768.0
            squared += value * value
            samples += 1
            index += 2
        }
        return sqrt(squared / samples)
    }

    private fun bytesForMs(durationMs: Int): Int = SAMPLE_RATE * durationMs / 1_000 * 2

    companion object {
        private const val SAMPLE_RATE = 16_000
        private const val SPEECH_CONFIDENCE_THRESHOLD = 0.10
        private const val MINIMUM_RMS = 0.003
        private const val NOISE_MULTIPLIER = 1.5
    }
}
