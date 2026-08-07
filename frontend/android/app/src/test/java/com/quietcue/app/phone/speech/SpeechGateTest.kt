package com.quietcue.app.phone.speech

import com.quietcue.app.domain.BuiltInProfile
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.SpeechMode
import com.quietcue.app.domain.SpeechSettings
import com.quietcue.app.domain.UserIdentity
import java.util.Collections
import java.util.concurrent.AbstractExecutorService
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

private class InlineExecutorService : AbstractExecutorService() {
    private var shutdown = false
    override fun shutdown() { shutdown = true }
    override fun shutdownNow(): MutableList<Runnable> { shutdown = true; return Collections.emptyList() }
    override fun isShutdown(): Boolean = shutdown
    override fun isTerminated(): Boolean = shutdown
    override fun awaitTermination(timeout: Long, unit: TimeUnit): Boolean = true
    override fun execute(command: Runnable) = command.run()
}

private class FixedPhoneTranscriber(private val text: String) : PhoneTranscriber {
    var calls = 0
    override fun transcribe(pcm: ByteArray): String {
        calls += 1
        return text
    }
}

class SpeechGateTest {
    @Test
    fun `resolver applies global identity people and profile rules`() {
        val profile = ProfileDefaults.forBuiltIn(BuiltInProfile.WORK_SCHOOL)
        val bank = MemoryBank(
            identity = UserIdentity("Rohan", aliases = listOf("Ro")),
            people = listOf(com.quietcue.app.domain.PersonMemory("1", "Maya", aliases = listOf("May"))),
            speechSettings = SpeechSettings(
                listenForPeople = true,
                globalPhrases = listOf("excuse me"),
            ),
        )

        val phrases = SpeechTriggerResolver.phrases(bank, profile)

        assertTrue("Rohan" in phrases)
        assertTrue("Maya" in phrases)
        assertTrue("May" in phrases)
        assertTrue("front desk" in phrases)
        assertTrue("excuse me" in phrases)
    }

    @Test
    fun `speech runs asynchronously and emits name event`() {
        val transcriber = FixedPhoneTranscriber("Hey Rowan")
        val gate = SpeechGate(
            transcriberFactory = { transcriber },
            executor = InlineExecutorService(),
        )
        val profile = ProfileDefaults.all().first()
        val bank = MemoryBank(identity = UserIdentity("Rohan"))
        val voicedPcm = bouncyPcm(16_000)

        val submitted = gate.update(voicedPcm, 0.8, false, bank, profile)
        val completed = gate.update(ByteArray(16_000), 0.0, false, bank, profile)

        assertTrue(submitted.pending)
        assertNotNull(completed.event)
        assertEquals("name_called", completed.event?.event)
        assertEquals(1, transcriber.calls)
    }

    @Test
    fun `off profile never loads or invokes transcriber`() {
        val transcriber = FixedPhoneTranscriber("Rohan")
        val gate = SpeechGate({ transcriber }, InlineExecutorService())
        val profile = ProfileDefaults.all().first().copy(speechMode = SpeechMode.OFF)

        val result = gate.update(
            bouncyPcm(16_000),
            0.9,
            false,
            MemoryBank(identity = UserIdentity("Rohan")),
            profile,
        )

        assertFalse(result.pending)
        assertFalse(result.modelLoaded)
        assertEquals(0, transcriber.calls)
    }

    private fun bouncyPcm(samples: Int): ByteArray = ByteArray(samples * 2) { index ->
        if (index % 2 == 0) 0 else if ((index / 2) % 2 == 0) 32 else -32
    }
}
