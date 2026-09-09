import Foundation

enum PlaceTransition: String, Codable {
    case enter = "ENTER"
    case exit = "EXIT"
}

struct SmartPlace: Codable, Equatable, Hashable, Identifiable {
    var id: String = UUID().uuidString.lowercased()
    var name: String
    var latitude: Double
    var longitude: Double
    var radiusMeters: Float = 150
    var profileId: String
    var enabled: Bool = true
    var autoApply: Bool = false
    var demoOnly: Bool = false

    func validationError() -> String? {
        if name.trimmingCharacters(in: .whitespaces).isEmpty { return "Give the place a name" }
        if !(-90.0...90.0).contains(latitude) { return "Invalid latitude" }
        if !(-180.0...180.0).contains(longitude) { return "Invalid longitude" }
        if !(15...1_000).contains(radiusMeters) { return "Place radius must be between 15 and 1,000 meters" }
        if profileId.isEmpty { return "Choose a profile" }
        return nil
    }
}

struct SmartProfileSuggestion: Codable, Equatable, Hashable {
    var id: String
    var placeId: String
    var placeName: String
    var targetProfileId: String
    var targetProfileName: String
    var transition: PlaceTransition
    var createdAtEpochMs: Int64
    var previousProfileId: String? = nil
    var simulated: Bool = false
}

struct SmartProfileState: Codable, Equatable {
    var places: [SmartPlace] = []
    var suggestion: SmartProfileSuggestion? = nil
    var manualOverrideUntilEpochMs: Int64 = 0
    var activePlaceId: String? = nil
    var returnProfileId: String? = nil
    var lastTransitionKey: String? = nil
    var lastTransitionAtEpochMs: Int64 = 0
    var statusMessage: String? = nil

    func manualOverrideActive(nowEpochMs: Int64) -> Bool { manualOverrideUntilEpochMs > nowEpochMs }
}

enum SmartProfileDecisionType {
    case ignore, suggest, activate
}

struct SmartProfileDecision {
    var type: SmartProfileDecisionType
    var targetProfileId: String? = nil
}

enum SmartProfilePolicy {
    static let manualOverrideMs: Int64 = 2 * 60 * 60 * 1_000
    static let duplicateTransitionMs: Int64 = 5 * 60 * 1_000
    static let suggestionExpiryMs: Int64 = 6 * 60 * 60 * 1_000

    static func decide(
        place: SmartPlace,
        transition: PlaceTransition,
        state: SmartProfileState,
        activeProfileId: String,
        availableProfileIds: Set<String>,
        nowEpochMs: Int64
    ) -> SmartProfileDecision {
        guard place.enabled else { return SmartProfileDecision(type: .ignore) }
        let transitionKey = "\(place.id):\(transition.rawValue)"
        if state.lastTransitionKey == transitionKey {
            let elapsed = nowEpochMs - state.lastTransitionAtEpochMs
            if elapsed >= 0 && elapsed < duplicateTransitionMs {
                return SmartProfileDecision(type: .ignore)
            }
        }
        let target: String?
        switch transition {
        case .enter: target = place.profileId
        case .exit: target = state.activePlaceId == place.id ? state.returnProfileId : nil
        }
        guard let targetProfileId = target,
              availableProfileIds.contains(targetProfileId),
              targetProfileId != activeProfileId else {
            return SmartProfileDecision(type: .ignore)
        }
        let automatic = place.autoApply && !state.manualOverrideActive(nowEpochMs: nowEpochMs)
        return SmartProfileDecision(type: automatic ? .activate : .suggest, targetProfileId: targetProfileId)
    }
}

func nowEpochMs() -> Int64 { Int64(Date().timeIntervalSince1970 * 1_000) }
