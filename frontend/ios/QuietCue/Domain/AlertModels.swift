import Foundation

struct DetectedAlert: Equatable, Hashable {
    var eventId: String
    var event: String
    var confidence: Float
    var category: String
    var pattern: String
    var profileName: String
    var sourceLabel: String
    var totalLatencyMs: Int
    var requiresAcknowledgement: Bool
    var simulated: Bool
    var fallbackToPhone: Bool
    var hapticActive: Bool = false
    var acknowledgedAtMs: Int64? = nil

    var displayName: String {
        if event.hasPrefix("custom:"), sourceLabel.hasPrefix("enrolled: ") {
            return String(sourceLabel.dropFirst("enrolled: ".count))
        }
        return event.split(separator: "_").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
    }
}

enum InferenceDevice: String, CaseIterable {
    case copilotPC = "copilot_pc"
    case phone = "samsung_phone"

    var displayName: String {
        switch self {
        case .copilotPC: return "PC"
        case .phone: return "iPhone"
        }
    }

    static func fromWire(_ value: String?) -> InferenceDevice {
        allCases.first { $0.rawValue == value } ?? .copilotPC
    }
}

struct RuntimeState: Equatable {
    var backendConnected: Bool = false
    var audioSourceConnected: Bool = false
    var backendProfileName: String? = nil
    var latestAlert: DetectedAlert? = nil
    var errorMessage: String? = nil
    var stopInProgress: Bool = false
    var requestedInferenceDevice: InferenceDevice = .copilotPC
    var activeInferenceDevice: InferenceDevice = .copilotPC
    var phoneInferenceAvailable: Bool = false
    var inferenceSwitchPending: Bool = false
    var inferenceRoutingError: String? = nil
}

/// Connection state of the phone's own microphone stream to the hub (the
/// role the Uno Q plays in the hardware demo).
struct EdgeStreamState: Equatable {
    enum Phase: Equatable {
        case idle
        case connecting
        case streaming
        case retrying(seconds: Int)
        case failed(String)
    }

    var phase: Phase = .idle
    var microphoneAuthorized: Bool = false
    var chunksSent: Int = 0
    var lastRmsDbfs: Float? = nil
    var lastRoundTripMs: Int? = nil
    var hubNodeId: String? = nil
    var hapticsDelivered: Int = 0
    var lastHapticPattern: String? = nil
    var hapticPlaying: Bool = false

    var isStreaming: Bool { phase == .streaming }
}
