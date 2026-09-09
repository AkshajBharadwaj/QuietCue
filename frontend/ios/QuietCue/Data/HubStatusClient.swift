import Foundation

struct HubStatusError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// Speech-related fields the hub attaches to its latest inference result.
/// Diagnostics are scores and reasons only; the hub never sends transcripts.
struct HubSpeechStatus: Equatable {
    var pending: Bool = false
    var error: String? = nil
    var inferenceMs: Double? = nil
    var transcript: String? = nil
    var voiceDetected: Bool = false
    var lastWindowMs: Int? = nil
    var lastMatchScore: Double? = nil
    var lastAsrConfidence: Double? = nil
    var lastMatched: Bool = false
    var lastRejectReason: String? = nil
}

/// Result of asking the Mac's Whisper model how it spells a name.
struct NameSpellingResult: Equatable {
    var heard: [String]
    var recognized: Bool
}

/// Talks to the hub's status API (`backend/app/status_server.py`), the same
/// endpoints the Android `AlertRepository` uses.
struct HubStatusClient {
    var baseURL: URL
    var timeout: TimeInterval = 2

    func fetchState() async throws -> (RuntimeState, HubSpeechStatus) {
        let json = try await request(method: "GET", path: "/api/state")
        return (Self.parseState(json), Self.parseSpeech(json))
    }

    func syncProfile(_ document: Data) async throws {
        _ = try await request(method: "PUT", path: "/api/state", body: document)
    }

    func stopHaptic(eventId: String) async throws {
        _ = try await request(method: "POST", path: "/api/haptics/stop", json: ["event_id": eventId])
    }

    func setInferenceDevice(_ device: InferenceDevice) async throws {
        _ = try await request(method: "POST", path: "/api/inference/device", json: ["device": device.rawValue])
    }

    /// `minRepeats` 1 records a single example (the loudest event in the
    /// session wins); 3 is the guided multi-repeat session the Android app uses.
    func captureEnrollmentSession(durationMs: Int = 5_000, minRepeats: Int = 1) async throws -> EnrollmentCapture {
        guard (4_000...15_000).contains(durationMs) else { throw HubStatusError(message: "Invalid enrollment duration") }
        guard (1...3).contains(minRepeats) else { throw HubStatusError(message: "Invalid enrollment repeat count") }
        _ = try await request(method: "POST", path: "/api/enrollment/start", json: ["duration_ms": durationMs, "min_repeats": minRepeats])
        let deadline = Date().addingTimeInterval(Double(durationMs) / 1_000 + 15)
        while Date() < deadline {
            let status = try await request(method: "GET", path: "/api/enrollment/status")
            switch status["state"] as? String {
            case "complete":
                return try Self.parseEnrollmentCapture(status)
            case "error":
                throw HubStatusError(message: status["error"] as? String ?? "Enrollment capture failed")
            case "recording":
                try await Task.sleep(for: .milliseconds(250))
            default:
                throw HubStatusError(message: "The QuietCue hub did not start enrollment")
            }
        }
        _ = try? await request(method: "POST", path: "/api/enrollment/cancel")
        throw HubStatusError(message: "No live microphone audio reached the enrollment session")
    }

    /// The hub records `durationMs` of the live iPhone stream, transcribes it
    /// with the same Whisper model the detector uses, and returns only the
    /// word(s) it produced for the name.
    func learnNameSpelling(name: String, knownSpellings: [String], durationMs: Int = 4_000) async throws -> NameSpellingResult {
        _ = try await request(method: "POST", path: "/api/name-enrollment/start", json: [
            "name": name,
            "known_spellings": knownSpellings,
            "duration_ms": durationMs,
        ])
        let deadline = Date().addingTimeInterval(Double(durationMs) / 1_000 + 20)
        while Date() < deadline {
            let status = try await request(method: "GET", path: "/api/name-enrollment/status")
            switch status["state"] as? String {
            case "complete":
                return NameSpellingResult(
                    heard: status["heard"] as? [String] ?? [],
                    recognized: status["recognized"] as? Bool == true
                )
            case "error":
                throw HubStatusError(message: status["error"] as? String ?? "The hub could not learn the name")
            case "recording", "processing":
                try await Task.sleep(for: .milliseconds(250))
            default:
                throw HubStatusError(message: "The QuietCue hub did not start listening")
            }
        }
        _ = try? await request(method: "POST", path: "/api/name-enrollment/cancel")
        throw HubStatusError(message: "No live microphone audio reached the hub; check that the iPhone is streaming")
    }

