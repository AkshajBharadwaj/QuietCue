import SwiftUI

/// Sound enrollment for the iPhone demo. The hub captures fingerprints from
/// the live microphone stream, which on this demo is the iPhone itself.
///
/// Unlike the Android guided session (play the sound 4-6 times in ten
/// seconds), each capture here records the sound once. One example is enough
/// to save; more can be added, and from three on the matcher requires a second
/// example to agree before it alerts.
struct SoundEnrollmentView: View {
    private static let captureDurationMs = 5_000

    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    var initialName: String
    var initialDescription: String
    var onBack: () -> Void
    var onEnroll: (SoundDefinition) -> Void

    @State private var name: String
    @State private var descriptionText: String
    @State private var priority: AlertPriority = .attention
    @State private var positives: [CapturedFingerprint] = []
    @State private var background: CapturedFingerprint? = nil
    @State private var confusingSounds: [CapturedFingerprint] = []
    @State private var testResult: String? = nil
    @State private var captureSummary: String? = nil
    @State private var recordingLabel: String? = nil
    @State private var error: String? = nil

    init(initialName: String, initialDescription: String, onBack: @escaping () -> Void, onEnroll: @escaping (SoundDefinition) -> Void) {
        self.initialName = initialName
        self.initialDescription = initialDescription
        self.onBack = onBack
        self.onEnroll = onEnroll
        _name = State(initialValue: initialName)
        _descriptionText = State(initialValue: initialDescription)
    }

    private func capture(_ label: String, onCaptured: @escaping (EnrollmentCapture) -> Void) {
        Task {
            recordingLabel = label
            error = nil
            do {
                onCaptured(try await model.captureEnrollmentSession(durationMs: Self.captureDurationMs, minRepeats: 1))
            } catch {
                self.error = error.localizedDescription
            }
            recordingLabel = nil
        }
    }

