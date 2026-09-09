import SwiftUI

/// Ports of the Android `MemoryEditorScreens`.

struct SpeechSettingsView: View {
    @Environment(\.scheme) private var scheme
    var initial: SpeechSettings
    var identityAvailable: Bool
    var onBack: () -> Void
    var onSave: (SpeechSettings) -> Void

    @State private var enabled: Bool
    @State private var model: SpeechModel
    @State private var sensitivity: Float
    @State private var listenForIdentity: Bool
    @State private var listenForPeople: Bool
    @State private var phrases: String

    init(initial: SpeechSettings, identityAvailable: Bool, onBack: @escaping () -> Void, onSave: @escaping (SpeechSettings) -> Void) {
        self.initial = initial
        self.identityAvailable = identityAvailable
        self.onBack = onBack
        self.onSave = onSave
        _enabled = State(initialValue: initial.enabled)
        _model = State(initialValue: initial.model)
        _sensitivity = State(initialValue: initial.sensitivity)
        _listenForIdentity = State(initialValue: initial.listenForIdentity)
        _listenForPeople = State(initialValue: initial.listenForPeople)
        _phrases = State(initialValue: initial.globalPhrases.joined(separator: ", "))
    }

    var body: some View {
        EditorScaffold(title: "Speech and names", onBack: onBack) {
            VStack(alignment: .leading, spacing: 16) {
                Text("Speech stays on the active hub. Audio and transcripts are never saved; only a matched configured phrase can become an alert.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialCard {
                    VStack(alignment: .leading, spacing: 14) {
                        SwitchRow(title: "Enable speech detection",
                                  description: "Profiles set to Off still remain silent; Always on profiles override this switch.",
                                  isOn: $enabled)
                        Text("On-device model").font(MaterialType.labelLarge)
                        OptionChips(options: SpeechModel.allCases, selected: model, label: \.displayName) { model = $0 }
                        Text("Match sensitivity: \(Int((sensitivity * 100).rounded()))%").font(MaterialType.labelLarge)
                        SliderM(value: Binding(get: { sensitivity }, set: { sensitivity = ($0 * 20).rounded() / 20 }),
                                range: 0.4...0.95, step: 0.05)
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Who and what triggers an alert").font(MaterialType.titleLarge)
                        SwitchRow(
                            title: "My name and aliases",
                            description: identityAvailable ? "Use your approved identity enrollment as alert phrases." : "Enroll your name from My context to use this option.",
                            isOn: Binding(get: { listenForIdentity && identityAvailable }, set: { listenForIdentity = $0 }),
                            enabled: identityAvailable
                        )
                        SwitchRow(title: "People in my context",
                                  description: "Off by default. Turn on only if their names should alert you too.",
                                  isOn: $listenForPeople)
                        MaterialTextField(label: "Global phrases", text: $phrases, placeholder: "excuse me, front desk",
                                          supporting: "Separate up to 20 phrases with commas.", minLines: 2, limit: 820)
                    }
                    .padding(16)
                }
                FilledButton(label: "Save speech settings") {
                    onSave(SpeechSettings(
                        enabled: enabled,
                        model: model,
                        sensitivity: sensitivity,
                        listenForIdentity: listenForIdentity,
                        listenForPeople: listenForPeople,
                        globalPhrases: parseCommaList(phrases, maximum: 20).map { String($0.prefix(40)) }
                    ))
                }
            }
        }
    }
}

struct IdentityEnrollmentView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.scheme) private var scheme
    var initial: UserIdentity?
    var onBack: () -> Void
    var onSave: (UserIdentity) -> Void

    @State private var name: String
    @State private var pronunciation: String
    @State private var aliases: String
    @State private var samples: [String]
    @State private var listening = false
    @State private var error: String? = nil

    init(initial: UserIdentity?, onBack: @escaping () -> Void, onSave: @escaping (UserIdentity) -> Void) {
        self.initial = initial
        self.onBack = onBack
        self.onSave = onSave
        _name = State(initialValue: initial?.displayName ?? "")
        _pronunciation = State(initialValue: initial?.pronunciation ?? "")
        _aliases = State(initialValue: initial?.aliases.joined(separator: ", ") ?? "")
        _samples = State(initialValue: initial?.recognitionPhrases ?? [])
    }

    var body: some View {
        EditorScaffold(title: "Enroll your name", onBack: onBack) {
            VStack(alignment: .leading, spacing: 16) {
                Text("Your name and approved variants help the local speech model recognize when someone calls you.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        MaterialTextField(label: "Your name", text: $name, placeholder: "Akshaj", limit: 60)
                        MaterialTextField(label: "Pronunciation guide", text: $pronunciation, placeholder: "Ak-shudge", limit: 80)
                        MaterialTextField(label: "Nicknames or aliases", text: $aliases, supporting: "Separate entries with commas.", limit: 320)
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Voice checks").font(MaterialType.titleLarge)
                        Text("Have someone say your name naturally. The phone keeps only the recognized text, never the recording. You can save up to three checks.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        ForEach(Array(samples.enumerated()), id: \.offset) { index, sample in
                            HStack {
                                Text("\(index + 1). “\(sample)”").font(MaterialType.bodyLarge)
                                Spacer()
                                IconButtonM(systemName: "trash", label: "Remove voice check \(index + 1)") { samples.remove(at: index) }
                            }
                        }
                        FilledButton(label: listening ? "Listening…" : "Record voice check \(samples.count + 1)", icon: "mic.fill",
                                     enabled: !listening && samples.count < 3) {
                            Task {
                                listening = true
                                error = nil
                                do {
                                    let text = try await app.recognizeNameSample()
                                    if !samples.contains(where: { $0.caseInsensitiveCompare(text) == .orderedSame }) { samples.append(text) }
                                } catch {
                                    self.error = error.localizedDescription
                                }
                                listening = false
                            }
                        }
                    }
                    .padding(16)
                }
                if let error { Text(error).font(MaterialType.bodyLarge).foregroundStyle(scheme.error) }
                FilledButton(label: "Save name enrollment", enabled: !name.trimmingCharacters(in: .whitespaces).isEmpty && !listening) {
                    onSave(UserIdentity(
                        displayName: name.trimmingCharacters(in: .whitespaces),
                        pronunciation: pronunciation.trimmingCharacters(in: .whitespaces),
                        aliases: parseCommaList(aliases, maximum: 10),
                        recognitionPhrases: samples
                    ))
                }
            }
        }
    }
}

