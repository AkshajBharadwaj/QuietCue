import Foundation

/// Built-in sound events. `id` values match the hub's event names exactly.
enum SoundType: String, CaseIterable, Codable {
    case fireAlarm = "fire_alarm"
    case doorbellKnock = "doorbell_knock"
    case carHorn = "car_horn"
    case siren = "siren"
    case nameCalled = "name_called"
    case babyCrying = "baby_crying"
    case kitchenTimer = "kitchen_timer"
    case phoneRinging = "phone_ringing"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .fireAlarm: return "Fire or smoke alarm"
        case .doorbellKnock: return "Doorbell or knock"
        case .carHorn: return "Car horn"
        case .siren: return "Siren"
        case .nameCalled: return "Name or phrase called"
        case .babyCrying: return "Baby crying"
        case .kitchenTimer: return "Kitchen timer"
        case .phoneRinging: return "Phone ringing"
        }
    }

    var descriptionText: String {
        switch self {
        case .fireAlarm: return "Smoke detectors, fire alarms, and evacuation tones"
        case .doorbellKnock: return "Door chimes and knocking at a nearby door"
        case .carHorn: return "Nearby vehicle horns and warning honks"
        case .siren: return "Emergency vehicle and civil-warning sirens"
        case .nameCalled: return "Speech containing one of your configured phrases"
        case .babyCrying: return "Sustained infant crying nearby"
        case .kitchenTimer: return "Timer beeps and common appliance alerts"
        case .phoneRinging: return "Phone calls and repeated ringtone patterns"
        }
    }

    var safetyCritical: Bool {
        switch self {
        case .fireAlarm, .carHorn, .siren: return true
        default: return false
        }
    }
}

enum AlertPriority: String, CaseIterable, Codable {
    case informational
    case attention
    case emergency

    var displayName: String {
        switch self {
        case .informational: return "Informational"
        case .attention: return "Attention"
        case .emergency: return "Emergency"
        }
    }
}

enum HapticPattern: String, CaseIterable, Codable {
    case shortPulse = "short_pulse"
    case twoShort = "two_short"
    case longPulse = "long_pulse"
    case urgentRepeat = "urgent_repeat"
    case custom

    var displayName: String {
        switch self {
        case .shortPulse: return "Short pulse"
        case .twoShort: return "Two short"
        case .longPulse: return "Long pulse"
        case .urgentRepeat: return "Urgent repeat"
        case .custom: return "Custom"
        }
    }

    var descriptionText: String {
        switch self {
        case .shortPulse: return "One quick pulse"
        case .twoShort: return "Two distinct quick pulses"
        case .longPulse: return "One sustained attention pulse"
        case .urgentRepeat: return "Repeated pulses until acknowledged or timed out"
        case .custom: return "A touch-recorded personal vibration"
        }
    }
}

enum HapticStrength: String, CaseIterable, Codable {
    case gentle
    case standard
    case strong

    var displayName: String { rawValue.capitalized }
}

struct CustomHapticStep: Codable, Equatable, Hashable {
    static let minOnMs = 100
    static let minOffMs = 80
    static let maxPhaseMs = 2_000

    var onMs: Int
    var offMs: Int

    var isValid: Bool {
        (Self.minOnMs...Self.maxPhaseMs).contains(onMs) && (Self.minOffMs...Self.maxPhaseMs).contains(offMs)
    }
}

struct CustomHapticPattern: Codable, Equatable, Hashable {
    static let maxSteps = 6
    static let maxTotalMs = 10_000

    var name: String
    var steps: [CustomHapticStep]

    var totalDurationMs: Int { steps.reduce(0) { $0 + $1.onMs + $1.offMs } }
    var encodedSteps: String { steps.map { "\($0.onMs),\($0.offMs)" }.joined(separator: ";") }

    var isValid: Bool {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed.count <= 30 &&
            (1...Self.maxSteps).contains(steps.count) && steps.allSatisfy(\.isValid) &&
            totalDurationMs <= Self.maxTotalMs
    }
}

struct SoundEnrollment: Codable, Equatable, Hashable {
    var prototype: [Float]
    var prototypes: [[Float]]
    var sampleRmsDbfs: [Float] = []
    var similarityThreshold: Float
    var positiveSampleCount: Int
    var backgroundSimilarity: Float
    var createdAtEpochMs: Int64
    var matcherVersion: Int = 4
}

struct SoundDefinition: Codable, Equatable, Hashable, Identifiable {
    var id: String
    var displayName: String
    var descriptionText: String
    var safetyCritical: Bool = false
    var builtInType: SoundType? = nil
    var defaultPriority: AlertPriority = .attention
    var defaultHapticPattern: HapticPattern = .longPulse
    var defaultHapticStrength: HapticStrength = .standard
    var defaultRequiresAcknowledgement: Bool = false
    var enrollment: SoundEnrollment? = nil
    var classifierLabels: [String] = []

