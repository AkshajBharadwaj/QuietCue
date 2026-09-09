import SwiftUI

/// Profiles tab: port of the Android `ProfilesScreen`.
struct ProfilesView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    var onEdit: (AlertProfile) -> Void
    var onGenerateFromText: () -> Void
    var onEnrollSound: () -> Void
    @State private var deleteCandidate: AlertProfile? = nil
    @State private var soundDeleteCandidate: SoundDefinition? = nil

    var body: some View {
        let catalog = model.catalog
        let customSounds = catalog.soundLibrary.filter(\.isCustom)
        let builtIns = catalog.profiles.filter(\.isBuiltIn)
        let customs = catalog.profiles.filter { !$0.isBuiltIn }
        ZStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Profiles").font(MaterialType.headlineMedium).foregroundStyle(scheme.onSurface)
                        Text("Choose what QuietCue listens for and how each alert should feel.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }

                    MaterialCard(container: scheme.secondaryContainer, contentColor: scheme.onSecondaryContainer) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Create for a new situation").font(MaterialType.titleLarge)
                            Text("Describe an unfamiliar place or teach QuietCue a sound unique to you.").font(MaterialType.bodyLarge)
                            FilledButton(label: "Describe a situation", icon: "sparkles", action: onGenerateFromText)
                            OutlinedButtonM(label: "Enroll a sound", icon: "waveform", action: onEnrollSound)
                        }
                        .padding(16)
                    }

                    if !customSounds.isEmpty {
                        SectionTitle("Personal sounds")
                        ForEach(customSounds) { sound in
                            MaterialCard(container: scheme.surfaceContainer) {
                                HStack(spacing: 12) {
                                    Image(systemName: "waveform").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(sound.displayName).font(MaterialType.titleMedium)
                                        Text(sound.enrollment.map { "\($0.positiveSampleCount) examples • experimental local match" } ?? "Classifier-label match")
                                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                                    }
                                    Spacer(minLength: 0)
                                    IconButtonM(systemName: "trash", label: "Delete \(sound.displayName)") { soundDeleteCandidate = sound }
                                }
                                .padding(16)
                            }
                        }
                    }

                    SectionTitle("Built-in")
                    ForEach(builtIns) { profile in
                        ProfileCard(
                            profile: profile,
                            active: profile.id == catalog.activeProfileId,
                            onEdit: { onEdit(profile) },
                            onActivate: { model.activate(profile.id) },
                            onDuplicate: { onEdit(duplicate(profile)) },
                            onDelete: {},
                            onReset: { model.reset(profile.id) }
                        )
                    }

                    if !customs.isEmpty {
                        SectionTitle("Custom")
                        ForEach(customs) { profile in
                            ProfileCard(
                                profile: profile,
                                active: profile.id == catalog.activeProfileId,
                                onEdit: { onEdit(profile) },
                                onActivate: { model.activate(profile.id) },
                                onDuplicate: { onEdit(duplicate(profile)) },
                                onDelete: { deleteCandidate = profile },
                                onReset: {}
                            )
                        }
                    }
                }
                .pagePadding()
                .padding(.top, 12)
                .padding(.bottom, 96)
            }

            if let profile = deleteCandidate {
                MaterialDialog(
                    title: "Delete \(profile.name)?",
                    confirmLabel: "Delete",
                    onConfirm: {
                        model.delete(profile.id)
                        deleteCandidate = nil
                    },
                    onDismiss: { deleteCandidate = nil }
                ) {
                    Text("This custom profile and all of its alert settings will be removed.")
                }
            }
            if let sound = soundDeleteCandidate {
                MaterialDialog(
                    title: "Delete \(sound.displayName)?",
                    confirmLabel: "Delete",
                    onConfirm: {
                        model.deleteEnrolledSound(sound.id)
                        soundDeleteCandidate = nil
                    },
                    onDismiss: { soundDeleteCandidate = nil }
                ) {
                    Text("Its acoustic fingerprint and alert rule will be removed from every profile. This cannot be undone.")
                }
            }
        }
    }

    private func duplicate(_ profile: AlertProfile) -> AlertProfile {
        var copy = ProfileDefaults.duplicate(profile)
        copy.soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary: model.catalog.soundLibrary)
        return copy
    }
}

private struct ProfileCard: View {
    @Environment(\.scheme) private var scheme
    var profile: AlertProfile
    var active: Bool
    var onEdit: () -> Void
    var onActivate: () -> Void
    var onDuplicate: () -> Void
    var onDelete: () -> Void
    var onReset: () -> Void

    var body: some View {
        MaterialCard(container: active ? scheme.primaryContainer : scheme.surfaceContainer,
                     contentColor: active ? scheme.onPrimaryContainer : scheme.onSurface) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    ZStack {
                        Circle().fill(profile.color.color).frame(width: 46, height: 46)
                        Image(systemName: profile.icon.symbolName).font(.system(size: 22)).foregroundStyle(.white)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(profile.name).font(MaterialType.titleMedium)
                            if active {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 19))
                                    .foregroundStyle(scheme.primary)
                                    .accessibilityLabel("Active profile")
                            }
                        }
                        Text("\(profile.enabledSoundCount) of \(profile.soundRules.count) sounds enabled")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer(minLength: 0)
                    Menu {
                        Button(action: onEdit) { Label("Edit", systemImage: "pencil") }
                        Button(action: onDuplicate) { Label("Duplicate", systemImage: "doc.on.doc") }
                        if profile.isBuiltIn {
                            Button(action: onReset) { Label("Restore defaults", systemImage: "arrow.counterclockwise") }
                        } else {
                            Button(role: .destructive, action: onDelete) { Label("Delete", systemImage: "trash") }
                        }
                    } label: {
                        Image(systemName: "ellipsis")
                            .rotationEffect(.degrees(90))
                            .font(.system(size: 22))
                            .frame(width: 48, height: 48)
                            .foregroundStyle(scheme.onSurfaceVariant)
                    }
                    .accessibilityLabel("More options for \(profile.name)")
                }
                Text(profile.descriptionText).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                if active {
                    OutlinedButtonM(label: "Edit active profile", icon: "pencil", action: onEdit)
                } else {
                    FilledButton(label: "Use this profile", action: onActivate)
                }
            }
            .padding(16)
        }
    }
}
