import Foundation

enum ProfileValidator {
    static func validate(
        _ profile: AlertProfile,
        soundLibrary: [SoundDefinition] = SoundLibrary.builtIns()
    ) -> [String] {
        var errors: [String] = []
        let trimmedName = profile.name.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedName.isEmpty { errors.append("Give the profile a name.") }
        if trimmedName.count > 40 { errors.append("Keep the profile name to 40 characters or fewer.") }
        if profile.descriptionText.count > 120 { errors.append("Keep the description to 120 characters or fewer.") }
        if !profile.soundRules.contains(where: \.enabled) { errors.append("Enable at least one sound.") }
        if Set(profile.soundRules.map(\.soundId)) != Set(soundLibrary.map(\.id)) {
            errors.append("The profile must contain one rule for every supported sound.")
        }
        if profile.soundRules.contains(where: { !(0.20...0.95).contains($0.confidenceThreshold) }) {
            errors.append("Confidence thresholds must be between 20% and 95%.")
        }
        if profile.soundRules.contains(where: { !(0...120).contains($0.cooldownSeconds) }) {
            errors.append("Cooldowns must be between 0 and 120 seconds.")
        }
        if profile.soundRules.contains(where: { $0.hapticPattern == .custom && $0.customHapticPattern?.isValid != true }) {
            errors.append("Every custom haptic must contain one to six valid touch-recorded pulses.")
        }
        if profile.phraseTriggers.contains(where: { $0.count > 40 }) {
            errors.append("Each name or phrase trigger must be 40 characters or fewer.")
        }
        return errors
    }
}

func formatTime(minutes: Int) -> String {
    let hour24 = minutes / 60
    let minute = minutes % 60
    let suffix = hour24 < 12 ? "AM" : "PM"
    let hour12 = hour24 % 12 == 0 ? 12 : hour24 % 12
    return String(format: "%d:%02d %@", hour12, minute, suffix)
}

func parseTime(_ value: String) -> Int? {
    let pattern = #"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$"#
    guard let regex = try? NSRegularExpression(pattern: pattern),
          let match = regex.firstMatch(in: value, range: NSRange(value.startIndex..., in: value)) else {
        return nil
    }
    func group(_ index: Int) -> String {
        guard let range = Range(match.range(at: index), in: value) else { return "" }
        return String(value[range])
    }
    guard let rawHour = Int(group(1)), let minute = Int(group(2)), (0...59).contains(minute) else { return nil }
    let suffix = group(3).uppercased()
    let hour24: Int
    switch suffix {
    case "" where (0...23).contains(rawHour): hour24 = rawHour
    case "AM" where (1...12).contains(rawHour): hour24 = rawHour == 12 ? 0 : rawHour
    case "PM" where (1...12).contains(rawHour): hour24 = rawHour == 12 ? 12 : rawHour + 12
    default: return nil
    }
    return hour24 * 60 + minute
}

func parseCommaList(_ value: String, maximum: Int) -> [String] {
    var seen = Set<String>()
    var result: [String] = []
    for item in value.split(separator: ",") {
        let trimmed = item.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, seen.insert(trimmed.lowercased()).inserted else { continue }
        result.append(trimmed)
        if result.count == maximum { break }
    }
    return result
}
