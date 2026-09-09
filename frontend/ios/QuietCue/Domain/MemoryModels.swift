import Foundation

enum SpeechModel: String, CaseIterable, Codable {
    case tinyEn = "tiny_en"
    case baseEn = "base_en"

    var displayName: String {
        switch self {
        case .tinyEn: return "Tiny English"
        case .baseEn: return "Base English"
        }
    }
}

struct SpeechSettings: Codable, Equatable, Hashable {
    var enabled: Bool = true
    var model: SpeechModel = .tinyEn
    var sensitivity: Float = 0.6
    var listenForIdentity: Bool = true
    var listenForPeople: Bool = false
    var globalPhrases: [String] = []
}

struct UserIdentity: Codable, Equatable, Hashable {
    var displayName: String
    var pronunciation: String = ""
    var aliases: [String] = []
    var recognitionPhrases: [String] = []
    var updatedAtEpochMs: Int64 = nowEpochMs()
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
            if let error = validateTextList(identity.aliases, maximumItems: 10, maximumLength: 60, label: "identity aliases") {
                errors.append(error)
            }
            if let error = validateTextList(identity.recognitionPhrases, maximumItems: 5, maximumLength: 100, label: "recognition samples") {
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
