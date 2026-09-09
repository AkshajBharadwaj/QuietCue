import Foundation

/// Private, user-entered speech context. Stored with complete data protection
/// (the file is unreadable while the phone is locked) and only ever synced to
/// the hub as part of the active profile document.
@MainActor
final class MemoryStore {
    private let file = JSONFileStore<MemoryBank>(fileName: "memory_bank.json", protection: .complete)
    private(set) var bank: MemoryBank

    init() {
        bank = file.load() ?? MemoryBank()
    }

    func saveIdentity(_ identity: UserIdentity) throws {
        try mutate { $0.identity = identity }
    }

    func deleteIdentity() throws {
        try mutate { $0.identity = nil }
    }

    func savePerson(_ person: PersonMemory) throws {
        try mutate { bank in
            if let index = bank.people.firstIndex(where: { $0.id == person.id }) {
                bank.people[index] = person
            } else {
                bank.people.append(person)
            }
            bank.people.sort { $0.name.lowercased() < $1.name.lowercased() }
        }
    }

    func deletePerson(_ personId: String) throws {
        try mutate { $0.people.removeAll { $0.id == personId } }
    }

    func saveContext(_ context: ContextMemory) throws {
        try mutate { bank in
            if let index = bank.contexts.firstIndex(where: { $0.id == context.id }) {
                bank.contexts[index] = context
            } else {
                bank.contexts.append(context)
            }
        }
    }

    func deleteContext(_ contextId: String) throws {
        try mutate { $0.contexts.removeAll { $0.id == contextId } }
    }

    func saveSpeechSettings(_ settings: SpeechSettings) throws {
        try mutate { $0.speechSettings = settings }
    }

    func clearAll() {
        bank = MemoryBank()
        file.delete()
    }

    private func mutate(_ transform: (inout MemoryBank) -> Void) throws {
        var updated = bank
        transform(&updated)
        let errors = MemoryBankValidator.validate(updated)
        guard errors.isEmpty else { throw StoreError(message: errors.joined(separator: " ")) }
        bank = updated
        file.save(updated)
    }
}
