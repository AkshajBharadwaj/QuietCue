package com.quietcue.app.data

import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.HapticStrength
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.SoundEnrollment
import org.json.JSONArray
import org.json.JSONObject

object SoundLibraryJsonCodec {
    private const val VERSION = 1

    fun encode(sounds: List<SoundDefinition>): String = JSONObject()
        .put("version", VERSION)
        .put("sounds", JSONArray().apply { sounds.filter(SoundDefinition::isEnrolled).forEach { put(encode(it)) } })
        .toString()

    fun decode(value: String): List<SoundDefinition> {
        if (value.isBlank()) return emptyList()
        val array = JSONObject(value).optJSONArray("sounds") ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                array.optJSONObject(index)?.let { json -> runCatching { decode(json) }.getOrNull()?.let(::add) }
            }
        }
    }

    private fun encode(sound: SoundDefinition): JSONObject = JSONObject()
        .put("id", sound.id)
        .put("displayName", sound.displayName)
        .put("description", sound.description)
        .put("safetyCritical", sound.safetyCritical)
        .put("defaultPriority", sound.defaultPriority.name)
        .put("defaultHapticPattern", sound.defaultHapticPattern.name)
        .put("defaultHapticStrength", sound.defaultHapticStrength.name)
        .put("defaultRequiresAcknowledgement", sound.defaultRequiresAcknowledgement)
        .put(
            "enrollment",
            sound.enrollment?.let { enrollment ->
                JSONObject()
                    .put("prototype", JSONArray(enrollment.prototype))
                    .put("similarityThreshold", enrollment.similarityThreshold.toDouble())
                    .put("positiveSampleCount", enrollment.positiveSampleCount)
                    .put("backgroundSimilarity", enrollment.backgroundSimilarity.toDouble())
                    .put("createdAtEpochMs", enrollment.createdAtEpochMs)
                    .put("matcherVersion", enrollment.matcherVersion)
            } ?: JSONObject.NULL,
        )

    private fun decode(json: JSONObject): SoundDefinition? {
        val id = json.optString("id")
        val name = json.optString("displayName").trim()
        val enrollmentJson = json.optJSONObject("enrollment") ?: return null
        val prototypeJson = enrollmentJson.optJSONArray("prototype") ?: return null
        val prototype = buildList {
            for (index in 0 until prototypeJson.length()) add(prototypeJson.optDouble(index).toFloat())
        }
        if (!id.startsWith("custom:") || name.isBlank() || prototype.size != 8) return null
        val priority = json.enumOrNull<AlertPriority>("defaultPriority") ?: AlertPriority.ATTENTION
        return SoundDefinition(
            id = id,
            displayName = name,
            description = json.optString("description", "Enrolled custom sound"),
            safetyCritical = json.optBoolean("safetyCritical", priority == AlertPriority.EMERGENCY),
            defaultPriority = priority,
            defaultHapticPattern = json.enumOrNull<HapticPattern>("defaultHapticPattern")
                ?: recommendedPattern(priority),
            defaultHapticStrength = json.enumOrNull<HapticStrength>("defaultHapticStrength")
                ?: if (priority == AlertPriority.EMERGENCY) HapticStrength.STRONG else HapticStrength.STANDARD,
            defaultRequiresAcknowledgement = json.optBoolean(
                "defaultRequiresAcknowledgement",
                priority == AlertPriority.EMERGENCY,
            ),
            enrollment = SoundEnrollment(
                prototype = prototype,
                similarityThreshold = enrollmentJson.optDouble("similarityThreshold", 0.82).toFloat()
                    .coerceIn(0.70f, 0.98f),
                positiveSampleCount = enrollmentJson.optInt("positiveSampleCount", 3).coerceAtLeast(1),
                backgroundSimilarity = enrollmentJson.optDouble("backgroundSimilarity", 0.0).toFloat()
                    .coerceIn(0f, 1f),
                createdAtEpochMs = enrollmentJson.optLong("createdAtEpochMs", 0L),
                matcherVersion = enrollmentJson.optInt("matcherVersion", 1),
            ),
        )
    }

    private fun recommendedPattern(priority: AlertPriority): HapticPattern = when (priority) {
        AlertPriority.INFORMATIONAL -> HapticPattern.TWO_SHORT
        AlertPriority.ATTENTION -> HapticPattern.LONG_PULSE
        AlertPriority.EMERGENCY -> HapticPattern.URGENT_REPEAT
    }

    private inline fun <reified T : Enum<T>> JSONObject.enumOrNull(key: String): T? {
        val value = optString(key)
        return enumValues<T>().firstOrNull { it.name == value }
    }
}
