import Foundation

enum SmartTransitionResultType {
    case ignored, suggested, activated
}

struct SmartTransitionResult {
    var type: SmartTransitionResultType
    var title: String
    var message: String
}

/// Port of the Android `SmartProfileCoordinator`.
@MainActor
final class SmartProfileCoordinator {
    private let profiles: ProfileStore
    private let smart: SmartProfileStore

    init(profiles: ProfileStore, smart: SmartProfileStore) {
        self.profiles = profiles
        self.smart = smart
    }

    func activateManually(_ profileId: String) throws {
        try profiles.setActive(profileId)
        smart.recordManualOverride()
    }

    func handleTransition(
        placeId: String,
        transition: PlaceTransition,
        nowEpochMs now: Int64 = nowEpochMs(),
        simulated: Bool = false
    ) throws -> SmartTransitionResult {
        let state = smart.state
        guard let place = state.places.first(where: { $0.id == placeId }) else { return ignored("Unknown smart place") }
        let catalog = profiles.catalog
        let activeProfileId = catalog.activeProfileId
        let decision = SmartProfilePolicy.decide(
            place: place,
            transition: transition,
            state: state,
            activeProfileId: activeProfileId,
            availableProfileIds: Set(catalog.profiles.map(\.id)),
            nowEpochMs: now
        )
        guard decision.type != .ignore,
              let targetId = decision.targetProfileId,
              let target = catalog.profiles.first(where: { $0.id == targetId }) else {
            smart.recordIgnoredTransition(place, transition: transition, nowEpochMs: now)
            return ignored("No profile change needed")
        }

        if decision.type == .activate {
            try profiles.setActive(target.id)
            smart.recordAutomaticActivation(
                place,
                transition: transition,
                previousProfileId: activeProfileId,
                targetProfileName: target.name,
                nowEpochMs: now
            )
            return SmartTransitionResult(
                type: .activated,
                title: "QuietCue changed profiles",
                message: "\(place.name): \(target.name) is now active"
            )
        }

        smart.publishSuggestion(
            SmartProfileSuggestion(
                id: UUID().uuidString.lowercased(),
                placeId: place.id,
                placeName: place.name,
                targetProfileId: target.id,
                targetProfileName: target.name,
                transition: transition,
                createdAtEpochMs: now,
                previousProfileId: transition == .enter ? activeProfileId : nil,
                simulated: simulated
            )
        )
        return SmartTransitionResult(
            type: .suggested,
            title: transition == .enter ? "Profile suggestion for \(place.name)" : "Leaving \(place.name)?",
            message: "Switch to \(target.name)?"
        )
    }

    func acceptSuggestion(always: Bool) throws -> SmartProfileSuggestion? {
        guard let suggestion = smart.state.suggestion else { return nil }
        try profiles.setActive(suggestion.targetProfileId)
        return smart.acceptSuggestion(always: always)
    }

    private func ignored(_ message: String) -> SmartTransitionResult {
        SmartTransitionResult(type: .ignored, title: "Smart profiles", message: message)
    }
}
