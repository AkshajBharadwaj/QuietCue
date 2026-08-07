package com.quietcue.app.domain

object ProfileValidator {
    fun validate(
        profile: AlertProfile,
        soundLibrary: List<SoundDefinition> = SoundLibrary.builtIns(),
    ): List<String> = buildList {
        if (profile.name.isBlank()) add("Give the profile a name.")
        if (profile.name.trim().length > 40) add("Keep the profile name to 40 characters or fewer.")
        if (profile.description.length > 120) add("Keep the description to 120 characters or fewer.")
        if (profile.soundRules.none(SoundRule::enabled)) add("Enable at least one sound.")
        if (profile.soundRules.map(SoundRule::soundId).toSet() != soundLibrary.map(SoundDefinition::id).toSet()) {
            add("The profile must contain one rule for every supported sound.")
        }
        if (profile.soundRules.any { it.confidenceThreshold !in 0.20f..0.95f }) {
            add("Confidence thresholds must be between 20% and 95%.")
        }
        if (profile.soundRules.any { it.cooldownSeconds !in 0..120 }) {
            add("Cooldowns must be between 0 and 120 seconds.")
        }
        if (profile.soundRules.any {
                it.hapticPattern == HapticPattern.CUSTOM &&
                    it.customHapticPattern?.isValid() != true
            }
        ) {
            add("Every custom haptic must contain one to six valid touch-recorded pulses.")
        }
        if (profile.phraseTriggers.any { it.length > 40 }) {
            add("Each name or phrase trigger must be 40 characters or fewer.")
        }
    }
}

fun formatTime(minutes: Int): String {
    val hour24 = minutes / 60
    val minute = minutes % 60
    val suffix = if (hour24 < 12) "AM" else "PM"
    val hour12 = when (val value = hour24 % 12) {
        0 -> 12
        else -> value
    }
    return "%d:%02d %s".format(hour12, minute, suffix)
}

fun parseTime(value: String): Int? {
    val match = Regex("^\\s*(\\d{1,2}):(\\d{2})\\s*([AaPp][Mm])?\\s*$").matchEntire(value) ?: return null
    val rawHour = match.groupValues[1].toIntOrNull() ?: return null
    val minute = match.groupValues[2].toIntOrNull()?.takeIf { it in 0..59 } ?: return null
    val suffix = match.groupValues[3].uppercase()
    val hour24 = when {
        suffix.isEmpty() && rawHour in 0..23 -> rawHour
        suffix == "AM" && rawHour in 1..12 -> if (rawHour == 12) 0 else rawHour
        suffix == "PM" && rawHour in 1..12 -> if (rawHour == 12) 12 else rawHour + 12
        else -> return null
    }
    return hour24 * 60 + minute
}
