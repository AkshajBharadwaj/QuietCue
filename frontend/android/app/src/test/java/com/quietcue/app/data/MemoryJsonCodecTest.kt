package com.quietcue.app.data

import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.UserIdentity
import org.junit.Assert.assertEquals
import org.junit.Test

class MemoryJsonCodecTest {
    @Test
    fun `manual memory bank survives persistence round trip`() {
        val bank = MemoryBank(
            identity = UserIdentity(
                displayName = "Akshaj",
                pronunciation = "Ak-shudge",
                aliases = listOf("Ak"),
                recognitionPhrases = listOf("Hey oxides"),
                updatedAtEpochMs = 10,
            ),
            people = listOf(
                PersonMemory("person-1", "Maya", "Sister", aliases = listOf("May"), updatedAtEpochMs = 11),
            ),
            contexts = listOf(
                ContextMemory("context-1", "Tuesday class", "Building 4", updatedAtEpochMs = 12),
            ),
        )

        assertEquals(bank, MemoryJsonCodec.decode(MemoryJsonCodec.encode(bank)))
    }
}
