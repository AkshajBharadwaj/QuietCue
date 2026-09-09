import CoreHaptics
import Foundation

/// One motor on/off step. Timings copied from `uno_q/stm32/haptics/sketch/sketch.ino`.
struct HapticStep {
    var onMs: Int
    var offMs: Int
}

/// Phone-side stand-in for the STM32 haptic firmware. Owns pattern timing, the
/// acknowledgement rule (an active emergency pattern is only replaced by another
/// emergency), and the 30-second urgent timeout.
@MainActor
final class HapticEngine {
    static let shortPulse = [HapticStep(onMs: 300, offMs: 260)]
    static let twoShort = [HapticStep(onMs: 240, offMs: 140), HapticStep(onMs: 240, offMs: 320)]
    static let longPulse = [HapticStep(onMs: 1000, offMs: 350)]
    static let urgent = [HapticStep(onMs: 250, offMs: 100), HapticStep(onMs: 250, offMs: 100), HapticStep(onMs: 250, offMs: 400)]
    static let urgentTimeoutMs = 30_000
    static let maxRepeatCount = 10

    private var engine: CHHapticEngine?
    private var player: CHHapticAdvancedPatternPlayer?
    private var timeoutTask: Task<Void, Never>?
    private(set) var activePattern: String? = nil
    /// True while a pattern that runs until acknowledged is active (the STM32's
    /// `cycles_remaining < 0`).
    private(set) var awaitingAcknowledgement = false
    private(set) var patternsPlayed = 0
    private(set) var lastAckMs: Int64 = 0
    let supportsHaptics: Bool
    /// Last Core Haptics failure, surfaced in the hub health snapshot.
    private(set) var lastError: String? = nil
    var onStateChange: ((Bool) -> Void)?

    init() {
        supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics
    }

    var isPlaying: Bool { activePattern != nil }

    func healthCheck() -> Bool {
        guard supportsHaptics else { return true }
        return (try? prepareEngine()) != nil
    }

    // MARK: RPC-equivalent surface

    func playHaptic(pattern: String, intensity: Int, repeatCount: Int) -> Bool {
        let steps: [HapticStep]
        switch pattern {
        case "short_pulse": steps = Self.shortPulse
        case "two_short": steps = Self.twoShort
        case "long_pulse": steps = Self.longPulse
        case "urgent_repeat": steps = Self.urgent
        default: return false
        }
        if awaitingAcknowledgement && pattern != "urgent_repeat" { return false }
        let untilStopped = pattern == "urgent_repeat" && repeatCount <= 0
        let cycles = untilStopped ? -1 : clampRepeat(pattern == "urgent_repeat" ? repeatCount : repeatCount)
        return start(name: pattern, steps: steps, intensity: intensity, cycles: cycles, timeout: pattern == "urgent_repeat")
    }

    func playCustomHaptic(encodedSteps: String, intensity: Int, repeatCount: Int) -> Bool {
        if awaitingAcknowledgement { return false }
        guard let steps = Self.parseCustom(encodedSteps) else { return false }
        let cycles = repeatCount > 0 ? clampRepeat(repeatCount) : -1
        return start(name: "custom", steps: steps, intensity: intensity, cycles: cycles, timeout: cycles < 0)
    }

    @discardableResult
    func stopHaptic() -> Bool {
        if awaitingAcknowledgement { lastAckMs = nowEpochMs() }
        stopPattern()
        return true
    }

    /// Plays a pattern for previews in the editor; ignores the ack rule.
    func preview(steps: [HapticStep]) {
        _ = start(name: "preview", steps: steps, intensity: 230, cycles: 1, timeout: false)
    }

    static func parseCustom(_ encoded: String) -> [HapticStep]? {
        guard !encoded.isEmpty, encoded.count <= 79 else { return nil }
        var steps: [HapticStep] = []
        var total = 0
        for part in encoded.split(separator: ";", omittingEmptySubsequences: false) {
            let phases = part.split(separator: ",", omittingEmptySubsequences: false)
            guard phases.count == 2, let on = Int(phases[0]), let off = Int(phases[1]),
                  (100...2_000).contains(on), (80...2_000).contains(off) else { return nil }
            total += on + off
            guard total <= 10_000, steps.count < 6 else { return nil }
            steps.append(HapticStep(onMs: on, offMs: off))
        }
        return steps.isEmpty ? nil : steps
    }

    // MARK: Pattern engine