struct PersonMemoryEditorView: View {
    @Environment(\.scheme) private var scheme
    var initial: PersonMemory?
    var onBack: () -> Void
    var onSave: (PersonMemory) -> Void

    @State private var id: String
    @State private var name: String
    @State private var relationship: String
    @State private var pronunciation: String
    @State private var aliases: String
    @State private var notes: String

    init(initial: PersonMemory?, onBack: @escaping () -> Void, onSave: @escaping (PersonMemory) -> Void) {
        self.initial = initial
        self.onBack = onBack
        self.onSave = onSave
        _id = State(initialValue: initial?.id ?? UUID().uuidString.lowercased())
        _name = State(initialValue: initial?.name ?? "")
        _relationship = State(initialValue: initial?.relationship ?? "")
        _pronunciation = State(initialValue: initial?.pronunciation ?? "")
        _aliases = State(initialValue: initial?.aliases.joined(separator: ", ") ?? "")
        _notes = State(initialValue: initial?.notes ?? "")
    }

    var body: some View {
        EditorScaffold(title: initial.map { "Edit \($0.name)" } ?? "Add a person", onBack: onBack) {
            VStack(alignment: .leading, spacing: 12) {
                Text("People are added only when you enter them here. Their names help local transcription and trigger alerts only if you enable that audience in Speech and names.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialTextField(label: "Name", text: $name, placeholder: "Maya", limit: 60)
                MaterialTextField(label: "Relationship", text: $relationship, placeholder: "Sister", limit: 80)
                MaterialTextField(label: "Pronunciation", text: $pronunciation, placeholder: "My-uh", limit: 80)
                MaterialTextField(label: "Aliases", text: $aliases, placeholder: "May, M", limit: 320)
                MaterialTextField(label: "Notes", text: $notes, placeholder: "Lives nearby and usually visits on weekends",
                                  supporting: "\(notes.count)/280", minLines: 3, limit: 280)
                FilledButton(label: "Save person", enabled: !name.trimmingCharacters(in: .whitespaces).isEmpty) {
                    onSave(PersonMemory(
                        id: id,
                        name: name.trimmingCharacters(in: .whitespaces),
                        relationship: relationship.trimmingCharacters(in: .whitespaces),
                        pronunciation: pronunciation.trimmingCharacters(in: .whitespaces),
                        aliases: parseCommaList(aliases, maximum: 10),
                        notes: notes.trimmingCharacters(in: .whitespacesAndNewlines)
                    ))
                }
            }
        }
    }
}

struct ContextMemoryEditorView: View {
    @Environment(\.scheme) private var scheme
    var initial: ContextMemory?
    var onBack: () -> Void
    var onSave: (ContextMemory) -> Void

    @State private var id: String
    @State private var title: String
    @State private var details: String

    init(initial: ContextMemory?, onBack: @escaping () -> Void, onSave: @escaping (ContextMemory) -> Void) {
        self.initial = initial
        self.onBack = onBack
        self.onSave = onSave
        _id = State(initialValue: initial?.id ?? UUID().uuidString.lowercased())
        _title = State(initialValue: initial?.title ?? "")
        _details = State(initialValue: initial?.details ?? "")
    }

    var body: some View {
        EditorScaffold(title: initial.map { "Edit \($0.title)" } ?? "Add context", onBack: onBack) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Add only details you want QuietCue to use as local transcription context. Nothing is inferred automatically.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialTextField(label: "Title", text: $title, placeholder: "Tuesday class", limit: 80)
                MaterialTextField(label: "Details", text: $details, placeholder: "My Tuesday accessibility design class is in Building 4.",
                                  supporting: "\(details.count)/500", minLines: 5, limit: 500)
                let valid = !title.trimmingCharacters(in: .whitespaces).isEmpty && !details.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                FilledButton(label: "Save context", enabled: valid) {
                    onSave(ContextMemory(id: id, title: title.trimmingCharacters(in: .whitespaces),
                                         details: details.trimmingCharacters(in: .whitespacesAndNewlines)))
                }
            }
        }
    }
}

/// Top bar + scrolling body used by every sub-screen.
struct EditorScaffold<Content: View>: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var onBack: () -> Void
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 0) {
            EditorTopBar(title: title, onBack: onBack)
            ScrollView {
                content()
                    .pagePadding()
                    .padding(.top, 12)
                    .padding(.bottom, 28)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .background(scheme.background)
    }
}
