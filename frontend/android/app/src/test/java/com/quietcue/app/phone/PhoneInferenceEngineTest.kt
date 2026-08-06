package com.quietcue.app.phone

import com.quietcue.app.domain.ProfileDefaults
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneInferenceEngineTest {
    @Test
    fun buffersTwoHalfSecondChunksThenMapsPhonePrediction() {
        val classifier = FakeClassifier()
        val engine = PhoneInferenceEngine(classifier)

        val pending = engine.process(ByteArray(16_000))
        val inferred = engine.process(ByteArray(16_000))

        assertTrue(pending.pending)
        assertFalse(inferred.pending)
        assertEquals(1, classifier.calls)
        assertEquals("fire_alarm", inferred.events.single().event)
        assertEquals("urgent_repeat", inferred.events.single().pattern)
    }

    @Test
    fun activePhoneProfileProducesArduinoCompatibleAlert() {
        val event = PhoneMappedEvent(
            event = "fire_alarm",
            confidence = 0.93,
            sourceLabel = "Fire alarm",
            category = "emergency",
            pattern = "urgent_repeat",
            requiresAck = true,
        )
        val engine = PhoneProfileDecisionEngine { ProfileDefaults.all().first() }

        val result = engine.decide(listOf(event), capturedAtMs = 1_000, sourceSequence = 3, nowMs = 1_050)
        val alert = result.alerts.getJSONObject(0)

        assertEquals("fire_alarm", alert.getString("event"))
        assertEquals("urgent_repeat", alert.getString("pattern"))
        assertEquals("strong", alert.getString("strength"))
        assertEquals(3, alert.getInt("source_sequence"))
    }

    private class FakeClassifier : PhoneSoundClassifier {
        var calls = 0
        override val provider = "fake"

        override fun classify(pcm: ByteArray, topK: Int): List<PhoneSoundPrediction> {
            calls += 1
            return listOf(PhoneSoundPrediction("Fire alarm", 0.93))
        }

        override fun close() = Unit
    }
}
