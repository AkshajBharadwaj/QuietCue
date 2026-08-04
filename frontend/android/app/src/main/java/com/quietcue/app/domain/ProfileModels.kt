package com.quietcue.app.domain

enum class SoundType(
    val displayName: String,
    val description: String,
    val safetyCritical: Boolean = false,
) {
    FIRE_ALARM(
        displayName = "Fire or smoke alarm",
        description = "Smoke detectors, fire alarms, and evacuation tones",
        safetyCritical = true,
    ),
    DOORBELL_KNOCK(
        displayName = "Doorbell or knock",
        description = "Door chimes and knocking at a nearby door",
    ),
    CAR_HORN(
        displayName = "Car horn",
        description = "Nearby vehicle horns and warning honks",
        safetyCritical = true,
    ),
    SIREN(
        displayName = "Siren",
        description = "Emergency vehicle and civil-warning sirens",
        safetyCritical = true,
    ),
    NAME_CALLED(
        displayName = "Name or phrase called",
        description = "Speech containing one of your configured phrases",
    ),
    BABY_CRYING(
        displayName = "Baby crying",
        description = "Sustained infant crying nearby",
    ),
    KITCHEN_TIMER(
        displayName = "Kitchen timer",
        description = "Timer beeps and common appliance alerts",
    ),
    PHONE_RINGING(
        displayName = "Phone ringing",
        description = "Phone calls and repeated ringtone patterns",
    ),
}

enum class AlertPriority(val displayName: String) {
    INFORMATIONAL("Informational"),
    ATTENTION("Attention"),
    EMERGENCY("Emergency"),
}

enum class HapticPattern(val displayName: String, val description: String) {
    SHORT_PULSE("Short pulse", "One quick pulse"),
    TWO_SHORT("Two short", "Two distinct quick pulses"),
    LONG_PULSE("Long pulse", "One sustained attention pulse"),
    URGENT_REPEAT("Urgent repeat", "Repeated pulses until acknowledged or timed out"),
}

enum class HapticStrength(val displayName: String) {
    GENTLE("Gentle"),
    STANDARD("Standard"),
    STRONG("Strong"),
}

enum class ActivityContext(val displayName: String) {
    ANY("Any activity"),
    HOME("At home"),
    WORK_SCHOOL("Work or school"),
    DRIVING_TRANSIT("Driving or transit"),
    SLEEPING("Sleeping"),
}

enum class ProfileIcon(val displayName: String) {
    HOME("Home"),
    WORK("Work"),
    DRIVE("Transit"),
    SLEEP("Night"),
    EMERGENCY("Emergency"),
    STAR("Star"),
    HEART("Heart"),
}

enum class ProfileColor(val displayName: String) {
    OCEAN("Ocean"),
    TEAL("Teal"),
    AMBER("Amber"),
    VIOLET("Violet"),
    CORAL("Coral"),
    SLATE("Slate"),
}

enum class BuiltInProfile {
    HOME,
    WORK_SCHOOL,
    DRIVING_TRANSIT,
    SLEEP_NIGHT,
    EMERGENCY,
}

data class QuietHours(
    val enabled: Boolean = false,
    val startMinutes: Int = 22 * 60,
    val endMinutes: Int = 7 * 60,
) {
    init {
        require(startMinutes in 0..1439)
        require(endMinutes in 0..1439)
    }
}

data class ActivationRule(
    val enabled: Boolean = false,
    val activity: ActivityContext = ActivityContext.ANY,
    val locationLabel: String = "",
)

data class SoundRule(
    val sound: SoundType,
    val enabled: Boolean,
    val confidenceThreshold: Float,
    val priority: AlertPriority,
    val hapticPattern: HapticPattern,
    val hapticStrength: HapticStrength,
    val requiresAcknowledgement: Boolean,
    val cooldownSeconds: Int,
)

data class AlertProfile(
    val id: String,
    val name: String,
    val description: String,
    val builtIn: BuiltInProfile? = null,
    val icon: ProfileIcon = ProfileIcon.STAR,
    val color: ProfileColor = ProfileColor.OCEAN,
    val quietHours: QuietHours = QuietHours(),
    val activation: ActivationRule = ActivationRule(),
    val phraseTriggers: List<String> = emptyList(),
    val soundRules: List<SoundRule>,
) {
    val isBuiltIn: Boolean get() = builtIn != null
    val enabledSoundCount: Int get() = soundRules.count(SoundRule::enabled)
}

data class ProfileCatalog(
    val profiles: List<AlertProfile> = emptyList(),
    val activeProfileId: String = "",
) {
    val activeProfile: AlertProfile?
        get() = profiles.firstOrNull { it.id == activeProfileId } ?: profiles.firstOrNull()
}