    var body: some View {
        EditorScaffold(title: "Enroll a sound", onBack: onBack) {
            VStack(alignment: .leading, spacing: 16) {
                Text("Tap Record, then play the sound once. One example is enough to save; adding two or three more from different distances makes matching more reliable. QuietCue listens through the iPhone microphone, ignores speech and incidental sounds, and immediately discards raw audio.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        MaterialTextField(label: "Sound name", text: $name, placeholder: "Apartment buzzer", limit: 40)
                        MaterialTextField(label: "Description", text: $descriptionText, placeholder: "The buzzer near my front door", minLines: 2, limit: 120)
                        Text("Urgency").font(MaterialType.labelLarge)
                        OptionChips(options: AlertPriority.allCases, selected: priority, label: \.displayName) { priority = $0 }
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Image(systemName: "waveform").font(.system(size: 22))
                            Text("Sound examples").font(MaterialType.titleLarge)
                        }
                        Text("Keep normal room noise present, but do not talk while recording. If you add more examples, vary the sound's distance or angle.")
                            .font(MaterialType.bodyLarge)
                        ForEach(Array(positives.enumerated()), id: \.offset) { index, sample in
                            HStack {
                                Text("✓ Example \(index + 1): \(Int(sample.rmsDbfs.rounded())) dBFS").font(MaterialType.bodyLarge)
                                Spacer()
                                TextButtonM(label: "Remove") {
                                    positives.remove(at: index)
                                    testResult = nil
                                }
                            }
                        }
                        if positives.count >= AcousticFingerprint.minPositiveSamples && positives.count < AcousticFingerprint.recommendedPositiveSamples {
                            Text("Ready to save. Optional: \(AcousticFingerprint.recommendedPositiveSamples - positives.count) more example(s) from a different spot cut misses and false alarms.")
                                .font(MaterialType.bodyLarge)
                        }
                        if let captureSummary { Text(captureSummary).font(MaterialType.bodyLarge).foregroundStyle(scheme.primary) }
                        FilledButton(
                            label: recordingLabel.map { "\($0)…" } ?? (positives.isEmpty ? "Record the sound (5 seconds)" : "Add another example (optional)"),
                            icon: "mic.fill",
                            enabled: recordingLabel == nil && positives.count < AcousticFingerprint.maxPositiveSamples
                        ) {
                            capture("Play the sound now") { session in
                                let room = AcousticFingerprint.maxPositiveSamples - positives.count
                                let captured = Array(session.positives.prefix(room))
                                positives.append(contentsOf: captured)
                                if background == nil {
                                    background = session.background
                                }
                                testResult = nil
                                var summary = captured.count > 1
                                    ? "Captured \(captured.count) matching repeats as examples \(positives.count - captured.count + 1)–\(positives.count)"
                                    : "Captured example \(positives.count)"
                                if positives.count == captured.count {
                                    summary += " and calibrated the room"
                                }
                                if session.speechRejectedMs > 0 {
                                    summary += "; ignored \(Double(session.speechRejectedMs) / 1_000) seconds of speech"
                                }
                                captureSummary = summary + "."
                                if captured.isEmpty {
                                    captureSummary = nil
                                    error = "No clear sound was found. Move it closer to the iPhone and play it once right after tapping Record."
                                }
                            }
                        }
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Automatic background calibration").font(MaterialType.titleLarge)
                        Text("QuietCue uses the quietest part of your first recording as the room baseline.").font(MaterialType.bodyLarge)
                        Text(background.map { "✓ Room baseline: \(Int($0.rmsDbfs.rounded())) dBFS" } ?? "The baseline will be captured with your first recording.")
                            .font(MaterialType.bodyLarge)
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Confusing sounds (optional)").font(MaterialType.titleLarge)
                        Text("Add sounds that resemble this one but should not trigger it. These help set a safer threshold.").font(MaterialType.bodyLarge)
                        ForEach(Array(confusingSounds.enumerated()), id: \.offset) { index, sample in
                            HStack {
                                Text("Non-match \(index + 1): \(Int(sample.rmsDbfs.rounded())) dBFS").font(MaterialType.bodyLarge)
                                Spacer()
                                TextButtonM(label: "Remove") { confusingSounds.remove(at: index) }
                            }
                        }
                        OutlinedButtonM(label: "Add confusing sound", enabled: recordingLabel == nil && confusingSounds.count < 10) {
                            capture("Play the confusing sound now") { session in
                                confusingSounds.append(contentsOf: session.positives.prefix(10 - confusingSounds.count))
                                if session.positives.isEmpty {
                                    error = "No clear non-match was found. Play it closer to the iPhone."
                                }
                            }
                        }
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Test before saving").font(MaterialType.titleLarge)
                        Text("Play the sound once more to check whether the current example(s) recognize it.").font(MaterialType.bodyLarge)
                        OutlinedButtonM(label: "Record test", enabled: recordingLabel == nil && positives.count >= AcousticFingerprint.minPositiveSamples) {
                            capture("Play the sound now") { session in
                                let draftEnrollment = background.flatMap { bg in
                                    try? AcousticFingerprint.enroll(
                                        name: name.isEmpty ? "Test sound" : name,
                                        description: descriptionText,
                                        priority: priority,
                                        positives: positives,
                                        background: bg,
                                        confusingSounds: confusingSounds
                                    ).enrollment
                                }
                                let rawBest = session.positives.map { sample in
                                    positives.map { AcousticFingerprint.similarity(sample.features, $0.features) }.max() ?? 0
                                }.max() ?? 0
                                let matched = draftEnrollment.flatMap { enrollment in
                                    session.positives.compactMap { AcousticFingerprint.matchConfidence($0.features, enrollment: enrollment) }.max()
                                }
                                if let matched {
                                    testResult = positives.count >= AcousticFingerprint.multiSupportSamples
                                        ? "Match \(Int((matched * 100).rounded()))%, supported by more than one example"
                                        : "Match \(Int((matched * 100).rounded()))%"
                                } else {
                                    testResult = "No reliable match (\(Int((rawBest * 100).rounded()))%). Add another example recorded the way you just played it."
                                }
                            }
                        }
                        if let testResult { Text(testResult).font(MaterialType.bodyLarge) }
                    }
                    .padding(16)
                }
                if let error { Text(error).font(MaterialType.bodyLarge).foregroundStyle(scheme.error) }
                let canCreate = !name.trimmingCharacters(in: .whitespaces).isEmpty &&
                    positives.count >= AcousticFingerprint.minPositiveSamples && background != nil && recordingLabel == nil
                FilledButton(label: "Create enrolled sound", enabled: canCreate) {
                    guard let background else { return }
                    do {
                        onEnroll(try AcousticFingerprint.enroll(
                            name: name,
                            description: descriptionText,
                            priority: priority,
                            positives: positives,
                            background: background,
                            confusingSounds: confusingSounds
                        ))
                    } catch {
                        self.error = error.localizedDescription
                    }
                }
                Text("Enrollment matching is an experimental local fingerprint and must not be used as the only detector for safety-critical sounds.")
                    .font(MaterialType.labelMedium).foregroundStyle(scheme.error)
            }
        }
    }
}
