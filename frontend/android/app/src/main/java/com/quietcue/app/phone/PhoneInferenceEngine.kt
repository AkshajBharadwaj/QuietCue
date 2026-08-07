package com.quietcue.app.phone

import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.SoundRule
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.phone.speech.SpeechGate
import java.time.ZonedDateTime
import java.util.UUID
import kotlin.math.round
import org.json.JSONArray
import org.json.JSONObject

data class PhoneMappedEvent(
    val event: String,
    val confidence: Double,
    val sourceLabel: String,
    val category: String,
    val pattern: String,
    val requiresAck: Boolean,
)

data class PhoneInferenceResult(
    val events: List<PhoneMappedEvent> = emptyList(),
    val predictions: List<PhoneSoundPrediction> = emptyList(),
    val speechConfidence: Double = 0.0,
    val inferenceMs: Double = 0.0,
    val pending: Boolean = false,
    val speechPending: Boolean = false,
    val speechListening: Boolean = false,
    val speechModelLoaded: Boolean = false,
    val speechInferenceMs: Double? = null,
    val speechError: String? = null,
)

class PhoneInferenceEngine(
    private val classifier: PhoneSoundClassifier,
    private val profileProvider: () -> AlertProfile = { ProfileDefaults.all().first() },
    private val memoryBankProvider: () -> MemoryBank = { MemoryBank() },
    private val speechGate: SpeechGate? = null,
) {
    private var bufferedPcm = byteArrayOf()

    @Synchronized
    fun process(
        pcm: ByteArray,
        edgeVoiceDetected: Boolean = false,
        additionalPhrases: List<String> = emptyList(),
    ): PhoneInferenceResult {
        require(pcm.isNotEmpty() && pcm.size % 2 == 0) { "PCM16 must contain complete samples" }
        bufferedPcm += pcm
        val environmentalPending = bufferedPcm.size < YamnetFeatureExtractor.WINDOW_BYTES
        val predictions: List<PhoneSoundPrediction>
        val inferenceMs: Double
        val mapping: Pair<List<PhoneMappedEvent>, Double>
        if (environmentalPending) {
            predictions = emptyList()
            inferenceMs = 0.0
            mapping = emptyList<PhoneMappedEvent>() to 0.0
        } else {
            val window = bufferedPcm.copyOfRange(0, YamnetFeatureExtractor.WINDOW_BYTES)
            bufferedPcm = bufferedPcm.copyOfRange(
                minOf(YamnetFeatureExtractor.HOP_BYTES, bufferedPcm.size),
                bufferedPcm.size,
            )
            val started = System.nanoTime()
            predictions = classifier.classify(window, topK = 10)
            inferenceMs = (System.nanoTime() - started) / 1_000_000.0
            mapping = mapPredictions(predictions)
        }
        val speech = speechGate?.update(
            pcm = pcm,
            speechConfidence = mapping.second,
            edgeVoiceDetected = edgeVoiceDetected,
            bank = memoryBankProvider(),
            profile = profileProvider(),
            additionalPhrases = additionalPhrases,
        )
        return PhoneInferenceResult(
            events = mapping.first + listOfNotNull(speech?.event),
            predictions = predictions.take(5),
            speechConfidence = mapping.second,
            inferenceMs = round(inferenceMs * 100.0) / 100.0,
            pending = environmentalPending,
            speechPending = speech?.pending == true,
            speechListening = speech?.listening == true,
            speechModelLoaded = speech?.modelLoaded == true,
            speechInferenceMs = speech?.inferenceMs,
            speechError = speech?.error,
        )
    }

    @Synchronized
    fun reset() {
        bufferedPcm = byteArrayOf()
        speechGate?.reset()
    }

    fun close() = speechGate?.close()

    private fun mapPredictions(
        predictions: List<PhoneSoundPrediction>,
    ): Pair<List<PhoneMappedEvent>, Double> {
        val strongest = mutableMapOf<String, PhoneMappedEvent>()
        var speechConfidence = 0.0
        predictions.forEach { prediction ->
            val label = prediction.label.trim().lowercase()
            if (speechTerms.any(label::contains)) {
                speechConfidence = maxOf(speechConfidence, prediction.confidence)
            }
            eventTerms.forEach { (event, terms) ->
                if (prediction.confidence < 0.10 || terms.none(label::contains)) return@forEach
                val mapped = mappedEvent(event, prediction)
                if ((strongest[event]?.confidence ?: -1.0) < mapped.confidence) {
                    strongest[event] = mapped
                }
            }
        }
        return strongest.values.sortedByDescending(PhoneMappedEvent::confidence) to speechConfidence
    }

    private fun mappedEvent(event: String, prediction: PhoneSoundPrediction): PhoneMappedEvent {
        val emergency = event == "fire_alarm" || event == "siren"
        val attention = event == "car_horn" || event == "doorbell_knock" || event == "baby_crying"
        return PhoneMappedEvent(
            event = event,
            confidence = prediction.confidence,
            sourceLabel = prediction.label,
            category = when {
                emergency -> "emergency"
                attention -> "attention"
                else -> "informational"
            },
            pattern = when {
                emergency -> "urgent_repeat"
                attention -> "long_pulse"
                else -> "two_short"
            },
            requiresAck = emergency,
        )
    }

    companion object {
        private val eventTerms = mapOf(
            "fire_alarm" to listOf("fire alarm", "smoke detector", "smoke alarm"),
            "doorbell_knock" to listOf("doorbell", "ding-dong", "knock"),
            "car_horn" to listOf("vehicle horn", "car horn", "honking", "air horn", "truck horn"),
            "siren" to listOf("siren", "emergency vehicle"),
            "baby_crying" to listOf("baby cry", "infant cry", "crying, sobbing"),
            "kitchen_timer" to listOf("timer", "alarm clock"),
            "phone_ringing" to listOf("telephone bell ringing", "ringtone"),
        )
        private val speechTerms = listOf("speech", "conversation", "narration", "child speech")
    }
}

