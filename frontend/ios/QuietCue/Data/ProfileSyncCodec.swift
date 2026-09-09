import Foundation

/// Produces the strict profile document the hub validates in
/// `backend/profiles/wire_codec.py`. Key names and enum values must match the
/// Android `ProfileSyncJsonCodec` exactly.
enum ProfileSyncCodec {
    static func encode(catalog: ProfileCatalog, memoryBank: MemoryBank = MemoryBank()) throws -> Data {
        guard let profile = catalog.activeProfile else { throw StoreError(message: "No active profile") }
        let soundsById = Dictionary(catalog.soundLibrary.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })

        var soundRules: [[String: Any]] = []
        var customSounds: [[String: Any]] = []
        var labelRules: [[String: Any]] = []
        for rule in profile.soundRules {
            var ruleJson: [String: Any] = [
                "event": rule.soundId,
                "enabled": rule.enabled,
                "confidence_threshold": jsonNumber(rule.confidenceThreshold),
                "category": rule.priority.rawValue,
                "pattern": rule.hapticPattern.rawValue,
                "strength": rule.hapticStrength.rawValue,
                "requires_ack": rule.requiresAcknowledgement,
                "cooldown_seconds": rule.cooldownSeconds,
            ]
            if rule.hapticPattern == .custom, let custom = rule.customHapticPattern {
                ruleJson["custom_pattern"] = [
                    "name": custom.name,
                    "steps": custom.steps.map { ["on_ms": $0.onMs, "off_ms": $0.offMs] },
                ]
            }
            soundRules.append(ruleJson)

            guard let sound = soundsById[rule.soundId] else { continue }
            if let enrollment = sound.enrollment {
                customSounds.append([
                    "event": sound.id,
                    "label": sound.displayName,
                    "prototype": enrollment.prototype.map(jsonNumber),
                    "prototypes": enrollment.prototypes.map { $0.map(jsonNumber) },
                    "similarity_threshold": jsonNumber(enrollment.similarityThreshold),
                    "matcher_version": enrollment.matcherVersion,
                ])
            }
            for label in sound.classifierLabels {
                labelRules.append(["event": sound.id, "label": label])
            }
        }

        let document: [String: Any] = [
            "id": profile.id,
            "name": profile.name,
            "speech_mode": profile.speechMode.rawValue,
            "phrase_triggers": profile.phraseTriggers,
            "speech_context": encodeSpeechContext(memoryBank),
            "quiet_hours": [
                "enabled": profile.quietHours.enabled,
                "start_minutes": profile.quietHours.startMinutes,
                "end_minutes": profile.quietHours.endMinutes,
            ],
            "sound_rules": soundRules,
            "custom_sounds": customSounds,
            "classifier_label_rules": labelRules,
        ]
        return try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys, .withoutEscapingSlashes])
    }

    private static func encodeSpeechContext(_ bank: MemoryBank) -> [String: Any] {
        let settings = bank.speechSettings
        var identity: Any = NSNull()
        if let user = bank.identity {
            identity = [
                "name": user.displayName,
                "pronunciation": user.pronunciation,
                "aliases": user.aliases,
                "recognition_phrases": user.recognitionPhrases,
            ] as [String: Any]
        }
        return [
            "settings": [
                "enabled": settings.enabled,
                "model": settings.model.rawValue,
                "sensitivity": jsonNumber(settings.sensitivity),
                // An enrolled name is always listened for; the hub key stays for compatibility.
                "listen_for_identity": true,
                "listen_for_people": settings.listenForPeople,
                "global_phrases": settings.globalPhrases,
            ] as [String: Any],
            "identity": identity,
            "people": bank.people.map { person in
                [
                    "name": person.name,
                    "relationship": person.relationship,
                    "pronunciation": person.pronunciation,
                    "aliases": person.aliases,
                    "notes": person.notes,
                ] as [String: Any]
            },
            "contexts": bank.contexts.map { ["title": $0.title, "details": $0.details] },
        ]
    }

    /// Floats such as 0.55 must reach the hub as 0.55, not 0.550000011920929.
    static func jsonNumber(_ value: Float) -> Double {
        Double(String(describing: value)) ?? Double(value)
    }
}
