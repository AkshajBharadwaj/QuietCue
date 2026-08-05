package com.quietcue.app.domain

import java.util.UUID

object ProfileDefaults {
    const val HOME_ID = "builtin-home"
    private const val WORK_ID = "builtin-work-school"
    private const val DRIVING_ID = "builtin-driving-transit"
    private const val SLEEP_ID = "builtin-sleep-night"
    private const val EMERGENCY_ID = "builtin-emergency"

    fun all(): List<AlertProfile> = listOf(
        home(),
        workSchool(),
        drivingTransit(),
        sleepNight(),
        emergency(),
    )

    fun forBuiltIn(builtIn: BuiltInProfile): AlertProfile = when (builtIn) {
        BuiltInProfile.HOME -> home()
        BuiltInProfile.WORK_SCHOOL -> workSchool()
        BuiltInProfile.DRIVING_TRANSIT -> drivingTransit()
        BuiltInProfile.SLEEP_NIGHT -> sleepNight()
        BuiltInProfile.EMERGENCY -> emergency()
    }

    fun newCustom(template: AlertProfile = home()): AlertProfile = template.copy(
        id = UUID.randomUUID().toString(),
        name = "Custom profile",
        description = "Personalized alerts for this situation",
        builtIn = null,
        icon = ProfileIcon.STAR,
        color = ProfileColor.OCEAN,
        activation = ActivationRule(),
    )

    fun duplicate(profile: AlertProfile): AlertProfile = profile.copy(
        id = UUID.randomUUID().toString(),
        name = "${profile.name} copy",
        builtIn = null,
    )

    fun completeRules(
        rules: List<SoundRule>,
        soundLibrary: List<SoundDefinition> = SoundLibrary.builtIns(),
    ): List<SoundRule> {
        val rulesBySound = rules.associateBy(SoundRule::soundId)
        return soundLibrary.map { sound ->
            rulesBySound[sound.id] ?: ruleForSound(sound, enabled = sound.builtInType != null)
        }
    }

    fun ruleForSound(sound: SoundDefinition, enabled: Boolean = false): SoundRule = SoundRule(
        soundId = sound.id,
        enabled = enabled,
        confidenceThreshold = sound.enrollment?.similarityThreshold
            ?: if (sound.defaultPriority == AlertPriority.EMERGENCY) 0.45f else 0.60f,
        priority = sound.defaultPriority,
        hapticPattern = sound.defaultHapticPattern,
        hapticStrength = sound.defaultHapticStrength,
        requiresAcknowledgement = sound.defaultRequiresAcknowledgement,
        cooldownSeconds = if (sound.defaultPriority == AlertPriority.EMERGENCY) 10 else 20,
    )

    fun fallbackRule(soundId: String): SoundRule {
        val definition = SoundLibrary.builtIns().firstOrNull { it.id == soundId }
            ?: SoundDefinition(soundId, "Custom sound", "Enrolled custom sound")
        return ruleForSound(definition, enabled = definition.builtInType != null)
    }

    private fun home(): AlertProfile = AlertProfile(
        id = HOME_ID,
        name = "Home",
        description = "Everyday household alerts and people nearby",
        builtIn = BuiltInProfile.HOME,
        icon = ProfileIcon.HOME,
        color = ProfileColor.TEAL,
        soundRules = rules(
            disabled = setOf(SoundType.CAR_HORN),
            overrides = mapOf(
                SoundType.DOORBELL_KNOCK to RuleOverrides(threshold = 0.55f),
                SoundType.BABY_CRYING to RuleOverrides(threshold = 0.50f),
                SoundType.KITCHEN_TIMER to RuleOverrides(
                    threshold = 0.60f,
                    priority = AlertPriority.INFORMATIONAL,
                    pattern = HapticPattern.TWO_SHORT,
                ),
            ),
        ),
    )

    private fun workSchool(): AlertProfile = AlertProfile(
        id = WORK_ID,
        name = "Work / School",
        description = "Focused alerts for shared spaces and conversations",
        builtIn = BuiltInProfile.WORK_SCHOOL,
        icon = ProfileIcon.WORK,
        color = ProfileColor.OCEAN,
        activation = ActivationRule(activity = ActivityContext.WORK_SCHOOL),
        soundRules = rules(
            disabled = setOf(SoundType.BABY_CRYING, SoundType.KITCHEN_TIMER),
            overrides = mapOf(
                SoundType.NAME_CALLED to RuleOverrides(threshold = 0.48f),
                SoundType.PHONE_RINGING to RuleOverrides(
                    threshold = 0.65f,
                    priority = AlertPriority.INFORMATIONAL,
                    pattern = HapticPattern.SHORT_PULSE,
                ),
            ),
        ),
    )