data class PhoneDecisionResult(val alerts: JSONArray, val suppressed: JSONArray)

class PhoneProfileDecisionEngine(private val profileProvider: () -> AlertProfile) {
    private val lastAlertMs = mutableMapOf<String, Long>()

    @Synchronized
    fun decide(
        events: List<PhoneMappedEvent>,
        capturedAtMs: Long,
        sourceSequence: Int,
        nowMs: Long = System.currentTimeMillis(),
    ): PhoneDecisionResult {
        val profile = profileProvider()
        val quietNow = isQuietNow(profile)
        val alerts = JSONArray()
        val suppressed = JSONArray()
        events.forEach { event ->
            val rule = profile.soundRules.firstOrNull { it.soundId == event.event }
            val reason = suppressionReason(event, rule, nowMs, quietNow)
            if (reason != null) {
                suppressed.put(
                    JSONObject()
                        .put("event", event.event)
                        .put("confidence", event.confidence)
                        .put("reason", reason),
                )
                return@forEach
            }
            checkNotNull(rule)
            lastAlertMs[event.event] = nowMs
            alerts.put(
                JSONObject()
                    .put("event_id", "evt_${UUID.randomUUID().toString().replace("-", "")}")
                    .put("event", event.event)
                    .put("category", rule.priority.name.lowercase())
                    .put("confidence", event.confidence)
                    .put("pattern", rule.hapticPattern.name.lowercase())
                    .put("custom_pattern", rule.customHapticPattern?.encodedSteps.orEmpty())
                    .put("strength", rule.hapticStrength.name.lowercase())
                    .put("requires_ack", rule.requiresAcknowledgement)
                    .put("profile_id", profile.id)
                    .put("profile_name", profile.name)
                    .put("source_label", event.sourceLabel)
                    .put("source_sequence", sourceSequence)
                    .put("captured_at_ms", capturedAtMs)
                    .put("issued_at_ms", nowMs)
                    .put("total_after_capture_ms", maxOf(0L, nowMs - capturedAtMs))
                    .put("simulated", false)
                    .put("fallback_to_phone", false),
            )
        }
        return PhoneDecisionResult(alerts, suppressed)
    }

    private fun suppressionReason(
        event: PhoneMappedEvent,
        rule: SoundRule?,
        nowMs: Long,
        quietNow: Boolean,
    ): String? = when {
        rule == null -> "unsupported_by_profile"
        !rule.enabled -> "disabled_by_profile"
        event.confidence < rule.confidenceThreshold -> "below_confidence_threshold"
        quietNow && rule.priority != AlertPriority.EMERGENCY -> "quiet_hours"
        lastAlertMs[event.event]?.let { nowMs - it < rule.cooldownSeconds * 1_000L } == true -> "cooldown"
        else -> null
    }

    private fun isQuietNow(profile: AlertProfile): Boolean {
        val quiet = profile.quietHours
        if (!quiet.enabled || quiet.startMinutes == quiet.endMinutes) return false
        val now = ZonedDateTime.now()
        val minute = now.hour * 60 + now.minute
        return if (quiet.startMinutes < quiet.endMinutes) {
            minute in quiet.startMinutes until quiet.endMinutes
        } else {
            minute >= quiet.startMinutes || minute < quiet.endMinutes
        }
    }
}
