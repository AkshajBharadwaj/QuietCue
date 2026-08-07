package com.quietcue.app.data

import com.quietcue.app.domain.ActivationRule
import com.quietcue.app.domain.ActivityContext
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.BuiltInProfile
import com.quietcue.app.domain.CustomHapticPattern
import com.quietcue.app.domain.CustomHapticStep
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.HapticStrength
import com.quietcue.app.domain.ProfileColor
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.ProfileIcon
import com.quietcue.app.domain.QuietHours
import com.quietcue.app.domain.SoundRule
import com.quietcue.app.domain.SoundType
import org.json.JSONArray
import org.json.JSONObject

object ProfileJsonCodec {
    private const val VERSION = 3

    fun encode(profiles: List<AlertProfile>): String = JSONObject()
        .put("version", VERSION)
        .put("profiles", JSONArray().apply { profiles.forEach { put(encodeProfile(it)) } })
        .toString()

    fun decode(value: String): List<AlertProfile> {
        if (value.isBlank()) return emptyList()
        val array = JSONObject(value).optJSONArray("profiles") ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val profileJson = array.optJSONObject(index) ?: continue
                runCatching { decodeProfile(profileJson) }.getOrNull()?.let(::add)
            }
        }
    }

    private fun encodeProfile(profile: AlertProfile): JSONObject = JSONObject()
        .put("id", profile.id)
        .put("name", profile.name)
        .put("description", profile.description)
        .put("builtIn", profile.builtIn?.name ?: JSONObject.NULL)
        .put("icon", profile.icon.name)
        .put("color", profile.color.name)
        .put(
            "quietHours",
            JSONObject()
                .put("enabled", profile.quietHours.enabled)
                .put("startMinutes", profile.quietHours.startMinutes)
                .put("endMinutes", profile.quietHours.endMinutes),
        )
        .put(
            "activation",
            JSONObject()
                .put("enabled", profile.activation.enabled)
                .put("activity", profile.activation.activity.name)
                .put("locationLabel", profile.activation.locationLabel),
        )
        .put("phraseTriggers", JSONArray(profile.phraseTriggers))
        .put(
            "soundRules",
            JSONArray().apply {
                profile.soundRules.forEach { rule ->
                    val ruleJson = JSONObject()
                            .put("soundId", rule.soundId)
                            .put("enabled", rule.enabled)
                            .put("confidenceThreshold", rule.confidenceThreshold.toDouble())
                            .put("priority", rule.priority.name)
                            .put("hapticPattern", rule.hapticPattern.name)
                            .put("hapticStrength", rule.hapticStrength.name)
                            .put("requiresAcknowledgement", rule.requiresAcknowledgement)
                            .put("cooldownSeconds", rule.cooldownSeconds)
                    rule.customHapticPattern?.let { custom ->
                        ruleJson.put(
                            "customHapticPattern",
                            JSONObject()
                                .put("name", custom.name)
                                .put(
                                    "steps",
                                    JSONArray().apply {
                                        custom.steps.forEach { step ->
                                            put(JSONObject().put("onMs", step.onMs).put("offMs", step.offMs))
                                        }
                                    },
                                ),
                        )
                    }
                    put(ruleJson)
                }
            },
        )

    private fun decodeProfile(json: JSONObject): AlertProfile {
        val builtIn = json.enumOrNull<BuiltInProfile>("builtIn")
        val fallback = builtIn?.let(ProfileDefaults::forBuiltIn) ?: ProfileDefaults.newCustom()
        val quietJson = json.optJSONObject("quietHours")
        val activationJson = json.optJSONObject("activation")
        val phraseJson = json.optJSONArray("phraseTriggers")
        val rulesJson = json.optJSONArray("soundRules")
        val decodedRules = buildList {
            if (rulesJson != null) {
                for (index in 0 until rulesJson.length()) {
                    rulesJson.optJSONObject(index)?.let { ruleJson ->
                        decodeRule(ruleJson)?.let(::add)
                    }
                }
            }
        }

        return AlertProfile(
            id = json.optString("id").ifBlank { fallback.id },
            name = json.optString("name").ifBlank { fallback.name },
            description = json.optString("description", fallback.description),
            builtIn = builtIn,
            icon = json.enumOrNull<ProfileIcon>("icon") ?: fallback.icon,
            color = json.enumOrNull<ProfileColor>("color") ?: fallback.color,
            quietHours = QuietHours(
                enabled = quietJson?.optBoolean("enabled", fallback.quietHours.enabled)
                    ?: fallback.quietHours.enabled,
                startMinutes = quietJson?.optInt("startMinutes", fallback.quietHours.startMinutes)
                    ?.coerceIn(0, 1439) ?: fallback.quietHours.startMinutes,
                endMinutes = quietJson?.optInt("endMinutes", fallback.quietHours.endMinutes)
                    ?.coerceIn(0, 1439) ?: fallback.quietHours.endMinutes,
            ),
            activation = ActivationRule(
                enabled = activationJson?.optBoolean("enabled", fallback.activation.enabled)
                    ?: fallback.activation.enabled,
                activity = activationJson?.enumOrNull<ActivityContext>("activity")
                    ?: fallback.activation.activity,
                locationLabel = activationJson?.optString("locationLabel", fallback.activation.locationLabel)
                    ?: fallback.activation.locationLabel,
            ),
            phraseTriggers = buildList {
                if (phraseJson != null) {
                    for (index in 0 until phraseJson.length()) {
                        phraseJson.optString(index).trim().takeIf(String::isNotEmpty)?.let(::add)
                    }
                }
            },
            soundRules = ProfileDefaults.completeRules(decodedRules) + decodedRules.filter { rule ->
                rule.soundId.startsWith("custom:")
            },
        )
    }

    private fun decodeRule(json: JSONObject): SoundRule? {
        val soundId = json.optString("soundId").ifBlank {
            json.enumOrNull<SoundType>("sound")?.id.orEmpty()
        }
        if (soundId.isBlank()) return null
        val fallback = ProfileDefaults.fallbackRule(soundId)
        val hapticPattern = json.enumOrNull<HapticPattern>("hapticPattern") ?: fallback.hapticPattern
        return SoundRule(
            soundId = soundId,
            enabled = json.optBoolean("enabled", fallback.enabled),
            confidenceThreshold = json.optDouble(
                "confidenceThreshold",
                fallback.confidenceThreshold.toDouble(),
            ).toFloat().coerceIn(0.20f, 0.95f),
            priority = json.enumOrNull<AlertPriority>("priority") ?: fallback.priority,
            hapticPattern = hapticPattern,
            hapticStrength = json.enumOrNull<HapticStrength>("hapticStrength") ?: fallback.hapticStrength,
            requiresAcknowledgement = json.optBoolean(
                "requiresAcknowledgement",
                fallback.requiresAcknowledgement,
            ),
            cooldownSeconds = json.optInt("cooldownSeconds", fallback.cooldownSeconds).coerceIn(0, 120),
            customHapticPattern = decodeCustomHaptic(json.optJSONObject("customHapticPattern"))
                ?.takeIf { hapticPattern == HapticPattern.CUSTOM },
        )
    }

    private fun decodeCustomHaptic(json: JSONObject?): CustomHapticPattern? {
        json ?: return null
        val stepsJson = json.optJSONArray("steps") ?: return null
        val steps = buildList {
            for (index in 0 until minOf(stepsJson.length(), CustomHapticPattern.MAX_STEPS)) {
                val step = stepsJson.optJSONObject(index) ?: continue
                add(CustomHapticStep(step.optInt("onMs"), step.optInt("offMs")))
            }
        }
        return CustomHapticPattern(json.optString("name").take(30), steps).takeIf(CustomHapticPattern::isValid)
    }

    private inline fun <reified T : Enum<T>> JSONObject.enumOrNull(key: String): T? {
        val value = optString(key)
        return enumValues<T>().firstOrNull { it.name == value }
    }
}