    private fun drivingTransit(): AlertProfile = AlertProfile(
        id = DRIVING_ID,
        name = "Driving / Transit",
        description = "Road warnings with fewer nonessential interruptions",
        builtIn = BuiltInProfile.DRIVING_TRANSIT,
        icon = ProfileIcon.DRIVE,
        color = ProfileColor.AMBER,
        activation = ActivationRule(activity = ActivityContext.DRIVING_TRANSIT),
        soundRules = rules(
            disabled = setOf(
                SoundType.DOORBELL_KNOCK,
                SoundType.BABY_CRYING,
                SoundType.KITCHEN_TIMER,
                SoundType.PHONE_RINGING,
            ),
            overrides = mapOf(
                SoundType.CAR_HORN to RuleOverrides(
                    threshold = 0.42f,
                    priority = AlertPriority.EMERGENCY,
                    pattern = HapticPattern.URGENT_REPEAT,
                    strength = HapticStrength.STRONG,
                    acknowledgement = true,
                    cooldown = 8,
                ),
                SoundType.SIREN to RuleOverrides(threshold = 0.45f),
            ),
        ),
    )

    private fun sleepNight(): AlertProfile = AlertProfile(
        id = SLEEP_ID,
        name = "Sleep / Night",
        description = "Only high-value alerts during rest",
        builtIn = BuiltInProfile.SLEEP_NIGHT,
        icon = ProfileIcon.SLEEP,
        color = ProfileColor.VIOLET,
        quietHours = QuietHours(enabled = true, startMinutes = 22 * 60, endMinutes = 7 * 60),
        activation = ActivationRule(activity = ActivityContext.SLEEPING),
        soundRules = rules(
            disabled = setOf(
                SoundType.DOORBELL_KNOCK,
                SoundType.CAR_HORN,
                SoundType.KITCHEN_TIMER,
                SoundType.PHONE_RINGING,
            ),
            overrides = mapOf(
                SoundType.BABY_CRYING to RuleOverrides(
                    threshold = 0.42f,
                    priority = AlertPriority.EMERGENCY,
                    pattern = HapticPattern.URGENT_REPEAT,
                    strength = HapticStrength.STRONG,
                    acknowledgement = true,
                ),
            ),
        ),
    )

    private fun emergency(): AlertProfile = AlertProfile(
        id = EMERGENCY_ID,
        name = "Emergency",
        description = "Persistent safety alerts with lower detection thresholds",
        builtIn = BuiltInProfile.EMERGENCY,
        icon = ProfileIcon.EMERGENCY,
        color = ProfileColor.CORAL,
        soundRules = SoundType.entries.map { sound ->
            val isCritical = sound.safetyCritical
            baseRule(sound).copy(
                enabled = isCritical,
                confidenceThreshold = if (isCritical) 0.35f else 0.65f,
                priority = if (isCritical) AlertPriority.EMERGENCY else AlertPriority.ATTENTION,
                hapticPattern = if (isCritical) HapticPattern.URGENT_REPEAT else HapticPattern.LONG_PULSE,
                hapticStrength = HapticStrength.STRONG,
                requiresAcknowledgement = isCritical,
                cooldownSeconds = if (isCritical) 5 else 20,
            )
        },
    )

    private data class RuleOverrides(
        val threshold: Float? = null,
        val priority: AlertPriority? = null,
        val pattern: HapticPattern? = null,
        val strength: HapticStrength? = null,
        val acknowledgement: Boolean? = null,
        val cooldown: Int? = null,
    )

    private fun rules(
        disabled: Set<SoundType>,
        overrides: Map<SoundType, RuleOverrides>,
    ): List<SoundRule> = SoundType.entries.map { sound ->
        val base = baseRule(sound)
        val override = overrides[sound]
        base.copy(
            enabled = sound !in disabled,
            confidenceThreshold = override?.threshold ?: base.confidenceThreshold,
            priority = override?.priority ?: base.priority,
            hapticPattern = override?.pattern ?: base.hapticPattern,
            hapticStrength = override?.strength ?: base.hapticStrength,
            requiresAcknowledgement = override?.acknowledgement ?: base.requiresAcknowledgement,
            cooldownSeconds = override?.cooldown ?: base.cooldownSeconds,
        )
    }

    private fun baseRule(sound: SoundType): SoundRule {
        val emergency = sound == SoundType.FIRE_ALARM || sound == SoundType.SIREN
        return SoundRule(
            soundId = sound.id,
            enabled = true,
            confidenceThreshold = if (emergency) 0.45f else 0.60f,
            priority = if (emergency) AlertPriority.EMERGENCY else AlertPriority.ATTENTION,
            hapticPattern = if (emergency) HapticPattern.URGENT_REPEAT else HapticPattern.LONG_PULSE,
            hapticStrength = if (emergency) HapticStrength.STRONG else HapticStrength.STANDARD,
            requiresAcknowledgement = emergency,
            cooldownSeconds = if (emergency) 10 else 20,
        )
    }
}
