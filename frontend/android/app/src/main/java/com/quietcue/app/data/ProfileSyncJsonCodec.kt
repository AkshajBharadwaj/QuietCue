package com.quietcue.app.data

import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.ProfileCatalog
import org.json.JSONArray
import org.json.JSONObject

object ProfileSyncJsonCodec {
    fun encode(catalog: ProfileCatalog, memoryBank: MemoryBank = MemoryBank()): String {
        val profile = requireNotNull(catalog.activeProfile)
        val soundsById = catalog.soundLibrary.associateBy { it.id }
        return JSONObject()
            .put("id", profile.id)
            .put("name", profile.name)
            .put("phrase_triggers", JSONArray(profile.phraseTriggers))
            .put("speech_context", encodeSpeechContext(memoryBank))
            .put(
                "quiet_hours",
                JSONObject()
                    .put("enabled", profile.quietHours.enabled)
                    .put("start_minutes", profile.quietHours.startMinutes)
                    .put("end_minutes", profile.quietHours.endMinutes),
            )
            .put(
                "sound_rules",
                JSONArray().apply {
                    profile.soundRules.forEach { rule ->
                        val ruleJson = JSONObject()
                                .put("event", rule.soundId)
                                .put("enabled", rule.enabled)
                                .put("confidence_threshold", rule.confidenceThreshold.toDouble())
                                .put("category", rule.priority.name.lowercase())
                                .put("pattern", rule.hapticPattern.name.lowercase())
                                .put("strength", rule.hapticStrength.name.lowercase())
                                .put("requires_ack", rule.requiresAcknowledgement)
                                .put("cooldown_seconds", rule.cooldownSeconds)
                        rule.customHapticPattern?.takeIf { rule.hapticPattern == HapticPattern.CUSTOM }?.let { custom ->
                            ruleJson.put(
                                "custom_pattern",
                                JSONObject()
                                    .put("name", custom.name)
                                    .put(
                                        "steps",
                                        JSONArray().apply {
                                            custom.steps.forEach { step ->
                                                put(
                                                    JSONObject()
                                                        .put("on_ms", step.onMs)
                                                        .put("off_ms", step.offMs),
                                                )
                                            }
                                        },
                                    ),
                            )
                        }
                        put(ruleJson)
                    }
                },
            )
            .put(
                "custom_sounds",
                JSONArray().apply {
                    profile.soundRules.forEach { rule ->
                        val sound = soundsById[rule.soundId] ?: return@forEach
                        val enrollment = sound.enrollment ?: return@forEach
                        put(
                            JSONObject()
                                .put("event", sound.id)
                                .put("label", sound.displayName)
                                .put("prototype", JSONArray(enrollment.prototype))
                                .put("similarity_threshold", enrollment.similarityThreshold.toDouble())
                                .put("matcher_version", enrollment.matcherVersion),
                        )
                    }
                },
            )
            .put(
                "classifier_label_rules",
                JSONArray().apply {
                    profile.soundRules.forEach { rule ->
                        val sound = soundsById[rule.soundId] ?: return@forEach
                        sound.classifierLabels.forEach { label ->
                            put(JSONObject().put("event", sound.id).put("label", label))
                        }
                    }
                },
            )
            .toString()
    }

    private fun encodeSpeechContext(bank: MemoryBank): JSONObject = JSONObject()
        .put(
            "identity",
            bank.identity?.let { identity ->
                JSONObject()
                    .put("name", identity.displayName)
                    .put("pronunciation", identity.pronunciation)
                    .put("aliases", JSONArray(identity.aliases))
                    .put("recognition_phrases", JSONArray(identity.recognitionPhrases))
            },
        )
        .put(
            "people",
            JSONArray().apply {
                bank.people.forEach { person ->
                    put(
                        JSONObject()
                            .put("name", person.name)
                            .put("relationship", person.relationship)
                            .put("pronunciation", person.pronunciation)
                            .put("aliases", JSONArray(person.aliases))
                            .put("notes", person.notes),
                    )
                }
            },
        )
        .put(
            "contexts",
            JSONArray().apply {
                bank.contexts.forEach { context ->
                    put(
                        JSONObject()
                            .put("title", context.title)
                            .put("details", context.details),
                    )
                }
            },
        )
}
