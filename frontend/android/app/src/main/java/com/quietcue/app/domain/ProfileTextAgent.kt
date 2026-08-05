package com.quietcue.app.domain

data class ProfileAgentResult(
    val profile: AlertProfile,
    val explanation: String,
    val assumptions: List<String>,
)

fun interface ProfileGenerationService {
    fun generate(
        description: String,
        activeProfile: AlertProfile,
        soundLibrary: List<SoundDefinition>,
    ): ProfileAgentResult
}

class LocalProfileTextAgent : ProfileGenerationService {
    override fun generate(
        description: String,
        activeProfile: AlertProfile,
        soundLibrary: List<SoundDefinition>,
    ): ProfileAgentResult {
        val prompt = description.trim()
        require(prompt.isNotBlank()) { "Describe the place or situation first" }
        val normalized = prompt.lowercase()
        val template = when {
            normalized.containsAny("sleep", "hotel", "night", "bed") ->
                ProfileDefaults.forBuiltIn(BuiltInProfile.SLEEP_NIGHT)
            normalized.containsAny("drive", "driving", "car", "transit", "train", "bus") ->
                ProfileDefaults.forBuiltIn(BuiltInProfile.DRIVING_TRANSIT)
            normalized.containsAny("work", "office", "school", "class", "library", "study") ->
                ProfileDefaults.forBuiltIn(BuiltInProfile.WORK_SCHOOL)
            normalized.containsAny("emergency only", "critical alerts only") ->
                ProfileDefaults.forBuiltIn(BuiltInProfile.EMERGENCY)
            else -> activeProfile
        }
        var draft = ProfileDefaults.newCustom(template).copy(
            name = suggestedName(normalized),
            description = prompt.take(120),
            soundRules = ProfileDefaults.completeRules(template.soundRules, soundLibrary),
        )

        val mentioned = soundLibrary.filter { sound -> normalized.mentions(sound) }.map(SoundDefinition::id).toSet()
        val ignored = soundLibrary.filter { sound -> normalized.ignores(sound) }.map(SoundDefinition::id).toSet()
        val onlyRequested = normalized.containsAny("only alert", "only notify", "nothing except", "just alert")
        val safetyIds = soundLibrary.filter(SoundDefinition::safetyCritical).map(SoundDefinition::id).toSet()
        draft = draft.copy(
            soundRules = draft.soundRules.map { rule ->
                when {
                    rule.soundId in ignored && rule.soundId !in safetyIds -> rule.copy(enabled = false)
                    rule.soundId in mentioned -> rule.copy(enabled = true)
                    onlyRequested && rule.soundId !in safetyIds -> rule.copy(enabled = false)
                    else -> rule
                }
            },
            phraseTriggers = (draft.phraseTriggers + extractPhrases(prompt)).distinct(),
            activation = draft.activation.copy(
                enabled = normalized.containsAny("when i arrive", "at the", "inside", "entering"),
                locationLabel = locationLabel(normalized),
            ),
        )

        val enabledNames = draft.soundRules.filter(SoundRule::enabled).mapNotNull { rule ->
            soundLibrary.firstOrNull { it.id == rule.soundId }?.displayName
        }
        val assumptions = buildList {
            add("Fire alarms, sirens, and other safety-critical sounds stay enabled unless reviewed manually.")
            if (mentioned.isEmpty()) add("No exact sound names were found, so the closest built-in profile was used.")
            if (draft.phraseTriggers.isEmpty()) add("No name or phrase trigger was inferred.")
            add("Review thresholds and haptics before activating this generated profile.")
        }
        return ProfileAgentResult(
            profile = draft,
            explanation = "Created ${draft.name} with ${enabledNames.size} enabled sounds: " +
                enabledNames.take(5).joinToString() + if (enabledNames.size > 5) ", and more." else ".",
            assumptions = assumptions,
        )
    }

    private fun suggestedName(prompt: String): String = when {
        "library" in prompt -> "Library visit"
        "coffee" in prompt || "cafe" in prompt -> "Coffee shop"
        "airport" in prompt -> "Airport"
        "hotel" in prompt -> "Hotel stay"
        prompt.containsAny("drive", "car", "transit") -> "Travel"
        prompt.containsAny("work", "office") -> "Work visit"
        prompt.containsAny("school", "class") -> "Class"
        else -> "Situation profile"
    }

    private fun extractPhrases(prompt: String): List<String> {
        val quoted = Regex("[\\\"']([^\\\"']{1,40})[\\\"']")
            .findAll(prompt)
            .map { it.groupValues[1].trim() }
            .filter(String::isNotBlank)
            .toList()
        val named = Regex("(?i)my name is\\s+([a-z][a-z -]{0,30})")
            .find(prompt)
            ?.groupValues
            ?.getOrNull(1)
            ?.trim()
            ?.let(::listOf)
            .orEmpty()
        return (quoted + named).distinct()
    }

    private fun locationLabel(prompt: String): String = when {
        "library" in prompt -> "Library"
        "coffee" in prompt || "cafe" in prompt -> "Coffee shop"
        "airport" in prompt -> "Airport"
        "hotel" in prompt -> "Hotel"
        "office" in prompt || "work" in prompt -> "Work"
        "school" in prompt || "class" in prompt -> "School"
        else -> "Custom area"
    }

    private fun String.mentions(sound: SoundDefinition): Boolean {
        val aliases = aliasesFor(sound)
        return aliases.any { alias -> contains(alias) }
    }

    private fun String.ignores(sound: SoundDefinition): Boolean {
        val aliases = aliasesFor(sound)
        return aliases.any { alias ->
            contains("ignore $alias") || contains("without $alias") || contains("no $alias")
        }
    }

    private fun aliasesFor(sound: SoundDefinition): Set<String> = buildSet {
        add(sound.displayName.lowercase())
        add(sound.id.removePrefix("custom:").replace('_', ' ').lowercase())
        when (sound.builtInType) {
            SoundType.FIRE_ALARM -> addAll(listOf("fire alarm", "smoke alarm"))
            SoundType.DOORBELL_KNOCK -> addAll(listOf("doorbell", "knock", "door"))
            SoundType.CAR_HORN -> addAll(listOf("car horn", "horn", "honking"))
            SoundType.SIREN -> addAll(listOf("siren", "emergency vehicle"))
            SoundType.NAME_CALLED -> addAll(listOf("my name", "name called", "someone calls"))
            SoundType.BABY_CRYING -> addAll(listOf("baby", "crying"))
            SoundType.KITCHEN_TIMER -> addAll(listOf("timer", "kitchen timer"))
            SoundType.PHONE_RINGING -> addAll(listOf("phone", "ringtone", "phone ringing"))
            null -> Unit
        }
    }

    private fun String.containsAny(vararg values: String): Boolean = values.any(::contains)
}
