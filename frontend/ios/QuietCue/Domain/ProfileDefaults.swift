import Foundation

enum ProfileDefaults {
    static let homeId = "builtin-home"
    private static let workId = "builtin-work-school"
    private static let drivingId = "builtin-driving-transit"
    private static let sleepId = "builtin-sleep-night"
    private static let emergencyId = "builtin-emergency"

    static func all() -> [AlertProfile] {
        [home(), workSchool(), drivingTransit(), sleepNight(), emergency()]
    }

    static func forBuiltIn(_ builtIn: BuiltInProfile) -> AlertProfile {
        switch builtIn {
        case .home: return home()
        case .workSchool: return workSchool()
        case .drivingTransit: return drivingTransit()
        case .sleepNight: return sleepNight()
        case .emergency: return emergency()
        }
    }

    static func newCustom(template: AlertProfile = home()) -> AlertProfile {
        var profile = template
        profile.id = UUID().uuidString.lowercased()
        profile.name = "Custom profile"
        profile.descriptionText = "Personalized alerts for this situation"
        profile.builtIn = nil
        profile.icon = .star
        profile.color = .ocean
        profile.activation = ActivationRule()
        return profile
    }

    static func duplicate(_ profile: AlertProfile) -> AlertProfile {
        var copy = profile
        copy.id = UUID().uuidString.lowercased()
        copy.name = "\(profile.name) copy"
        copy.builtIn = nil
        return copy
    }

    static func completeRules(
        _ rules: [SoundRule],
        soundLibrary: [SoundDefinition] = SoundLibrary.builtIns()
    ) -> [SoundRule] {
        let bySound = Dictionary(rules.map { ($0.soundId, $0) }, uniquingKeysWith: { first, _ in first })
        return soundLibrary.map { sound in
            bySound[sound.id] ?? ruleForSound(sound, enabled: sound.builtInType != nil)
        }
    }

    static func ruleForSound(_ sound: SoundDefinition, enabled: Bool = false) -> SoundRule {
        SoundRule(
            soundId: sound.id,
            enabled: enabled,
            confidenceThreshold: sound.enrollment?.similarityThreshold
                ?? (sound.defaultPriority == .emergency ? 0.45 : 0.60),
            priority: sound.defaultPriority,
            hapticPattern: sound.defaultHapticPattern,
            hapticStrength: sound.defaultHapticStrength,
            requiresAcknowledgement: sound.defaultRequiresAcknowledgement,
            cooldownSeconds: defaultCooldownSeconds(soundId: sound.id, emergency: sound.defaultPriority == .emergency)
        )
    }

    /// Someone calling your name twice in a row should register twice.
    static func defaultCooldownSeconds(soundId: String, emergency: Bool) -> Int {
        if soundId == SoundType.nameCalled.id { return 5 }
        return emergency ? 10 : 20
    }

    static func fallbackRule(soundId: String) -> SoundRule {
        let definition = SoundLibrary.builtIns().first { $0.id == soundId }
            ?? SoundDefinition(id: soundId, displayName: "Custom sound", descriptionText: "Enrolled custom sound")
        return ruleForSound(definition, enabled: definition.builtInType != nil)
    }

    private struct RuleOverrides {
        var threshold: Float? = nil
        var priority: AlertPriority? = nil
        var pattern: HapticPattern? = nil
        var strength: HapticStrength? = nil
        var acknowledgement: Bool? = nil
        var cooldown: Int? = nil
    }

    private static func home() -> AlertProfile {
        AlertProfile(
            id: homeId,
            name: "Home",
            descriptionText: "Everyday household alerts and people nearby",
            builtIn: .home,
            icon: .home,
            color: .teal,
            soundRules: rules(
                disabled: [.carHorn],
                overrides: [
                    .doorbellKnock: RuleOverrides(threshold: 0.55),
                    .babyCrying: RuleOverrides(threshold: 0.50),
                    .kitchenTimer: RuleOverrides(threshold: 0.60, priority: .informational, pattern: .twoShort),
                ]
            )
        )
    }

