import Foundation

enum SpeechModel: String, CaseIterable, Codable {
    case tinyEn = "tiny_en"
    case baseEn = "base_en"
    case smallEn = "small_en"

    var displayName: String {
        switch self {
        case .tinyEn: return "Tiny"
        case .baseEn: return "Base"
        case .smallEn: return "Small"
        }
    }

    var detail: String {
        switch self {
        case .tinyEn: return "Fastest (about 150 ms per window); misses more unusual names."
        case .baseEn: return "Recommended. About 300 ms per window on the Mac."
        case .smallEn: return "Most accurate; about 1 s per window, so alerts arrive later."
        }
    }
}

/// Global speech controls, edited on the Settings tab. Your own name is always
/// listened for once it is enrolled; there is no separate switch for it.
struct SpeechSettings: Codable, Equatable, Hashable {
    var enabled: Bool = true
    var model: SpeechModel = .baseEn
    var sensitivity: Float = 0.6
    var listenForPeople: Bool = false
    var globalPhrases: [String] = []

    private enum CodingKeys: String, CodingKey {
        case enabled, model, sensitivity, listenForPeople, globalPhrases
    }
}

struct UserIdentity: Codable, Equatable, Hashable {
    var displayName: String
    /// Kept for older stored banks; no longer edited or sent as a hotword.
    var pronunciation: String = ""
    var aliases: [String] = []
    /// Spellings the Mac's Whisper model produced for the name during
    /// enrollment ("Rowan" for Rohan). Matched exactly like nicknames.
    var recognitionPhrases: [String] = []
    var updatedAtEpochMs: Int64 = nowEpochMs()

    static let maxLearnedSpellings = 10
}

struct PersonMemory: Codable, Equatable, Hashable, Identifiable {
    var id: String
    var name: String
    var relationship: String = ""
    var pronunciation: String = ""
    var aliases: [String] = []
    var notes: String = ""
    var updatedAtEpochMs: Int64 = nowEpochMs()
}

struct ContextMemory: Codable, Equatable, Hashable, Identifiable {
    var id: String
    var title: String
    var details: String
    var updatedAtEpochMs: Int64 = nowEpochMs()
}

struct MemoryBank: Codable, Equatable {
    var identity: UserIdentity? = nil
    var people: [PersonMemory] = []
    var contexts: [ContextMemory] = []
    var speechSettings: SpeechSettings = SpeechSettings()

    var isEmpty: Bool {
        identity == nil && people.isEmpty && contexts.isEmpty && speechSettings == SpeechSettings()
    }
}

enum MemoryBankValidator {
    static let maxPeople = 50
    static let maxContexts = 50

    static func validate(_ bank: MemoryBank) -> [String] {
        var errors: [String] = []
        if let identity = bank.identity {
            let name = identity.displayName.trimmingCharacters(in: .whitespaces)
            if name.isEmpty || name.count > 60 { errors.append("Your name must be between 1 and 60 characters.") }
            if identity.pronunciation.count > 80 { errors.append("Pronunciation must be 80 characters or fewer.") }
            if let error = validateTextList(identity.aliases, maximumItems: 10, maximumLength: 60, label: "nicknames") {
                errors.append(error)
            }
            if let error = validateTextList(identity.recognitionPhrases, maximumItems: UserIdentity.maxLearnedSpellings, maximumLength: 60, label: "learned spellings") {
                errors.append(error)
            }
        }
        if bank.people.count > maxPeople { errors.append("The memory bank supports up to \(maxPeople) people.") }
        if bank.contexts.count > maxContexts { errors.append("The memory bank supports up to \(maxContexts) context entries.") }
        if Set(bank.people.map(\.id)).count != bank.people.count { errors.append("People must have unique IDs.") }
        if Set(bank.contexts.map(\.id)).count != bank.contexts.count { errors.append("Context entries must have unique IDs.") }
        for person in bank.people {
            if person.id.isEmpty || person.id.count > 80 { errors.append("Each person needs a valid ID.") }
            let name = person.name.trimmingCharacters(in: .whitespaces)
            if name.isEmpty || name.count > 60 { errors.append("Each person's name must be 1 to 60 characters.") }
            if person.relationship.count > 80 { errors.append("Relationships must be 80 characters or fewer.") }
            if person.pronunciation.count > 80 { errors.append("Pronunciations must be 80 characters or fewer.") }
            if person.notes.count > 280 { errors.append("Person notes must be 280 characters or fewer.") }
            if let error = validateTextList(person.aliases, maximumItems: 10, maximumLength: 60, label: "person aliases") {
                errors.append(error)
            }
        }
        for context in bank.contexts {
            if context.id.isEmpty || context.id.count > 80 { errors.append("Each context entry needs a valid ID.") }
            let title = context.title.trimmingCharacters(in: .whitespaces)
            if title.isEmpty || title.count > 80 { errors.append("Context titles must be 1 to 80 characters.") }
            let details = context.details.trimmingCharacters(in: .whitespaces)
            if details.isEmpty || details.count > 500 { errors.append("Context details must be 1 to 500 characters.") }
        }
        if !(0.4...0.95).contains(bank.speechSettings.sensitivity) {
            errors.append("Speech sensitivity must be between 40% and 95%.")
        }
        if let error = validateTextList(bank.speechSettings.globalPhrases, maximumItems: 20, maximumLength: 40, label: "global speech phrases") {
            errors.append(error)
        }
        var seen = Set<String>()
        return errors.filter { seen.insert($0).inserted }
    }

    private static func validateTextList(_ values: [String], maximumItems: Int, maximumLength: Int, label: String) -> String? {
        let invalid = values.count > maximumItems ||
            values.contains { $0.trimmingCharacters(in: .whitespaces).isEmpty || $0.count > maximumLength } ||
            Set(values.map { $0.lowercased() }).count != values.count
        return invalid ? "Invalid \(label)." : nil
    }
}
