import Foundation

struct ProfileAgentResult {
    var profile: AlertProfile
    var explanation: String
    var assumptions: [String]
}

struct ProfileAgentError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// Deterministic, fully local text-to-profile agent (port of the Android
/// `LocalProfileTextAgent`). Nothing leaves the phone.
struct LocalProfileTextAgent {
    func generate(
        description: String,
        activeProfile: AlertProfile,
        soundLibrary: [SoundDefinition]
    ) throws -> ProfileAgentResult {
        let prompt = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { throw ProfileAgentError(message: "Describe the place or situation first") }
        let normalized = prompt.lowercased()

        let template: AlertProfile
        if normalized.containsAny("sleep", "hotel", "night", "bed") {
            template = ProfileDefaults.forBuiltIn(.sleepNight)
        } else if normalized.containsAny("drive", "driving", "car", "transit", "train", "bus") {
            template = ProfileDefaults.forBuiltIn(.drivingTransit)
        } else if normalized.containsAny("work", "office", "school", "class", "library", "study") {
            template = ProfileDefaults.forBuiltIn(.workSchool)
        } else if normalized.containsAny("emergency only", "critical alerts only") {
            template = ProfileDefaults.forBuiltIn(.emergency)
        } else {
            template = activeProfile
        }

        var draft = ProfileDefaults.newCustom(template: template)
        draft.name = suggestedName(normalized)
        draft.descriptionText = String(prompt.prefix(120))
        draft.soundRules = ProfileDefaults.completeRules(template.soundRules, soundLibrary: soundLibrary)

        let mentioned = Set(soundLibrary.filter { mentions(normalized, $0) }.map(\.id))
        let ignored = Set(soundLibrary.filter { ignores(normalized, $0) }.map(\.id))
        let onlyRequested = normalized.containsAny("only alert", "only notify", "nothing except", "just alert")
        let safetyIds = Set(soundLibrary.filter(\.safetyCritical).map(\.id))
        draft.soundRules = draft.soundRules.map { rule in
            var updated = rule
            if ignored.contains(rule.soundId) && !safetyIds.contains(rule.soundId) {
                updated.enabled = false
            } else if mentioned.contains(rule.soundId) {
                updated.enabled = true
            } else if onlyRequested && !safetyIds.contains(rule.soundId) {
                updated.enabled = false
            }
            return updated
        }
        var phrases = draft.phraseTriggers
        for phrase in extractPhrases(prompt) where !phrases.contains(phrase) { phrases.append(phrase) }
        draft.phraseTriggers = phrases
        draft.activation.enabled = normalized.containsAny("when i arrive", "at the", "inside", "entering")
        draft.activation.locationLabel = locationLabel(normalized)

        let enabledNames = draft.soundRules.filter(\.enabled).compactMap { rule in
            soundLibrary.first { $0.id == rule.soundId }?.displayName
        }
        var assumptions = ["Fire alarms, sirens, and other safety-critical sounds stay enabled unless reviewed manually."]
        if mentioned.isEmpty { assumptions.append("No exact sound names were found, so the closest built-in profile was used.") }
        if draft.phraseTriggers.isEmpty { assumptions.append("No name or phrase trigger was inferred.") }
        assumptions.append("Review thresholds and haptics before activating this generated profile.")

        let explanation = "Created \(draft.name) with \(enabledNames.count) enabled sounds: " +
            enabledNames.prefix(5).joined(separator: ", ") + (enabledNames.count > 5 ? ", and more." : ".")
        return ProfileAgentResult(profile: draft, explanation: explanation, assumptions: assumptions)
    }

    private func suggestedName(_ prompt: String) -> String {
        if prompt.contains("library") { return "Library visit" }
        if prompt.contains("coffee") || prompt.contains("cafe") { return "Coffee shop" }
        if prompt.contains("airport") { return "Airport" }
        if prompt.contains("hotel") { return "Hotel stay" }
        if prompt.containsAny("drive", "car", "transit") { return "Travel" }
        if prompt.containsAny("work", "office") { return "Work visit" }
        if prompt.containsAny("school", "class") { return "Class" }
        return "Situation profile"
    }

    private func extractPhrases(_ prompt: String) -> [String] {
        var results: [String] = []
        if let quoted = try? NSRegularExpression(pattern: #"["']([^"']{1,40})["']"#) {
            for match in quoted.matches(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)) {
                if let range = Range(match.range(at: 1), in: prompt) {
                    let value = prompt[range].trimmingCharacters(in: .whitespaces)
                    if !value.isEmpty && !results.contains(value) { results.append(value) }
                }
            }
        }
        if let named = try? NSRegularExpression(pattern: #"my name is\s+([a-z][a-z -]{0,30})"#, options: .caseInsensitive),
           let match = named.firstMatch(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)),
           let range = Range(match.range(at: 1), in: prompt) {
            let value = prompt[range].trimmingCharacters(in: .whitespaces)
            if !value.isEmpty && !results.contains(value) { results.append(value) }
        }
        return results
    }

    private func locationLabel(_ prompt: String) -> String {
        if prompt.contains("library") { return "Library" }
        if prompt.contains("coffee") || prompt.contains("cafe") { return "Coffee shop" }
        if prompt.contains("airport") { return "Airport" }
        if prompt.contains("hotel") { return "Hotel" }
        if prompt.contains("office") || prompt.contains("work") { return "Work" }
        if prompt.contains("school") || prompt.contains("class") { return "School" }
        return "Custom area"
    }

    private func mentions(_ prompt: String, _ sound: SoundDefinition) -> Bool {
        aliases(for: sound).contains { prompt.contains($0) }
    }

    private func ignores(_ prompt: String, _ sound: SoundDefinition) -> Bool {
        aliases(for: sound).contains { alias in
            prompt.contains("ignore \(alias)") || prompt.contains("without \(alias)") || prompt.contains("no \(alias)")
        }
    }

    private func aliases(for sound: SoundDefinition) -> Set<String> {
        var result: Set<String> = [sound.displayName.lowercased()]
        let bare = sound.id.hasPrefix("custom:") ? String(sound.id.dropFirst("custom:".count)) : sound.id
        result.insert(bare.replacingOccurrences(of: "_", with: " ").lowercased())
        switch sound.builtInType {
        case .fireAlarm: result.formUnion(["fire alarm", "smoke alarm"])
        case .doorbellKnock: result.formUnion(["doorbell", "knock", "door"])
        case .carHorn: result.formUnion(["car horn", "horn", "honking"])
        case .siren: result.formUnion(["siren", "emergency vehicle"])
        case .nameCalled: result.formUnion(["my name", "name called", "someone calls"])
        case .babyCrying: result.formUnion(["baby", "crying"])
        case .kitchenTimer: result.formUnion(["timer", "kitchen timer"])
        case .phoneRinging: result.formUnion(["phone", "ringtone", "phone ringing"])
        case nil: break
        }
        return result
    }
}

private extension String {
    func containsAny(_ values: String...) -> Bool { values.contains { contains($0) } }
}
