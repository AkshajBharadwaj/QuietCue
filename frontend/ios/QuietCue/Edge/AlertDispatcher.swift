import Foundation

/// Port of `uno_q/linux/rpc_client/haptic_dispatcher.py`: turns hub alert
/// commands into haptic playback with duplicate suppression and cooldowns. It
/// never makes safety decisions of its own.
@MainActor
final class AlertDispatcher {
    struct Outcome {
        var event: String
        var delivered: Bool
        var reason: String
        var pattern: String
        var eventId: String

        func toWire() -> [String: Any] {
            ["event": event, "delivered": delivered, "reason": reason, "pattern": pattern, "event_id": eventId]
        }
    }

    private struct Plan {
        var pattern: String
        var intensity: Int
        var repeatCount: Int
        var customPattern: String = ""
    }

    static let defaultCooldownSeconds = 10.0
    static let emergencyCooldownSeconds = 2.0
    private static let seenEventIdLimit = 256
    private static let categoryPlans: [String: Plan] = [
        "emergency": Plan(pattern: "urgent_repeat", intensity: 255, repeatCount: 0),
        "attention": Plan(pattern: "long_pulse", intensity: 230, repeatCount: 1),
        "informational": Plan(pattern: "two_short", intensity: 190, repeatCount: 1),
    ]
    private static let strengthIntensities = ["gentle": 190, "standard": 230, "strong": 255]

    let engine: HapticEngine
    private var lastDelivered: [String: TimeInterval] = [:]
    private var seenEventIds: [String] = []
    private var pendingAckEvent: String? = nil
    private(set) var deliveredCount = 0
    private(set) var suppressedCount = 0
    private var lastTransportError: String? = nil
    private var lastDeliveredEvent: String? = nil
    /// Set when the user acknowledged from the phone since the last report.
    private var acknowledgedSinceLastReport = false

    init(engine: HapticEngine) {
        self.engine = engine
    }

    func handleDetectionResult(_ body: [String: Any]) -> [Outcome] {
        var outcomes: [Outcome] = []
        if let alerts = body["alerts"] as? [[String: Any]] {
            outcomes = alerts.map(dispatch)
        }
        if let commands = body["control_commands"] as? [[String: Any]] {
            for command in commands where command["command"] as? String == "stop_haptic" {
                stopHaptic(userInitiated: false)
            }
        }
        return outcomes
    }

    @discardableResult
    func stopHaptic(userInitiated: Bool) -> Bool {
        engine.stopHaptic()
        lastTransportError = nil
        if pendingAckEvent != nil && userInitiated { acknowledgedSinceLastReport = true }
        pendingAckEvent = nil
        return true
    }

    /// Equivalent of polling the Uno Q's hardware button.
    func pollAcknowledge() -> Bool {
        defer { acknowledgedSinceLastReport = false }
        return acknowledgedSinceLastReport
    }

    func dispatch(_ alert: [String: Any]) -> Outcome {
        let event = (alert["event"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "unknown"
        let category = (alert["category"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "informational"
        let plan = self.plan(for: alert, category: category)
        let eventId = alert["event_id"] as? String ?? ""

        if !eventId.isEmpty, seenEventIds.contains(eventId) {
            suppressedCount += 1
            return Outcome(event: event, delivered: false, reason: "duplicate_event_id", pattern: plan.pattern, eventId: eventId)
        }
        let now = ProcessInfo.processInfo.systemUptime
        let cooldown = category == "emergency" ? Self.emergencyCooldownSeconds : Self.defaultCooldownSeconds
        if let last = lastDelivered[event], now - last < cooldown {
            suppressedCount += 1
            return Outcome(event: event, delivered: false, reason: "cooldown_active", pattern: plan.pattern, eventId: eventId)
        }

        let accepted: Bool
        if plan.pattern == "custom" {
            if plan.customPattern.isEmpty {
                lastTransportError = "custom pattern has no recorded steps"
                return Outcome(event: event, delivered: false, reason: "transport_error", pattern: plan.pattern, eventId: eventId)
            }
            if pendingAckEvent != nil && category == "emergency" {
                engine.stopHaptic()
                pendingAckEvent = nil
            }
            accepted = engine.playCustomHaptic(encodedSteps: plan.customPattern, intensity: plan.intensity, repeatCount: plan.repeatCount)
        } else {
            accepted = engine.playHaptic(pattern: plan.pattern, intensity: plan.intensity, repeatCount: plan.repeatCount)
        }
        guard accepted else {
            lastTransportError = "haptic engine refused pattern \(plan.pattern)"
            if let detail = engine.lastError { lastTransportError! += ": \(detail)" }
            return Outcome(event: event, delivered: false, reason: "transport_error", pattern: plan.pattern, eventId: eventId)
        }

        lastTransportError = nil
        lastDelivered[event] = now
        lastDeliveredEvent = event
        deliveredCount += 1
        if !eventId.isEmpty { rememberEventId(eventId) }
        if alert["requires_ack"] as? Bool == true { pendingAckEvent = event }
        return Outcome(event: event, delivered: true, reason: "delivered", pattern: plan.pattern, eventId: eventId)
    }

    func healthSnapshot() -> [String: Any] {
        [
            "transport_healthy": engine.healthCheck(),
            "delivered": deliveredCount,
            "suppressed": suppressedCount,
            "pending_ack_event": pendingAckEvent as Any? ?? NSNull(),
            "last_delivered_event": lastDeliveredEvent as Any? ?? NSNull(),
            "last_transport_error": lastTransportError as Any? ?? NSNull(),
        ]
    }

    private func plan(for alert: [String: Any], category: String) -> Plan {
        let base = Self.categoryPlans[category] ?? Self.categoryPlans["informational"]!
        let intensity = (alert["strength"] as? String).flatMap { Self.strengthIntensities[$0] } ?? base.intensity
        if let pattern = alert["pattern"] as? String, !pattern.isEmpty {
            return Plan(
                pattern: pattern,
                intensity: intensity,
                repeatCount: base.repeatCount,
                customPattern: alert["custom_pattern"] as? String ?? ""
            )
        }
        return Plan(pattern: base.pattern, intensity: intensity, repeatCount: base.repeatCount)
    }

    private func rememberEventId(_ eventId: String) {
        seenEventIds.append(eventId)
        if seenEventIds.count > Self.seenEventIdLimit {
            seenEventIds.removeFirst(seenEventIds.count - Self.seenEventIdLimit)
        }
    }
}
