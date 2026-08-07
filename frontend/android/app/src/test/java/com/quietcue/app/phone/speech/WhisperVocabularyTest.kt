package com.quietcue.app.phone.speech

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WhisperVocabularyTest {
    @Test
    fun `token bytes decode utf8 while special tokens remain empty`() {
        val vocabulary = WhisperVocabulary.fromJson(
            """{
                "eot": 0,
                "sot": 1,
                "english": 2,
                "transcribe": 3,
                "no_speech": 4,
                "no_timestamps": 5,
                "token_bytes": [[], [], [], [], [], [], [82,111], [104,97,110]]
            }""".trimIndent(),
        )

        assertEquals("Rohan", vocabulary.decode(listOf(1, 2, 3, 5, 6, 7, 0)))
        assertNull(selectWhisperToken(0, vocabulary.noSpeech, vocabulary))
        assertNull(selectWhisperToken(3, vocabulary.endOfText, vocabulary))
        assertEquals(vocabulary.english, selectWhisperToken(0, 6, vocabulary))
        assertEquals(vocabulary.transcribe, selectWhisperToken(1, 6, vocabulary))
        assertEquals(vocabulary.noTimestamps, selectWhisperToken(2, 6, vocabulary))
        assertEquals(6, selectWhisperToken(3, 6, vocabulary))
    }
}
