import Foundation

struct StoreError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// Port of the Android `ProfileRepository`: profiles, the active profile, and
/// enrolled custom sounds, persisted locally.
@MainActor
final class ProfileStore {
    private struct Persisted: Codable {
        var profiles: [AlertProfile] = []
        var activeProfileId: String = ProfileDefaults.homeId
        var customSounds: [SoundDefinition] = []
    }

    private let file = JSONFileStore<Persisted>(fileName: "profiles.json")
    private var persisted: Persisted
    private(set) var catalog: ProfileCatalog

    init() {
        persisted = file.load() ?? Persisted()
        catalog = ProfileCatalog()
        catalog = buildCatalog()
    }

    func save(_ profile: AlertProfile) throws {
        let library = soundLibrary
        var cleaned = profile
        cleaned.name = profile.name.trimmingCharacters(in: .whitespacesAndNewlines)
        cleaned.descriptionText = profile.descriptionText.trimmingCharacters(in: .whitespacesAndNewlines)
        var seenPhrases = Set<String>()
        cleaned.phraseTriggers = profile.phraseTriggers
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && seenPhrases.insert($0).inserted }
        cleaned.soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary: library)
        let errors = ProfileValidator.validate(cleaned, soundLibrary: library)
        guard errors.isEmpty else { throw StoreError(message: errors.joined(separator: " ")) }
        var profiles = currentProfiles(library: library)
        if let index = profiles.firstIndex(where: { $0.id == cleaned.id }) {
            profiles[index] = cleaned
        } else {
            profiles.append(cleaned)
        }
        persisted.profiles = sortProfiles(profiles)
        if persisted.activeProfileId.isEmpty { persisted.activeProfileId = ProfileDefaults.homeId }
        commit()
    }

    func setActive(_ profileId: String) throws {
        guard currentProfiles(library: soundLibrary).contains(where: { $0.id == profileId }) else {
            throw StoreError(message: "Unknown profile: \(profileId)")
        }
        persisted.activeProfileId = profileId
        commit()
    }

    func delete(_ profileId: String) throws {
        let profiles = currentProfiles(library: soundLibrary)
        guard let profile = profiles.first(where: { $0.id == profileId }) else { return }
        guard !profile.isBuiltIn else { throw StoreError(message: "Built-in profiles cannot be deleted") }
        persisted.profiles = profiles.filter { $0.id != profileId }
        if persisted.activeProfileId == profileId { persisted.activeProfileId = ProfileDefaults.homeId }
        commit()
    }

    func resetBuiltIn(_ profileId: String) {
        let library = soundLibrary
        var profiles = currentProfiles(library: library)
        guard let index = profiles.firstIndex(where: { $0.id == profileId }), let builtIn = profiles[index].builtIn else { return }
        var restored = ProfileDefaults.forBuiltIn(builtIn)
        restored.soundRules = ProfileDefaults.completeRules(restored.soundRules, soundLibrary: library)
        profiles[index] = restored
        persisted.profiles = sortProfiles(profiles)
        commit()
    }

    func addEnrolledSound(_ sound: SoundDefinition) throws {
        guard sound.id.hasPrefix("custom:"), sound.enrollment != nil else { throw StoreError(message: "Sound must be enrolled") }
        guard !sound.displayName.trimmingCharacters(in: .whitespaces).isEmpty else { throw StoreError(message: "Give the sound a name") }
        let existing = persisted.customSounds
        guard !existing.contains(where: { $0.displayName.caseInsensitiveCompare(sound.displayName) == .orderedSame }) else {
            throw StoreError(message: "A sound with that name already exists")
        }
        let customSounds = existing + [sound]
        let library = SoundLibrary.complete(customSounds)
        let activeId = persisted.activeProfileId.isEmpty ? ProfileDefaults.homeId : persisted.activeProfileId
        let profiles = currentProfiles(library: SoundLibrary.complete(existing)).map { profile -> AlertProfile in
            var updated = profile
            updated.soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary: library).map { rule in
                rule.soundId == sound.id ? ProfileDefaults.ruleForSound(sound, enabled: profile.id == activeId) : rule
            }
            return updated
        }
        persisted.customSounds = customSounds
        persisted.profiles = sortProfiles(profiles)
        commit()
    }

    func deleteEnrolledSound(_ soundId: String) {
        let oldLibrary = soundLibrary
        persisted.customSounds.removeAll { $0.id == soundId }
        persisted.profiles = sortProfiles(currentProfiles(library: oldLibrary).map { profile in
            var updated = profile
            updated.soundRules = profile.soundRules.filter { $0.soundId != soundId }
            return updated
        })
        commit()
    }

    // MARK: Private

    private var soundLibrary: [SoundDefinition] { SoundLibrary.complete(persisted.customSounds) }

    private func commit() {
        file.save(persisted)
        catalog = buildCatalog()
    }

    private func buildCatalog() -> ProfileCatalog {
        let library = soundLibrary
        let profiles = currentProfiles(library: library)
        let activeId = profiles.contains { $0.id == persisted.activeProfileId } ? persisted.activeProfileId : ProfileDefaults.homeId
        return ProfileCatalog(profiles: profiles, activeProfileId: activeId, soundLibrary: library)
    }

    private func currentProfiles(library: [SoundDefinition]) -> [AlertProfile] {
        let decoded = persisted.profiles
        if decoded.isEmpty {
            return ProfileDefaults.all().map { profile in
                var completed = profile
                completed.soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary: library)
                return completed
            }
        }
        let byBuiltIn = Dictionary(decoded.compactMap { profile in profile.builtIn.map { ($0, profile) } }, uniquingKeysWith: { first, _ in first })
        let builtIns = ProfileDefaults.all().map { fallback -> AlertProfile in
            var stored = fallback.builtIn.flatMap { byBuiltIn[$0] } ?? fallback
            stored.phraseTriggers = stored.phraseTriggers.filter { $0.caseInsensitiveCompare("my name") != .orderedSame }
            stored.soundRules = ProfileDefaults.completeRules(stored.soundRules, soundLibrary: library)
            return stored
        }
        let customs = decoded.filter { $0.builtIn == nil }.map { profile -> AlertProfile in
            var completed = profile
            completed.soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary: library)
            return completed
        }
        return builtIns + customs
    }

    private func sortProfiles(_ profiles: [AlertProfile]) -> [AlertProfile] {
        let order = Dictionary(uniqueKeysWithValues: ProfileDefaults.all().enumerated().compactMap { index, profile in
            profile.builtIn.map { ($0, index) }
        })
        return profiles.sorted { left, right in
            let leftCustom = left.builtIn == nil
            let rightCustom = right.builtIn == nil
            if leftCustom != rightCustom { return !leftCustom }
            let leftOrder = left.builtIn.flatMap { order[$0] } ?? Int.max
            let rightOrder = right.builtIn.flatMap { order[$0] } ?? Int.max
            if leftOrder != rightOrder { return leftOrder < rightOrder }
            return left.name.lowercased() < right.name.lowercased()
        }
    }
}
