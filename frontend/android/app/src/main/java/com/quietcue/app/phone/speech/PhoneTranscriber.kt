package com.quietcue.app.phone.speech

import java.io.Closeable

interface PhoneTranscriber : Closeable {
    fun transcribe(pcm: ByteArray): String?
    override fun close() = Unit
}
