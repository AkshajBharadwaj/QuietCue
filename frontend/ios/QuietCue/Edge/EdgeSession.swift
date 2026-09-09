import Foundation
import Observation

/// Runs the Uno Q client loop on the phone: microphone → hub → haptics, with
/// bounded reconnect backoff. Mirrors `run_microphone_client` in
/// `uno_q/linux/transport/hub_client.py`.
@MainActor
@Observable
final class EdgeSession {
    private(set) var state = EdgeStreamState()
    let dispatcher: AlertDispatcher
    private var task: Task<Void, Never>?
    private var capture: MicrophoneCapture?
    private var settings: HubSettings
    private var phraseTriggers: [String] = []
    var onDetection: (([String: Any]) -> Void)?

    init(settings: HubSettings, dispatcher: AlertDispatcher) {
        self.settings = settings
        self.dispatcher = dispatcher
        dispatcher.engine.onStateChange = { [weak self] playing in
            self?.state.hapticPlaying = playing
        }
    }

    var isRunning: Bool { task != nil }

    func updateSettings(_ settings: HubSettings) {
        let changed = settings.host != self.settings.host || settings.audioPort != self.settings.audioPort ||
            settings.pairingToken != self.settings.pairingToken
        self.settings = settings
        if changed, isRunning {
            stop()
            start()
        }
    }

    func updatePhraseTriggers(_ phrases: [String]) {
        phraseTriggers = Array(phrases.prefix(20))
    }

    func start() {
        guard task == nil else { return }
        task = Task { [weak self] in
            await self?.run()
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        capture?.stop()
        capture = nil
        dispatcher.stopHaptic(userInitiated: false)
        state.phase = .idle
        state.hubNodeId = nil
    }

    /// Acknowledge from the phone (the Uno Q's hardware button).
    func acknowledge() {
        dispatcher.stopHaptic(userInitiated: true)
    }

    private func run() async {
        let authorized = await MicrophoneCapture.requestPermission()
        state.microphoneAuthorized = authorized
        guard authorized else {
            state.phase = .failed("Microphone access is required. Allow it in Settings.")
            task = nil
            return
        }
        var backoff = 1.0
        while !Task.isCancelled {
            do {
                try await streamOnce()
                backoff = 1.0
            } catch is CancellationError {
                break
            } catch {
                guard !Task.isCancelled else { break }
                let seconds = Int(backoff)
                state.phase = .retrying(seconds: seconds)
                state.hubNodeId = nil
                capture?.stop()
                capture = nil
                dispatcher.stopHaptic(userInitiated: false)
                try? await Task.sleep(for: .seconds(backoff))
                backoff = min(backoff * 2, 30)
            }
        }
        capture?.stop()
        capture = nil
        if !Task.isCancelled { task = nil }
    }

    private func streamOnce() async throws {
        guard !settings.host.isEmpty else {
            throw WireProtocolError(message: "Enter the Mac's address to connect")
        }
        state.phase = .connecting
        let connection = HubConnection(host: settings.host, port: settings.audioPort)
        defer { connection.close() }
        let started = Date()
        try await connection.connect()
        try await connection.send(
            WireMessage(kind: "edge_hello", body: [
                "device_id": settings.deviceId,
                "protocol": 1,
                "pairing_token": settings.pairingToken,
            ])
        )
        let hello = try await connection.receive(timeout: 5)
        guard hello.kind == "hub_hello" else {
            let message = hello.body["message"] as? String ?? "Hub rejected the session"
            throw WireProtocolError(message: message)
        }
        state.hubNodeId = hello.body["node_id"] as? String
        state.lastRoundTripMs = Int(Date().timeIntervalSince(started) * 1_000)

        // One full YAMNet patch (0.96 s) per chunk. Shorter chunks get zero-padded
        // on the hub, so half of every patch was silence and only loud, sustained
        // sounds (smoke alarms) scored above their thresholds.
        let capture = MicrophoneCapture(chunkMs: 1_000)
        self.capture = capture
        let chunks = try capture.start()
        state.phase = .streaming
        let analyzer = EdgeAnalyzer()

        for await chunk in chunks {
            try Task.checkCancellation()
            let edge = analyzer.analyze(chunk.samples)
            var body = chunk.toWire()
            body["edge_analysis"] = edge.toWire()
            body["phrase_triggers"] = phraseTriggers
            let sentAt = Date()
            try await connection.send(WireMessage(kind: "audio_chunk", body: body, payload: chunk.pcm))
            let response = try await connection.receive(timeout: 10)
            if response.kind == "error" {
                throw WireProtocolError(message: response.body["message"] as? String ?? "Hub reported an error")
            }
            guard response.kind == "detection_result" else { continue }
            state.chunksSent = chunk.sequence + 1
            state.lastRmsDbfs = edge.rmsDbfs
            state.lastRoundTripMs = Int(Date().timeIntervalSince(sentAt) * 1_000)

            let outcomes = dispatcher.handleDetectionResult(response.body)
            for outcome in outcomes where outcome.delivered {
                state.hapticsDelivered += 1
                state.lastHapticPattern = outcome.pattern
            }
            let acknowledged = dispatcher.pollAcknowledge()
            if !outcomes.isEmpty || acknowledged || chunk.sequence % 10 == 0 {
                try await connection.send(
                    WireMessage(kind: "haptic_result", body: [
                        "sequence": chunk.sequence,
                        "outcomes": outcomes.map { $0.toWire() },
                        "acknowledged": acknowledged,
                        "health": dispatcher.healthSnapshot(),
                    ])
                )
            }
            onDetection?(response.body)
        }
        throw WireProtocolError(message: "Microphone capture stopped")
    }
}
