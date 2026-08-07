package com.quietcue.app.phone.speech

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhraseMatcherTest {
    @Test
    fun `matching ignores punctuation and case`() {
        val match = PhraseMatcher.find("Hey, ROHAN!", listOf("Rohan"), asrConfidence = 0.7)

        assertNotNull(match)
        assertEquals("Rohan", match?.phrase)
        assertEquals(0.7, match?.confidence ?: 0.0, 0.0001)
    }

    @Test
    fun `common name transcription variants match`() {
        listOf("Roan", "Rowan", "Ro han").forEach { transcription ->
            val match = PhraseMatcher.find(transcription, listOf("Rohan"))
            assertNotNull(transcription, match)
            assertTrue(match!!.confidence >= 0.6)
        }
    }

    @Test
    fun `phonetic substitution matches while unrelated phrase does not`() {
        assertEquals(0.9, PhraseMatcher.find("Stefan", listOf("Stephan"))?.confidence ?: 0.0, 0.0001)
        assertNull(PhraseMatcher.find("Maya", listOf("Rohan")))
    }

    @Test
    fun `sensitivity is checked before optional asr weighting`() {
        val match = PhraseMatcher.find("Rowan", listOf("Rohan"), 0.75f, 0.5)

        assertEquals(0.4, match?.confidence ?: 0.0, 0.0001)
        assertNull(PhraseMatcher.find("Rowan", listOf("Rohan"), 0.85f))
    }
}
