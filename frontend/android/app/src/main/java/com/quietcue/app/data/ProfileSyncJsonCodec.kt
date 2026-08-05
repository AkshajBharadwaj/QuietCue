package com.quietcue.app.data

import com.quietcue.app.domain.ProfileCatalog
import org.json.JSONArray
import org.json.JSONObject

object ProfileSyncJsonCodec {
    fun encode(catalog: ProfileCatalog): String {
        val profile = requireNotNull(catalog.activeProfile)
        val soundsById = catalog.soundLibrary.associateBy { it.id }
        return JSONObject()
            .put("id", profile.id)
            .put("name", profile.name)
            .put("phrase_triggers", JSONArray(profile.phraseTriggers))
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
                        put(
                            JSONObject()
                                .put("event", rule.soundId)
                                .put("enabled", rule.enabled)
                                .put("confidence_threshold", rule.confidenceThreshold.toDouble())
                                .put("category", rule.priority.name.lowercase())
                                .put("pattern", rule.hapticPattern.name.lowercase())
                                .put("strength", rule.hapticStrength.name.lowercase())
                                .put("requires_ack", rule.requiresAcknowledgement)
                                .put("cooldown_seconds", rule.cooldownSeconds),
                        )
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
            .toString()
    }
}
