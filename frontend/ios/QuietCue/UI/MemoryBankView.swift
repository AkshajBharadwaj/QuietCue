import SwiftUI

/// My context tab: port of the Android `MemoryBankScreen`.
struct MemoryBankView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    var onEditSpeech: () -> Void
    var onEditIdentity: () -> Void
    var onEditPerson: (PersonMemory?) -> Void
    var onEditContext: (ContextMemory?) -> Void

    @State private var deletePerson: PersonMemory? = nil
    @State private var deleteContext: ContextMemory? = nil
    @State private var confirmIdentityDelete = false
    @State private var confirmClear = false

    var body: some View {
        let bank = model.memoryBank
        ZStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("My context").font(MaterialType.headlineMedium).foregroundStyle(scheme.onSurface)
                        Text("Teach QuietCue the names and details you choose so local speech recognition has the right context.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    MaterialCard(container: scheme.secondaryContainer, contentColor: scheme.onSecondaryContainer) {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: "lock.fill").font(.system(size: 22))
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Private and user-controlled").font(MaterialType.titleMedium)
                                Text("This bank is encrypted on your phone. QuietCue never creates memories from background conversations, and enrollment audio is not saved.")
                                    .font(MaterialType.bodyLarge)
                            }
                        }
                        .padding(16)
                    }

                    SectionTitle("Speech and names")
                    MaterialCard(container: scheme.surfaceContainer) {
                        HStack(spacing: 12) {
                            Image(systemName: "person.wave.2").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(bank.speechSettings.enabled ? "Local speech detection on" : "Local speech detection off")
                                    .font(MaterialType.titleMedium)
                                Text("\(bank.speechSettings.model.displayName) • \(Int(bank.speechSettings.sensitivity * 100))% sensitivity • \(bank.speechSettings.globalPhrases.count) global phrases")
                                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                            }
                            Spacer(minLength: 0)
                            IconButtonM(systemName: "pencil", label: "Edit speech settings", action: onEditSpeech)
                        }
                        .padding(16)
                    }

                    SectionTitle("Your name")
                    MaterialCard(container: scheme.surfaceContainer) {
                        HStack(spacing: 12) {
                            Image(systemName: "person.text.rectangle").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(bank.identity?.displayName ?? "No name enrolled").font(MaterialType.titleMedium)
                                Text(identitySubtitle(bank.identity)).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                            }
                            Spacer(minLength: 0)
                            IconButtonM(systemName: "pencil", label: "Edit your name", action: onEditIdentity)
                            if bank.identity != nil {
                                IconButtonM(systemName: "trash", label: "Delete name enrollment") { confirmIdentityDelete = true }
                            }
                        }
                        .padding(16)
                    }

                    SectionTitle("People")
                    if bank.people.isEmpty {
                        EmptyMemoryCard(title: "No people added", detail: "Add family, friends, coworkers, or other important names.")
                    } else {
                        ForEach(bank.people) { person in
                            let subtitle = [person.relationship, person.pronunciation].filter { !$0.isEmpty }.joined(separator: " • ")
                            MemoryItemCard(
                                icon: "person.2.fill",
                                title: person.name,
                                subtitle: subtitle.isEmpty ? "Known person" : subtitle,
                                onEdit: { onEditPerson(person) },
                                onDelete: { deletePerson = person }
                            )
                        }
                    }
                    OutlinedButtonM(label: "Add a person", icon: "plus") { onEditPerson(nil) }

                    SectionTitle("Manual context")
                    if bank.contexts.isEmpty {
                        EmptyMemoryCard(title: "No context added", detail: "Add places, routines, projects, or other details you want QuietCue to know.")
                    } else {
                        ForEach(bank.contexts) { context in
                            MemoryItemCard(
                                icon: "book",
                                title: context.title,
                                subtitle: context.details,
                                onEdit: { onEditContext(context) },
                                onDelete: { deleteContext = context }
                            )
                        }
                    }
                    OutlinedButtonM(label: "Add context", icon: "plus") { onEditContext(nil) }

                    if !bank.isEmpty {
                        SectionTitle("Privacy controls")
                        FilledButton(label: "Delete entire memory bank", icon: "trash.fill") { confirmClear = true }
                    }
                }
                .pagePadding()
                .padding(.top, 12)
                .padding(.bottom, 28)
            }

            if let person = deletePerson {
                DeleteMemoryDialog(title: "Delete \(person.name)?", detail: "This person will be removed from transcription context.",
                                   onDismiss: { deletePerson = nil }) {
                    model.deletePerson(person.id)
                    deletePerson = nil
                }
            }
            if let context = deleteContext {
                DeleteMemoryDialog(title: "Delete \(context.title)?", detail: "This manual context entry will be permanently removed.",
                                   onDismiss: { deleteContext = nil }) {
                    model.deleteContext(context.id)
                    deleteContext = nil
                }
            }
            if confirmIdentityDelete {
                DeleteMemoryDialog(title: "Delete name enrollment?",
                                   detail: "Your name, pronunciation, aliases, and voice-check text will be removed from name detection.",
                                   onDismiss: { confirmIdentityDelete = false }) {
                    model.deleteIdentity()
                    confirmIdentityDelete = false
                }
            }
            if confirmClear {
                DeleteMemoryDialog(title: "Delete the entire memory bank?",
                                   detail: "Your speech settings, name enrollment, people, and manual context will be permanently removed. Profiles and enrolled sounds are not affected.",
                                   onDismiss: { confirmClear = false }) {
                    model.clearMemoryBank()
                    confirmClear = false
                }
            }
        }
    }

    private func identitySubtitle(_ identity: UserIdentity?) -> String {
        guard let identity else { return "Add your name, pronunciation, aliases, and optional voice checks." }
        if !identity.pronunciation.isEmpty { return "Pronounced \(identity.pronunciation)" }
        return "\(identity.aliases.count) aliases • \(identity.recognitionPhrases.count) voice checks"
    }
}

private struct MemoryItemCard: View {
    @Environment(\.scheme) private var scheme
    var icon: String
    var title: String
    var subtitle: String
    var onEdit: () -> Void
    var onDelete: () -> Void

    var body: some View {
        MaterialCard(container: scheme.surfaceContainer) {
            HStack(spacing: 12) {
                Image(systemName: icon).font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(MaterialType.titleMedium)
                    Text(subtitle).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant).lineLimit(3)
                }
                Spacer(minLength: 0)
                IconButtonM(systemName: "pencil", label: "Edit \(title)", action: onEdit)
                IconButtonM(systemName: "trash", label: "Delete \(title)", action: onDelete)
            }
            .padding(16)
        }
    }
}

private struct EmptyMemoryCard: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var detail: String

    var body: some View {
        MaterialCard(container: scheme.surfaceContainerLow) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(MaterialType.titleMedium)
                Text(detail).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
            }
            .padding(16)
        }
    }
}

private struct DeleteMemoryDialog: View {
    var title: String
    var detail: String
    var onDismiss: () -> Void
    var onConfirm: () -> Void

    var body: some View {
        MaterialDialog(title: title, confirmLabel: "Delete", onConfirm: onConfirm, onDismiss: onDismiss) {
            Text(detail)
        }
    }
}
