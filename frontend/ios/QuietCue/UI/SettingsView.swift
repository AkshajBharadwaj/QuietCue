import SwiftUI

/// Settings tab. Global switches live here so "My context" is only about
/// teaching QuietCue names and details. Every change saves immediately and
/// reaches the hub on the next status poll.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    @State private var phrasesDraft = ""
    @State private var phrasesLoaded = false

    var body: some View {
        let settings = model.memoryBank.speechSettings
        let speech = model.hubSpeech
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Settings").font(MaterialType.headlineMedium).foregroundStyle(scheme.onSurface)
                    Text("Global controls for speech detection. Profiles can still force speech on or off individually.")
                        .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                }

                SectionTitle("Speech and name detection")
                MaterialCard(container: scheme.surfaceContainer) {
                    VStack(alignment: .leading, spacing: 14) {
                        SwitchRow(
                            title: settings.enabled ? "Speech detection on" : "Speech detection off",
                            description: "Runs on the Mac hub only. Audio and transcripts are never stored; only a matched name or phrase becomes an alert.",
                            isOn: Binding(
                                get: { settings.enabled },
                                set: { value in model.updateSpeechSettings { $0.enabled = value } }
                            )
                        )
                        Divider()
                        Text("Whisper model on the Mac").font(MaterialType.labelLarge)
                        OptionChips(options: SpeechModel.allCases, selected: settings.model, label: \.displayName, enabled: settings.enabled) { choice in
                            model.updateSpeechSettings { $0.model = choice }
                        }
                        Text(settings.model.detail).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        Divider()
                        Text("Match strictness: \(Int((settings.sensitivity * 100).rounded()))%").font(MaterialType.labelLarge)
                        SliderM(
                            value: Binding(
                                get: { settings.sensitivity },
                                set: { value in
                                    let stepped = (value * 20).rounded() / 20
                                    model.updateSpeechSettings { $0.sensitivity = stepped }
                                }
                            ),
                            range: 0.4...0.95,
                            step: 0.05,
                            enabled: settings.enabled
                        )
                        Text("Lower catches more pronunciations; higher needs a closer spelling. 60% accepts one-letter variants of a five-letter name.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    .padding(16)
                }

                SectionTitle("What triggers an alert")
                MaterialCard(container: scheme.surfaceContainer) {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            Image(systemName: "person.text.rectangle").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Your name").font(MaterialType.titleMedium)
                                Text(model.memoryBank.identity.map { "Always on for \($0.displayName). Edit it under My context." } ?? "Enroll your name under My context to be alerted when someone calls you.")
                                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                            }
                        }
                        Divider()
                        SwitchRow(
                            title: "People in my context",
                            description: "Off by default. Turn on if hearing their names should alert you too.",
                            isOn: Binding(
                                get: { settings.listenForPeople },
                                set: { value in model.updateSpeechSettings { $0.listenForPeople = value } }
                            ),
                            enabled: settings.enabled
                        )
                        Divider()
                        MaterialTextField(
                            label: "Global phrases",
                            text: $phrasesDraft,
                            placeholder: "excuse me, front desk",
                            supporting: "Up to 20 short phrases, separated by commas. Saved when you leave the field.",
                            minLines: 2,
                            limit: 820
                        )
                        .onSubmit(savePhrases)
                    }
                    .padding(16)
                }

                SectionTitle("Hub status")
                MaterialCard(container: scheme.surfaceContainerLow) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(statusHeadline(speech)).font(MaterialType.titleMedium)
                        Text(statusDetail(speech)).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    .padding(16)
                }

                MaterialCard(container: scheme.secondaryContainer, contentColor: scheme.onSecondaryContainer) {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "lock.fill").font(.system(size: 22))
                        Text("Diagnostics show match scores and reasons only. The hub never sends what was said.")
                            .font(MaterialType.bodyLarge)
                    }
                    .padding(16)
                }
            }
            .pagePadding()
            .padding(.top, 12)
            .padding(.bottom, 28)
        }
        .scrollDismissesKeyboard(.interactively)
        .onAppear {
            if !phrasesLoaded {
                phrasesDraft = settings.globalPhrases.joined(separator: ", ")
                phrasesLoaded = true
            }
        }
        .onDisappear(perform: savePhrases)
    }

    private func savePhrases() {
        let parsed = parseCommaList(phrasesDraft, maximum: 20).map { String($0.prefix(40)) }
        model.updateSpeechSettings { $0.globalPhrases = parsed }
    }

    private func statusHeadline(_ speech: HubSpeechStatus) -> String {
        if let error = speech.error { return "Speech error: \(error)" }
        if speech.pending { return "Transcribing on the Mac…" }
        if let ms = speech.inferenceMs { return "Whisper ready • last decode \(Int(ms)) ms" }
        return "Waiting for speech"
    }

    private func statusDetail(_ speech: HubSpeechStatus) -> String {
        guard let window = speech.lastWindowMs else {
            return "The model loads when the first speech window arrives from the iPhone microphone."
        }
        var parts = ["Last window \(window) ms"]
        if let score = speech.lastMatchScore { parts.append("best match \(Int((score * 100).rounded()))%") }
        if let asr = speech.lastAsrConfidence { parts.append("ASR confidence \(Int((asr * 100).rounded()))%") }
        if speech.lastMatched {
            parts.append("name matched")
        } else if let reason = speech.lastRejectReason {
            parts.append(rejectLabel(reason))
        }
        return parts.joined(separator: " • ")
    }

    private func rejectLabel(_ reason: String) -> String {
        switch reason {
        case "no_speech": return "no words recognized"
        case "no_tokens": return "empty transcript"
        case "below_sensitivity": return "nothing close to a configured name"
        case "asr_confidence_floor": return "rejected as a likely mishearing"
        default: return reason.replacingOccurrences(of: "_", with: " ")
        }
    }
}
