package com.quietcue.app.phone.speech

import java.io.ByteArrayOutputStream
import org.json.JSONObject

class WhisperVocabulary private constructor(
    private val tokenBytes: Array<ByteArray>,
    val endOfText: Int,
    val startOfTranscript: Int,
    val english: Int,
    val transcribe: Int,
    val noSpeech: Int,
    val noTimestamps: Int,
) {
    val size: Int get() = tokenBytes.size

    fun decode(tokenIds: List<Int>): String {
        val output = ByteArrayOutputStream()
        tokenIds.forEach { tokenId ->
            tokenBytes.getOrNull(tokenId)?.let(output::write)
        }
        return output.toByteArray().toString(Charsets.UTF_8).trim()
    }

    companion object {
        fun fromJson(value: String): WhisperVocabulary {
            val root = JSONObject(value)
            val tokens = root.getJSONArray("token_bytes")
            val tokenBytes = Array(tokens.length()) { tokenIndex ->
                val bytes = tokens.getJSONArray(tokenIndex)
                ByteArray(bytes.length()) { byteIndex -> bytes.getInt(byteIndex).toByte() }
            }
            listOf("eot", "sot", "english", "transcribe", "no_speech", "no_timestamps").forEach { key ->
                require(root.getInt(key) in tokenBytes.indices) { "Vocabulary token $key is out of range" }
            }
            return WhisperVocabulary(
                tokenBytes = tokenBytes,
                endOfText = root.getInt("eot"),
                startOfTranscript = root.getInt("sot"),
                english = root.getInt("english"),
                transcribe = root.getInt("transcribe"),
                noSpeech = root.getInt("no_speech"),
                noTimestamps = root.getInt("no_timestamps"),
            )
        }
    }
}