    private func start(name: String, steps: [HapticStep], intensity: Int, cycles: Int, timeout: Bool) -> Bool {
        stopPattern(resetAck: true)
        let clampedIntensity = intensity <= 0 ? 255 : min(max(intensity, 180), 255)
        let strength = Float(clampedIntensity - 180) / Float(255 - 180) * 0.35 + 0.65
        activePattern = name
        awaitingAcknowledgement = cycles < 0
        patternsPlayed += 1
        onStateChange?(true)

        let cycleDuration = steps.reduce(0.0) { $0 + Double($1.onMs + $1.offMs) / 1_000 }
        let finiteCycles = cycles < 0 ? 1 : cycles
        if supportsHaptics {
            var events: [CHHapticEvent] = []
            var time = 0.0
            for _ in 0..<finiteCycles {
                for step in steps {
                    events.append(
                        CHHapticEvent(
                            eventType: .hapticContinuous,
                            parameters: [
                                CHHapticEventParameter(parameterID: .hapticIntensity, value: strength),
                                CHHapticEventParameter(parameterID: .hapticSharpness, value: 0.6),
                            ],
                            relativeTime: time,
                            duration: Double(step.onMs) / 1_000
                        )
                    )
                    time += Double(step.onMs + step.offMs) / 1_000
                }
            }
            // The microphone reconfigures the shared audio session when streaming
            // starts or stops, which stops a Core Haptics engine created earlier.
            // The stopped handler is delivered asynchronously, so a cached engine
            // can still look alive here: on any failure throw it away and retry
            // once with a fresh one.
            var started = false
            for attempt in 0..<2 {
                do {
                    let engine = try prepareEngine()
                    let pattern = try CHHapticPattern(events: events, parameters: [])
                    let player = try engine.makeAdvancedPlayer(with: pattern)
                    player.loopEnabled = cycles < 0
                    player.loopEnd = cycleDuration
                    player.completionHandler = { [weak self] _ in
                        Task { @MainActor in
                            guard let self, self.activePattern == name, !self.awaitingAcknowledgement else { return }
                            self.stopPattern()
                        }
                    }
                    self.player = player
                    try player.start(atTime: CHHapticTimeImmediate)
                    started = true
                    break
                } catch {
                    player = nil
                    engine?.stop(completionHandler: nil)
                    engine = nil
                    if attempt == 1 { lastError = String(describing: error) }
                }
            }
            if !started {
                activePattern = nil
                awaitingAcknowledgement = false
                onStateChange?(false)
                return false
            }
        } else {
            // No haptic hardware (simulator): keep the state machine so the UI and
            // the hub see the same delivery lifecycle.
            if cycles >= 0 {
                let total = cycleDuration * Double(finiteCycles)
                timeoutTask = Task { [weak self] in
                    try? await Task.sleep(for: .seconds(total))
                    guard !Task.isCancelled else { return }
                    self?.stopPattern()
                }
            }
        }
        if timeout {
            timeoutTask?.cancel()
            timeoutTask = Task { [weak self] in
                try? await Task.sleep(for: .milliseconds(Self.urgentTimeoutMs))
                guard !Task.isCancelled else { return }
                self?.stopPattern()
            }
        }
        return true
    }

    private func stopPattern(resetAck: Bool = true) {
        timeoutTask?.cancel()
        timeoutTask = nil
        try? player?.stop(atTime: CHHapticTimeImmediate)
        player = nil
        let wasActive = activePattern != nil
        activePattern = nil
        if resetAck { awaitingAcknowledgement = false }
        if wasActive { onStateChange?(false) }
    }

    private func prepareEngine() throws -> CHHapticEngine {
        if let engine {
            // Starting an already running engine is a no-op; a stopped one comes back.
            try engine.start()
            return engine
        }
        let engine = try CHHapticEngine()
        engine.playsHapticsOnly = true
        engine.isAutoShutdownEnabled = false
        engine.resetHandler = { [weak self] in
            Task { @MainActor in
                guard let self else { return }
                // Players do not survive a reset; drop ours and start fresh next time.
                self.player = nil
                try? self.engine?.start()
            }
        }
        engine.stoppedHandler = { [weak self, weak engine] _ in
            Task { @MainActor in
                // Ignore late callbacks from an engine we already replaced.
                guard let self, let engine, self.engine === engine else { return }
                self.engine = nil
                self.player = nil
                // A pattern that was in flight is gone with the engine.
                if self.activePattern != nil, !self.awaitingAcknowledgement { self.stopPattern() }
            }
        }
        try engine.start()
        self.engine = engine
        return engine
    }

    private func clampRepeat(_ count: Int) -> Int { min(max(count, 1), Self.maxRepeatCount) }
}
