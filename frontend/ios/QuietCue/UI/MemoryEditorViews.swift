import SwiftUI

/// Ports of the Android `MemoryEditorScreens`. Global speech switches moved to
/// the Settings tab; these editors only teach QuietCue names and details.

struct IdentityEnrollmentView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.scheme) private var scheme
    var initial: UserIdentity?
    var onBack: () -> Void
    var onSave: (UserIdentity) -> Void

    @State private var name: String
    @State private var aliases: String
    @State private var spellings: [String]
    @State private var listening = false
    @State private var lastResult: String? = nil
    @State private var error: String? = nil

    init(initial: UserIdentity?, onBack: @escaping () -> Void, onSave: @escaping (UserIdentity) -> Void) {
        self.initial = initial
        self.onBack = onBack
        self.onSave = onSave
        _name = State(initialValue: initial?.displayName ?? "")
        _aliases = State(initialValue: initial?.aliases.joined(separator: ", ") ?? "")
        _spellings = State(initialValue: initial?.recognitionPhrases ?? [])
    }

    private var trimmedName: String { name.trimmingCharacters(in: .whitespaces) }
    private var canListen: Bool {
        !listening && !trimmedName.isEmpty && spellings.count < UserIdentity.maxLearnedSpellings && app.edge.isRunning
    }

    var body: some View {
        EditorScaffold(title: "Enroll your name", onBack: onBack) {
            VStack(alignment: .leading, spacing: 16) {
                Text("Once your name is saved, QuietCue alerts you whenever someone says it. Speech detection itself is switched on or off from Settings.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialCard {
                    VStack(alignment: .leading, spacing: 12) {
                        MaterialTextField(label: "Your name", text: $name, placeholder: "Rohan", limit: 60)
                        MaterialTextField(label: "Nicknames", text: $aliases, placeholder: "Ro, Roh",
                                          supporting: "Optional. Separate entries with commas.", limit: 320)
                    }
                    .padding(16)
                }
                MaterialCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Teach the hub your name").font(MaterialType.titleLarge)
                        Text("Tap Listen, then have someone say your name once, naturally. The Mac's speech model reports how it spelled what it heard, and that spelling is matched from then on. Only the spelling is kept.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        if !spellings.isEmpty {
                            Text("Learned spellings").font(MaterialType.labelLarge)
                            FlowRowM {
                                ForEach(spellings, id: \.self) { spelling in
                                    HStack(spacing: 6) {
                                        Text(spelling).font(MaterialType.labelLarge)
                                        Button {
                                            spellings.removeAll { $0 == spelling }
                                        } label: {
                                            Image(systemName: "xmark").font(.system(size: 12, weight: .semibold))
                                        }
                                        .buttonStyle(.plain)
                                        .accessibilityLabel("Remove spelling \(spelling)")
                                    }
                                    .padding(.horizontal, 12)
                                    .frame(minHeight: 32)
                                    .foregroundStyle(scheme.onSecondaryContainer)
                                    .background(scheme.secondaryContainer)
                                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                }
                            }
                        }
                        FilledButton(label: listening ? "Listening for 4 seconds…" : "Listen for my name", icon: "mic.fill", enabled: canListen) {
                            Task {
                                listening = true
                                error = nil
                                lastResult = nil
                                do {
                                    let result = try await app.learnNameSpelling(
                                        name: trimmedName,
                                        knownSpellings: parseCommaList(aliases, maximum: 10) + spellings
                                    )
                                    let fresh = result.heard.filter { heard in
                                        !spellings.contains { $0.caseInsensitiveCompare(heard) == .orderedSame }
                                    }
                                    let room = max(0, UserIdentity.maxLearnedSpellings - spellings.count)
                                    spellings.append(contentsOf: fresh.prefix(room))
                                    if !fresh.isEmpty {
                                        lastResult = "Heard it as “\(fresh.joined(separator: "”, “"))”. Saved as a spelling to match."
                                    } else if result.recognized {
                                        lastResult = "The hub already recognizes “\(trimmedName)”. Try again from farther away or in a sentence to catch other spellings."
                                    } else {
                                        lastResult = "Nothing new was learned."
                                    }
                                } catch {
                                    self.error = error.localizedDescription
                                }
                                listening = false
                            }
                        }
                        if !app.edge.isRunning {
                            Text("Connect the iPhone microphone to the Mac hub on the Home tab to listen.")
                                .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        }
                        if let lastResult { Text(lastResult).font(MaterialType.bodyLarge).foregroundStyle(scheme.primary) }
                    }
                    .padding(16)
                }
                if let error { Text(error).font(MaterialType.bodyLarge).foregroundStyle(scheme.error) }
                FilledButton(label: "Save name", enabled: !trimmedName.isEmpty && !listening) {
                    onSave(UserIdentity(
                        displayName: trimmedName,
                        pronunciation: initial?.pronunciation ?? "",
                        aliases: parseCommaList(aliases, maximum: 10),
                        recognitionPhrases: spellings
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
                Text("People are added only when you enter them here. Their names help local transcription and trigger alerts only if you turn on “People in my context” in Settings.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                MaterialTextField(label: "Name", text: $name, placeholder: "Maya", limit: 60)
                MaterialTextField(label: "Relationship", text: $relationship, placeholder: "Sister", limit: 80)
                MaterialTextField(label: "Pronunciation (for you, not the detector)", text: $pronunciation, placeholder: "My-uh", limit: 80)
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
