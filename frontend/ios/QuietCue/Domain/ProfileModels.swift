import Foundation

/// Built-in sound events. `id` values match the hub's event names exactly
/// (`backend/inference/sound_catalog.py`). The list was rebuilt in September
/// 2026 around what YAMNet detects reliably on real recordings.
enum SoundType: String, CaseIterable, Codable {
    case alarm
    case siren
    case loudBang = "loud_bang"
    case glassBreaking = "glass_breaking"
    case carHorn = "car_horn"
    case doorbellKnock = "doorbell_knock"
    case bell
    case phoneRinging = "phone_ringing"
    case babyCrying = "baby_crying"
    case nameCalled = "name_called"
    case dogBark = "dog_bark"
    case cat
    case applianceBeep = "appliance_beep"
    case thunder
    case train
    case clapping
    case cough
    case toiletFlush = "toilet_flush"
    case typing
    case snoring
    case chainsaw

    var id: String { rawValue }

    /// Ids from before the rebuild, still present in saved profiles.
    static let legacyIds: [String: SoundType] = [
        "fire_alarm": .alarm,
        "kitchen_timer": .applianceBeep,
    ]

    static func canonicalId(_ soundId: String) -> String {
        legacyIds[soundId]?.id ?? soundId
    }

    var displayName: String {
        switch self {
        case .alarm: return "Alarm"
        case .siren: return "Siren"
        case .loudBang: return "Loud bang"
        case .glassBreaking: return "Glass breaking"
        case .carHorn: return "Car horn"
        case .doorbellKnock: return "Doorbell or knock"
        case .bell: return "Bell or chime"
        case .phoneRinging: return "Phone ringing"
        case .babyCrying: return "Baby crying"
        case .nameCalled: return "Name or phrase called"
        case .dogBark: return "Dog barking"
        case .cat: return "Cat"
        case .applianceBeep: return "Appliance beeps"
        case .thunder: return "Thunder"
        case .train: return "Train"
        case .clapping: return "Clapping or applause"
        case .cough: return "Coughing"
        case .toiletFlush: return "Toilet flush"
        case .typing: return "Typing"
        case .snoring: return "Snoring"
        case .chainsaw: return "Chainsaw"
        }
    }

    var descriptionText: String {
        switch self {
        case .alarm: return "Smoke and fire alarms, alarm clocks, buzzers and other alarm tones"
        case .siren: return "Police, ambulance, fire-engine and civil-defense sirens"
        case .loudBang: return "Explosions, gunshots, fireworks and firecrackers"
        case .glassBreaking: return "Shattering or breaking glass"
        case .carHorn: return "Nearby vehicle horns and warning honks"
        case .doorbellKnock: return "Door chimes, apartment buzzers and knocking at a nearby door"
        case .bell: return "Church bells, hand bells and chimes, including bell-type doorbells"
        case .phoneRinging: return "Classic phone rings and ringtones (musical ringtones are often missed)"
        case .babyCrying: return "Infant crying and sobbing nearby"
        case .nameCalled: return "Speech containing one of your configured phrases"
        case .dogBark: return "Barking, howling and growling dogs"
        case .cat: return "Meowing, purring and caterwauling cats"
        case .applianceBeep: return "Microwave, timer, washer and other appliance beeps"
        case .thunder: return "Thunder and thunderstorms"
        case .train: return "Trains, train horns and whistles, rail transport"
        case .clapping: return "Hand clapping and applause, often used to get attention"
        case .cough: return "Coughing and throat clearing nearby"
        case .toiletFlush: return "A toilet flushing"
        case .typing: return "Keyboard typing"
        case .snoring: return "Snoring nearby"
        case .chainsaw: return "Chainsaws and similar power tools"
        }
    }

    /// Default urgency; mirrors the hub catalog's category.
    var category: AlertPriority {
        switch self {
        case .alarm, .siren: return .emergency
        case .loudBang, .glassBreaking, .carHorn, .doorbellKnock, .bell, .phoneRinging,
             .babyCrying, .nameCalled, .dogBark, .cat, .thunder, .train, .chainsaw: return .attention
        case .applianceBeep, .clapping, .cough, .toiletFlush, .typing, .snoring: return .informational
        }
    }

    var safetyCritical: Bool {
        switch self {
        case .alarm, .siren, .loudBang, .glassBreaking, .carHorn: return true
        default: return false
        }
    }

    /// Words the profile text agent accepts for this sound.
    var aliases: Set<String> {
        switch self {
        case .alarm: return ["alarm", "fire alarm", "smoke alarm", "smoke detector", "alarm clock"]
        case .siren: return ["siren", "emergency vehicle", "ambulance", "police"]
        case .loudBang: return ["bang", "explosion", "gunshot", "fireworks"]
        case .glassBreaking: return ["glass", "breaking glass", "glass breaking"]
        case .carHorn: return ["car horn", "horn", "honking"]
        case .doorbellKnock: return ["doorbell", "knock", "door", "buzzer"]
        case .bell: return ["bell", "chime", "church bell"]
        case .phoneRinging: return ["phone", "ringtone", "phone ringing", "telephone"]
        case .babyCrying: return ["baby", "crying"]
        case .nameCalled: return ["my name", "name called", "someone calls"]
        case .dogBark: return ["dog", "bark", "barking"]
        case .cat: return ["cat", "meow"]
        case .applianceBeep: return ["beep", "beeps", "timer", "kitchen timer", "microwave"]
        case .thunder: return ["thunder", "storm", "thunderstorm"]
        case .train: return ["train", "railway"]
        case .clapping: return ["clap", "clapping", "applause"]
        case .cough: return ["cough", "coughing"]
        case .toiletFlush: return ["toilet", "flush"]
        case .typing: return ["typing", "keyboard"]
        case .snoring: return ["snoring", "snore"]
        case .chainsaw: return ["chainsaw", "power tool"]
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
            let category = sound.category
            let pattern: HapticPattern
            switch category {
            case .emergency: pattern = .urgentRepeat
            case .attention: pattern = .longPulse
            case .informational: pattern = .twoShort
            }
            return SoundDefinition(
                id: sound.id,
                displayName: sound.displayName,
                descriptionText: sound.descriptionText,
                safetyCritical: sound.safetyCritical,
                builtInType: sound,
                defaultPriority: category,
                defaultHapticPattern: pattern,
                defaultHapticStrength: category == .emergency ? .strong : .standard,
                defaultRequiresAcknowledgement: category == .emergency
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
