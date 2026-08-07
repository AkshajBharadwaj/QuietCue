package com.quietcue.app.phone.speech

import java.text.Normalizer
import java.util.Locale

data class PhraseMatch(
    val phrase: String,
    val confidence: Double,
)

object PhraseMatcher {
    fun find(
        transcript: String,
        phrases: List<String>,
        sensitivity: Float = 0.6f,
        asrConfidence: Double? = null,
    ): PhraseMatch? {
        require(sensitivity in 0f..1f) { "Speech sensitivity must be between zero and one" }
        val transcriptTokens = normalize(transcript).split(' ').filter(String::isNotEmpty)
        var bestScore = -1.0
        var bestLength = -1
        var bestPhrase: String? = null
        phrases.asSequence()
            .map { normalize(it) to it.trim() }
            .filter { (normalized, original) -> normalized.isNotEmpty() && original.isNotEmpty() }
            .sortedByDescending { (normalized, _) -> normalized.length }
            .forEach { (normalizedPhrase, originalPhrase) ->
                val phraseTokens = normalizedPhrase.split(' ')
                for (windowSize in maxOf(1, phraseTokens.size - 1)..(phraseTokens.size + 1)) {
                    if (windowSize > transcriptTokens.size) continue
                    for (start in 0..transcriptTokens.size - windowSize) {
                        val window = transcriptTokens.subList(start, start + windowSize).joinToString(" ")
                        val score = phraseSimilarity(normalizedPhrase, window)
                        if (score > bestScore || score == bestScore && normalizedPhrase.length > bestLength) {
                            bestScore = score
                            bestLength = normalizedPhrase.length
                            bestPhrase = originalPhrase
                        }
                    }
                }
            }
        if (bestPhrase == null || bestScore < sensitivity) return null
        val confidence = (bestScore * (asrConfidence ?: 1.0)).coerceIn(0.0, 1.0)
        return PhraseMatch(bestPhrase, (confidence * 10_000).toInt() / 10_000.0)
    }

    internal fun normalize(value: String): String {
        val decomposed = Normalizer.normalize(value, Normalizer.Form.NFKD)
            .lowercase(Locale.ROOT)
        return decomposed
            .filterNot { Character.getType(it) == Character.NON_SPACING_MARK.toInt() }
            .replace(Regex("[^a-z0-9]+"), " ")
            .trim()
            .replace(Regex("\\s+"), " ")
    }

    private fun phraseSimilarity(left: String, right: String): Double {
        if (left == right) return 1.0
        val leftPhonetic = left.split(' ').joinToString("") { phoneticKey(it) }
        val rightPhonetic = right.split(' ').joinToString("") { phoneticKey(it) }
        if (leftPhonetic.isNotEmpty() && leftPhonetic == rightPhonetic) return 0.9
        return editSimilarity(left, right)
    }

    private fun phoneticKey(token: String): String {
        val substituted = token.replace("ph", "f").replace("ck", "k")
        val collapsed = buildString {
            substituted.forEach { character ->
                if (isEmpty() || last() != character) append(character)
            }
        }
        if (collapsed.isEmpty()) return ""
        return buildString {
            append(collapsed.first())
            collapsed.drop(1).filterNot { it in "aeiou" }.forEach(::append)
        }
    }

    private fun editSimilarity(left: String, right: String): Double {
        if (left.isEmpty() || right.isEmpty()) return 0.0
        var previous = IntArray(right.length + 1) { it }
        left.forEachIndexed { leftIndex, leftCharacter ->
            val current = IntArray(right.length + 1)
            current[0] = leftIndex + 1
            right.forEachIndexed { rightIndex, rightCharacter ->
                current[rightIndex + 1] = minOf(
                    current[rightIndex] + 1,
                    previous[rightIndex + 1] + 1,
                    previous[rightIndex] + if (leftCharacter == rightCharacter) 0 else 1,
                )
            }
            previous = current
        }
        return 1.0 - previous.last().toDouble() / maxOf(left.length, right.length)
    }
}
