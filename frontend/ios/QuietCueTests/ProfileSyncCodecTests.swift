import XCTest
@testable import QuietCue

final class ProfileSyncCodecTests: XCTestCase {
    private func sampleCatalog() -> (ProfileCatalog, MemoryBank) {
        var custom = ProfileDefaults.newCustom()
        custom.id = "custom-test"
        custom.name = "Library visit"
        var rules = ProfileDefaults.completeRules(custom.soundRules)
        rules[0].hapticPattern = .custom
        rules[0].customHapticPattern = CustomHapticPattern(
            name: "Double tap",
            steps: [CustomHapticStep(onMs: 180, offMs: 120), CustomHapticStep(onMs: 420, offMs: 300)]
        )
        rules[1].confidenceThreshold = 0.55
        custom.soundRules = rules
        custom.phraseTriggers = ["front desk", "Akshaj"]
        let catalog = ProfileCatalog(profiles: ProfileDefaults.all() + [custom], activeProfileId: custom.id)
        let bank = MemoryBank(
            identity: UserIdentity(displayName: "Akshaj", pronunciation: "Ak-shudge", aliases: ["AK"], recognitionPhrases: ["hey akshaj"]),
            people: [PersonMemory(id: "p1", name: "Maya", relationship: "Sister", aliases: ["May"], notes: "Visits on weekends")],
            contexts: [ContextMemory(id: "c1", title: "Tuesday class", details: "Accessibility design class in Building 4.")],
            speechSettings: SpeechSettings(enabled: true, model: .tinyEn, sensitivity: 0.65, listenForIdentity: true, listenForPeople: false, globalPhrases: ["excuse me"])
        )
        return (catalog, bank)
    }

    func testDocumentUsesHubKeysAndEnumValues() throws {
        let (catalog, bank) = sampleCatalog()
        let data = try ProfileSyncCodec.encode(catalog: catalog, memoryBank: bank)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["id"] as? String, "custom-test")
        XCTAssertEqual(json["speech_mode"] as? String, "inherit")
        let rules = try XCTUnwrap(json["sound_rules"] as? [[String: Any]])
        XCTAssertEqual(rules.count, 8)
        XCTAssertEqual(rules[0]["pattern"] as? String, "custom")
        XCTAssertEqual(rules[0]["category"] as? String, "emergency")
        XCTAssertEqual(rules[0]["strength"] as? String, "strong")
        let custom = try XCTUnwrap(rules[0]["custom_pattern"] as? [String: Any])
        XCTAssertEqual((custom["steps"] as? [[String: Any]])?.count, 2)
        XCTAssertEqual(rules[1]["confidence_threshold"] as? Double, 0.55, "floats must not pick up single-precision noise")
        let speech = try XCTUnwrap(json["speech_context"] as? [String: Any])
        XCTAssertEqual((speech["identity"] as? [String: Any])?["name"] as? String, "Akshaj")
        XCTAssertEqual((speech["settings"] as? [String: Any])?["model"] as? String, "tiny_en")
    }

    func testEncodingIsDeterministic() throws {
        let (catalog, bank) = sampleCatalog()
        XCTAssertEqual(try ProfileSyncCodec.encode(catalog: catalog, memoryBank: bank),
                       try ProfileSyncCodec.encode(catalog: catalog, memoryBank: bank))
    }

    /// Writes the document to QUIETCUE_FIXTURE_DIR so the Python hub test in
    /// tests/test_ios_profile_sync.py can validate it with the real decoder.
    func testWritesFixtureForHubDecoder() throws {
        guard let dir = ProcessInfo.processInfo.environment["QUIETCUE_FIXTURE_DIR"] else {
            throw XCTSkip("Set QUIETCUE_FIXTURE_DIR to regenerate the fixture")
        }
        let (catalog, bank) = sampleCatalog()
        let data = try ProfileSyncCodec.encode(catalog: catalog, memoryBank: bank)
        try data.write(to: URL(fileURLWithPath: dir).appendingPathComponent("ios_profile_sync.json"))
    }
}