    var isEnrolled: Bool { enrollment != nil }
    var isCustom: Bool { isEnrolled || !classifierLabels.isEmpty }
}

enum SoundLibrary {
    static func builtIns() -> [SoundDefinition] {
        SoundType.allCases.map { sound in
            let emergency = sound == .fireAlarm || sound == .siren
            return SoundDefinition(
                id: sound.id,
                displayName: sound.displayName,
                descriptionText: sound.descriptionText,
                safetyCritical: sound.safetyCritical,
                builtInType: sound,
                defaultPriority: emergency ? .emergency : .attention,
                defaultHapticPattern: emergency ? .urgentRepeat : .longPulse,
                defaultHapticStrength: emergency ? .strong : .standard,
                defaultRequiresAcknowledgement: emergency
            )
        }
    }

    static func complete(_ customSounds: [SoundDefinition]) -> [SoundDefinition] {
        let builtInIds = Set(SoundType.allCases.map(\.id))
        var seen = Set<String>()
        let customs = customSounds.filter { sound in
            guard !builtInIds.contains(sound.id), sound.id.hasPrefix("custom:") else { return false }
            return seen.insert(sound.id).inserted
        }
        return builtIns() + customs
    }
}

enum ActivityContext: String, CaseIterable, Codable {
    case any
    case home
    case workSchool = "work_school"
    case drivingTransit = "driving_transit"
    case sleeping

    var displayName: String {
        switch self {
        case .any: return "Any activity"
        case .home: return "At home"
        case .workSchool: return "Work or school"
        case .drivingTransit: return "Driving or transit"
        case .sleeping: return "Sleeping"
        }
    }
}

enum ProfileIcon: String, CaseIterable, Codable {
    case home, work, drive, sleep, emergency, star, heart

    var displayName: String {
        switch self {
        case .home: return "Home"
        case .work: return "Work"
        case .drive: return "Transit"
        case .sleep: return "Night"
        case .emergency: return "Emergency"
        case .star: return "Star"
        case .heart: return "Heart"
        }
    }
}

enum ProfileColor: String, CaseIterable, Codable {
    case ocean, teal, amber, violet, coral, slate

    var displayName: String { rawValue.capitalized }
}

enum BuiltInProfile: String, Codable, CaseIterable {
    case home
    case workSchool = "work_school"
    case drivingTransit = "driving_transit"
    case sleepNight = "sleep_night"
    case emergency
}

enum SpeechMode: String, CaseIterable, Codable {
    case inherit
    case alwaysOn = "always_on"
    case off

    var displayName: String {
        switch self {
        case .inherit: return "Use global setting"
        case .alwaysOn: return "Always on"
        case .off: return "Off"
        }
    }
}

struct QuietHours: Codable, Equatable, Hashable {
    var enabled: Bool = false
    var startMinutes: Int = 22 * 60
    var endMinutes: Int = 7 * 60
}

struct ActivationRule: Codable, Equatable, Hashable {
    var enabled: Bool = false
    var activity: ActivityContext = .any
    var locationLabel: String = ""
}

struct SoundRule: Codable, Equatable, Hashable, Identifiable {
    var id: String { soundId }
    var soundId: String
    var enabled: Bool
    var confidenceThreshold: Float
    var priority: AlertPriority
    var hapticPattern: HapticPattern
    var hapticStrength: HapticStrength
    var requiresAcknowledgement: Bool
    var cooldownSeconds: Int
    var customHapticPattern: CustomHapticPattern? = nil
}

struct AlertProfile: Codable, Equatable, Hashable, Identifiable {
    var id: String
    var name: String
    var descriptionText: String
    var builtIn: BuiltInProfile? = nil
    var icon: ProfileIcon = .star
    var color: ProfileColor = .ocean
    var quietHours: QuietHours = QuietHours()
    var activation: ActivationRule = ActivationRule()
    var speechMode: SpeechMode = .inherit
    var phraseTriggers: [String] = []
    var soundRules: [SoundRule]

    var isBuiltIn: Bool { builtIn != nil }
    var enabledSoundCount: Int { soundRules.filter(\.enabled).count }
}

struct ProfileCatalog: Codable, Equatable {
    var profiles: [AlertProfile] = []
    var activeProfileId: String = ""
    var soundLibrary: [SoundDefinition] = SoundLibrary.builtIns()

    var activeProfile: AlertProfile? {
        profiles.first { $0.id == activeProfileId } ?? profiles.first
    }

    func sound(_ soundId: String) -> SoundDefinition? {
        soundLibrary.first { $0.id == soundId }
    }
}