    private static func workSchool() -> AlertProfile {
        AlertProfile(
            id: workId,
            name: "Work / School",
            descriptionText: "Focused alerts for shared spaces and conversations",
            builtIn: .workSchool,
            icon: .work,
            color: .ocean,
            activation: ActivationRule(activity: .workSchool),
            speechMode: .alwaysOn,
            phraseTriggers: ["front desk"],
            soundRules: rules(
                disabled: [.babyCrying, .kitchenTimer],
                overrides: [
                    .nameCalled: RuleOverrides(threshold: 0.48),
                    .phoneRinging: RuleOverrides(threshold: 0.65, priority: .informational, pattern: .shortPulse),
                ]
            )
        )
    }

    private static func drivingTransit() -> AlertProfile {
        AlertProfile(
            id: drivingId,
            name: "Driving / Transit",
            descriptionText: "Road warnings with fewer nonessential interruptions",
            builtIn: .drivingTransit,
            icon: .drive,
            color: .amber,
            activation: ActivationRule(activity: .drivingTransit),
            soundRules: rules(
                disabled: [.doorbellKnock, .babyCrying, .kitchenTimer, .phoneRinging],
                overrides: [
                    .carHorn: RuleOverrides(
                        threshold: 0.42,
                        priority: .emergency,
                        pattern: .urgentRepeat,
                        strength: .strong,
                        acknowledgement: true,
                        cooldown: 8
                    ),
                    .siren: RuleOverrides(threshold: 0.45),
                ]
            )
        )
    }

    private static func sleepNight() -> AlertProfile {
        AlertProfile(
            id: sleepId,
            name: "Sleep / Night",
            descriptionText: "Only high-value alerts during rest",
            builtIn: .sleepNight,
            icon: .sleep,
            color: .violet,
            quietHours: QuietHours(enabled: true, startMinutes: 22 * 60, endMinutes: 7 * 60),
            activation: ActivationRule(activity: .sleeping),
            speechMode: .off,
            soundRules: rules(
                disabled: [.doorbellKnock, .carHorn, .kitchenTimer, .phoneRinging],
                overrides: [
                    .babyCrying: RuleOverrides(
                        threshold: 0.42,
                        priority: .emergency,
                        pattern: .urgentRepeat,
                        strength: .strong,
                        acknowledgement: true
                    ),
                ]
            )
        )
    }

    private static func emergency() -> AlertProfile {
        AlertProfile(
            id: emergencyId,
            name: "Emergency",
            descriptionText: "Persistent safety alerts with lower detection thresholds",
            builtIn: .emergency,
            icon: .emergency,
            color: .coral,
            soundRules: SoundType.allCases.map { sound in
                let critical = sound.safetyCritical
                var rule = baseRule(sound)
                rule.enabled = critical
                rule.confidenceThreshold = critical ? 0.35 : 0.65
                rule.priority = critical ? .emergency : .attention
                rule.hapticPattern = critical ? .urgentRepeat : .longPulse
                rule.hapticStrength = .strong
                rule.requiresAcknowledgement = critical
                rule.cooldownSeconds = critical || sound == .nameCalled ? 5 : 20
                return rule
            }
        )
    }

    private static func rules(disabled: Set<SoundType>, overrides: [SoundType: RuleOverrides]) -> [SoundRule] {
        SoundType.allCases.map { sound in
            var rule = baseRule(sound)
            let override = overrides[sound]
            rule.enabled = !disabled.contains(sound)
            rule.confidenceThreshold = override?.threshold ?? rule.confidenceThreshold
            rule.priority = override?.priority ?? rule.priority
            rule.hapticPattern = override?.pattern ?? rule.hapticPattern
            rule.hapticStrength = override?.strength ?? rule.hapticStrength
            rule.requiresAcknowledgement = override?.acknowledgement ?? rule.requiresAcknowledgement
            rule.cooldownSeconds = override?.cooldown ?? rule.cooldownSeconds
            return rule
        }
    }

    private static func baseRule(_ sound: SoundType) -> SoundRule {
        let emergency = sound == .fireAlarm || sound == .siren
        return SoundRule(
            soundId: sound.id,
            enabled: true,
            confidenceThreshold: emergency ? 0.45 : 0.60,
            priority: emergency ? .emergency : .attention,
            hapticPattern: emergency ? .urgentRepeat : .longPulse,
            hapticStrength: emergency ? .strong : .standard,
            requiresAcknowledgement: emergency,
            cooldownSeconds: defaultCooldownSeconds(soundId: sound.id, emergency: emergency)
        )
    }
}
