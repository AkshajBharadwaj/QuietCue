import Foundation

/// Port of the Android `SmartProfileRepository`.
@MainActor
final class SmartProfileStore {
    private static let legacyDefaultRadius: Float = 15
    private static let reliableDefaultRadius: Float = 150

    private let file = JSONFileStore<SmartProfileState>(fileName: "smart_profiles.json")
    private var stored: SmartProfileState

    init() {
        stored = file.load() ?? SmartProfileState()
    }

    var state: SmartProfileState { clean(stored, nowEpochMs: nowEpochMs()) }

    func savePlace(_ place: SmartPlace) throws {
        var cleaned = place
        cleaned.name = place.name.trimmingCharacters(in: .whitespacesAndNewlines)
        if let error = cleaned.validationError() { throw StoreError(message: error) }
        mutate { state in
            if let index = state.places.firstIndex(where: { $0.id == cleaned.id }) {
                state.places[index] = cleaned
            } else {
                state.places.append(cleaned)
            }
            state.places.sort { $0.name.lowercased() < $1.name.lowercased() }
            state.statusMessage = "\(cleaned.name) is ready for profile suggestions"
        }
    }

    func deletePlace(_ placeId: String) {
        mutate { state in
            let wasActive = state.activePlaceId == placeId
            state.places.removeAll { $0.id == placeId }
            if state.suggestion?.placeId == placeId { state.suggestion = nil }
            if wasActive {
                state.activePlaceId = nil
                state.returnProfileId = nil
            }
            state.statusMessage = "Place removed"
        }
    }

    func removeProfile(_ profileId: String) {
        mutate { state in
            let removedPlaceIds = Set(state.places.filter { $0.profileId == profileId }.map(\.id))
            state.places.removeAll { $0.profileId == profileId }
            if let suggestion = state.suggestion,
               suggestion.targetProfileId == profileId || removedPlaceIds.contains(suggestion.placeId) {
                state.suggestion = nil
            }
            if let active = state.activePlaceId, removedPlaceIds.contains(active) { state.activePlaceId = nil }
            if state.returnProfileId == profileId { state.returnProfileId = nil }
        }
    }

    func setAutoApply(_ placeId: String, enabled: Bool) {
        mutate { state in
            state.places = state.places.map { place in
                var updated = place
                if place.id == placeId { updated.autoApply = enabled }
                return updated
            }
            state.statusMessage = enabled ? "Automatic switching enabled for this place" : "This place will ask before switching"
            if enabled {
                // An explicit instruction: do not let an earlier manual choice
                // silently block it for hours.
                state.manualOverrideUntilEpochMs = 0
                if state.suggestion?.placeId == placeId { state.suggestion = nil }
                if state.lastTransitionKey?.hasPrefix("\(placeId):") == true {
                    state.lastTransitionKey = nil
                    state.lastTransitionAtEpochMs = 0
                }
            }
        }
    }

    func recordManualOverride(nowEpochMs now: Int64 = nowEpochMs()) {
        mutate { state in
            state.suggestion = nil
            state.manualOverrideUntilEpochMs = now + SmartProfilePolicy.manualOverrideMs
            state.statusMessage = "Location automation paused for two hours after your manual choice"
        }
    }

    func recordIgnoredTransition(_ place: SmartPlace, transition: PlaceTransition, nowEpochMs now: Int64) {
        mutate { state in
            state.lastTransitionKey = "\(place.id):\(transition.rawValue)"
            state.lastTransitionAtEpochMs = now
        }
    }

    func publishSuggestion(_ suggestion: SmartProfileSuggestion) {
        mutate { state in
            state.suggestion = suggestion
            state.lastTransitionKey = "\(suggestion.placeId):\(suggestion.transition.rawValue)"
            state.lastTransitionAtEpochMs = suggestion.createdAtEpochMs
            state.statusMessage = suggestion.transition == .enter
                ? "Arrival detected at \(suggestion.placeName)"
                : "Departure detected from \(suggestion.placeName)"
        }
    }

    func recordAutomaticActivation(
        _ place: SmartPlace,
        transition: PlaceTransition,
        previousProfileId: String,
        targetProfileName: String,
        nowEpochMs now: Int64
    ) {
        mutate { state in
            state.suggestion = nil
            state.activePlaceId = transition == .enter ? place.id : nil
            state.returnProfileId = transition == .enter ? previousProfileId : nil
            state.lastTransitionKey = "\(place.id):\(transition.rawValue)"
            state.lastTransitionAtEpochMs = now
            state.statusMessage = "Switched to \(targetProfileName) automatically"
        }
    }

    @discardableResult
    func acceptSuggestion(always: Bool) -> SmartProfileSuggestion? {
        var accepted: SmartProfileSuggestion?
        mutate { state in
            guard let suggestion = state.suggestion else { return }
            accepted = suggestion
            if always && suggestion.transition == .enter {
                state.places = state.places.map { place in
                    var updated = place
                    if place.id == suggestion.placeId { updated.autoApply = true }
                    return updated
                }
            }
            state.suggestion = nil
            state.activePlaceId = suggestion.transition == .enter ? suggestion.placeId : nil
            state.returnProfileId = suggestion.transition == .enter ? suggestion.previousProfileId : nil
            state.manualOverrideUntilEpochMs = 0
            state.statusMessage = always && suggestion.transition == .enter
                ? "Switched to \(suggestion.targetProfileName); future arrivals will switch automatically"
                : "Switched to \(suggestion.targetProfileName)"
        }
        return accepted
    }

    func dismissSuggestion() {
        mutate { state in
            state.suggestion = nil
            state.statusMessage = "Location suggestion dismissed"
        }
    }

    private func mutate(_ transform: (inout SmartProfileState) -> Void) {
        var current = clean(stored, nowEpochMs: nowEpochMs())
        transform(&current)
        stored = current
        file.save(current)
    }

    private func clean(_ state: SmartProfileState, nowEpochMs now: Int64) -> SmartProfileState {
        var cleaned = state
        if let suggestion = state.suggestion, now - suggestion.createdAtEpochMs >= SmartProfilePolicy.suggestionExpiryMs {
            cleaned.suggestion = nil
        }
        cleaned.places = state.places.map { place in
            var updated = place
            if !place.demoOnly && place.radiusMeters == Self.legacyDefaultRadius {
                updated.radiusMeters = Self.reliableDefaultRadius
            }
            return updated
        }
        return cleaned
    }
}