    // MARK: Parsing

    static func parseState(_ json: [String: Any]) -> RuntimeState {
        let hub = json["hub"] as? [String: Any]
        let profile = json["active_profile"] as? [String: Any]
        let inference = json["inference"] as? [String: Any]
        let routingError = inference?["error"] as? String
        return RuntimeState(
            backendConnected: json["status"] as? String == "ready",
            audioSourceConnected: hub?["audio_source_connected"] as? Bool == true,
            backendProfileName: (profile?["name"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            latestAlert: (json["latest_alert"] as? [String: Any]).map(parseAlert),
            requestedInferenceDevice: InferenceDevice.fromWire(inference?["requested_device"] as? String),
            activeInferenceDevice: InferenceDevice.fromWire(inference?["active_device"] as? String),
            phoneInferenceAvailable: inference?["samsung_available"] as? Bool == true,
            inferenceSwitchPending: inference?["switch_pending"] as? Bool == true,
            inferenceRoutingError: routingError.flatMap { $0.isEmpty ? nil : $0 }
        )
    }

    static func parseSpeech(_ json: [String: Any]) -> HubSpeechStatus {
        guard let result = json["latest_result"] as? [String: Any] else { return HubSpeechStatus() }
        let diagnostics = result["speech_diagnostics"] as? [String: Any]
        return HubSpeechStatus(
            pending: result["speech_pending"] as? Bool == true,
            error: (result["speech_error"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            inferenceMs: result["speech_inference_ms"] as? Double,
            transcript: (result["transcript"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            voiceDetected: result["voice_detected"] as? Bool == true,
            lastWindowMs: diagnostics?["window_ms"] as? Int,
            lastMatchScore: diagnostics?["match_score"] as? Double,
            lastAsrConfidence: diagnostics?["asr_confidence"] as? Double,
            lastMatched: diagnostics?["matched"] as? Bool == true,
            lastRejectReason: (diagnostics?["reject_reason"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        )
    }

    static func parseAlert(_ json: [String: Any]) -> DetectedAlert {
        DetectedAlert(
            eventId: json["event_id"] as? String ?? "",
            event: json["event"] as? String ?? "unknown_event",
            confidence: Float(json["confidence"] as? Double ?? 0),
            category: json["category"] as? String ?? "informational",
            pattern: json["pattern"] as? String ?? "none",
            profileName: json["profile_name"] as? String ?? "Unknown profile",
            sourceLabel: json["source_label"] as? String ?? "",
            totalLatencyMs: json["total_after_capture_ms"] as? Int ?? 0,
            requiresAcknowledgement: json["requires_ack"] as? Bool ?? false,
            simulated: json["simulated"] as? Bool ?? true,
            fallbackToPhone: json["fallback_to_phone"] as? Bool ?? false,
            hapticActive: json["haptic_active"] as? Bool ?? false,
            acknowledgedAtMs: (json["acknowledged_at_ms"] as? NSNumber)?.int64Value
        )
    }

    private static func parseEnrollmentCapture(_ json: [String: Any]) throws -> EnrollmentCapture {
        let positives = (json["positives"] as? [[String: Any]] ?? []).compactMap(parseFingerprint)
        guard let backgroundJson = json["background"] as? [String: Any], let background = parseFingerprint(backgroundJson) else {
            throw HubStatusError(message: "The enrollment session did not capture background audio")
        }
        return EnrollmentCapture(
            positives: positives,
            background: background,
            speechRejectedMs: json["speech_rejected_ms"] as? Int ?? 0
        )
    }

    private static func parseFingerprint(_ json: [String: Any]) -> CapturedFingerprint? {
        guard let features = json["features"] as? [Double], features.count == 8 else { return nil }
        return CapturedFingerprint(
            features: features.map(Float.init),
            rmsDbfs: Float(json["rms_dbfs"] as? Double ?? -180)
        )
    }

    // MARK: Transport

    private func request(method: String, path: String, json: [String: Any]) async throws -> [String: Any] {
        try await request(method: method, path: path, body: try JSONSerialization.data(withJSONObject: json))
    }

    private func request(method: String, path: String, body: Data? = nil) async throws -> [String: Any] {
        var request = URLRequest(url: baseURL.appendingPathComponent(path), timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw HubStatusError(message: "QuietCue hub gave no HTTP response") }
        guard http.statusCode == 200 else { throw HubStatusError(message: "QuietCue hub returned HTTP \(http.statusCode)") }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw HubStatusError(message: "QuietCue hub returned an invalid document")
        }
        return json
    }
}
