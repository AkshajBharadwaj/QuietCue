import SwiftUI

/// Port of the Android `ProfileEditorScreen`.
struct ProfileEditorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    var initialProfile: AlertProfile
    var soundLibrary: [SoundDefinition]
    var onBack: () -> Void
    var onSave: (AlertProfile) -> Void

    @State private var draft: AlertProfile
    @State private var startTimeText: String
    @State private var endTimeText: String

    init(initialProfile: AlertProfile, soundLibrary: [SoundDefinition], onBack: @escaping () -> Void, onSave: @escaping (AlertProfile) -> Void) {
        self.initialProfile = initialProfile
        self.soundLibrary = soundLibrary
        self.onBack = onBack
        self.onSave = onSave
        _draft = State(initialValue: initialProfile)
        _startTimeText = State(initialValue: formatTime(minutes: initialProfile.quietHours.startMinutes))
        _endTimeText = State(initialValue: formatTime(minutes: initialProfile.quietHours.endMinutes))
    }

    private var parsedStart: Int? { parseTime(startTimeText) }
    private var parsedEnd: Int? { parseTime(endTimeText) }

    private var profileForSave: AlertProfile {
        var profile = draft
        if let start = parsedStart, let end = parsedEnd {
            profile.quietHours.startMinutes = start
            profile.quietHours.endMinutes = end
        }
        return profile
    }

    private var validationErrors: [String] {
        var errors = ProfileValidator.validate(profileForSave, soundLibrary: soundLibrary)
        if draft.quietHours.enabled && parsedStart == nil { errors.append("Use a valid quiet-hours start time, such as 10:00 PM.") }
        if draft.quietHours.enabled && parsedEnd == nil { errors.append("Use a valid quiet-hours end time, such as 7:00 AM.") }
        var seen = Set<String>()
        return errors.filter { seen.insert($0).inserted }
    }

    var body: some View {
        let errors = validationErrors
        VStack(spacing: 0) {
            EditorTopBar(title: draft.isBuiltIn ? "Customize \(draft.name)" : "Edit profile", onBack: onBack) {
                IconButtonM(systemName: "square.and.arrow.down", label: "Save profile", enabled: errors.isEmpty, tint: scheme.onSurface) {
                    onSave(profileForSave)
                }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if draft.isBuiltIn {
                        Text("Built-in profile • Your changes are saved locally and can be restored later.")
                            .font(MaterialType.labelLarge).foregroundStyle(scheme.primary)
                    }

                    EditorSection(title: "Profile details", icon: "slider.horizontal.3") {
                        MaterialTextField(label: "Profile name", text: $draft.name, limit: 40)
                        MaterialTextField(label: "Description", text: $draft.descriptionText,
                                          supporting: "\(draft.descriptionText.count)/120", minLines: 2, limit: 120)
                    }

                    EditorSection(title: "Appearance") {
                        Text("Icon").font(MaterialType.labelLarge)
                        FlowRowM {
                            ForEach(ProfileIcon.allCases, id: \.self) { icon in
                                FilterChipM(selected: draft.icon == icon, label: icon.displayName, action: { draft.icon = icon }) {
                                    Image(systemName: icon.symbolName).font(.system(size: 16))
                                }
                            }
                        }
                        Text("Color").font(MaterialType.labelLarge)
                        FlowRowM {
                            ForEach(ProfileColor.allCases, id: \.self) { color in
                                FilterChipM(selected: draft.color == color, label: color.displayName, action: { draft.color = color }) {
                                    Circle().fill(color.color).frame(width: 16, height: 16)
                                }
                            }
                        }
                    }

                    EditorSection(title: "Automatic activation", icon: "mappin") {
                        SwitchRow(
                            title: "Switch to this profile automatically",
                            description: "The backend will use this rule when context detection is connected.",
                            isOn: $draft.activation.enabled
                        )
                        if draft.activation.enabled {
                            Text("Activity").font(MaterialType.labelLarge)
                            OptionChips(options: ActivityContext.allCases, selected: draft.activation.activity, label: \.displayName) {
                                draft.activation.activity = $0
                            }
                            MaterialTextField(label: "Location label (optional)", text: $draft.activation.locationLabel,
                                              placeholder: "Home, office, campus…", limit: 60)
                        }
                    }

                    EditorSection(title: "Quiet hours", icon: "clock") {
                        SwitchRow(
                            title: "Use quiet hours",
                            description: "Non-emergency alerts are suppressed during this window.",
                            isOn: $draft.quietHours.enabled
                        )
                        if draft.quietHours.enabled {
                            HStack(alignment: .top, spacing: 10) {
                                MaterialTextField(label: "Starts", text: $startTimeText,
                                                  supporting: parsedStart == nil ? "Example: 10:00 PM" : nil,
                                                  isError: parsedStart == nil, limit: 10)
                                MaterialTextField(label: "Ends", text: $endTimeText,
                                                  supporting: parsedEnd == nil ? "Example: 7:00 AM" : nil,
                                                  isError: parsedEnd == nil, limit: 10)
                            }
                            Text("Emergency alerts always break through quiet hours.")
                                .font(MaterialType.labelLarge).foregroundStyle(scheme.primary)
                        }
                    }

                    EditorSection(title: "Name and phrase detection", icon: "person.wave.2") {
                        Text("Speech processing").font(MaterialType.labelLarge)
                        OptionChips(options: SpeechMode.allCases, selected: draft.speechMode, label: \.displayName) {
                            draft.speechMode = $0
                        }
                        MaterialTextField(
                            label: "Trigger phrases",
                            text: Binding(
                                get: { draft.phraseTriggers.joined(separator: ", ") },
                                set: { value in
                                    draft.phraseTriggers = value.split(separator: ",", omittingEmptySubsequences: false)
                                        .map { $0.trimmingCharacters(in: .whitespaces) }
                                        .filter { !$0.isEmpty }
                                }
                            ),
                            placeholder: "Alex, front desk, excuse me",
                            supporting: "Separate phrases with commas. Speech processing stays separate from sound classification.",
                            minLines: 2
                        )
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        SectionTitle("Sounds and alerts")
                        Text("Tune each event independently. Lower thresholds are more sensitive and may create more false alerts.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }

                    ForEach(draft.soundRules) { rule in
                        if let sound = soundLibrary.first(where: { $0.id == rule.soundId }) {
                            SoundRuleCard(
                                rule: Binding(
                                    get: { draft.soundRules.first { $0.soundId == rule.soundId } ?? rule },
                                    set: { updated in
                                        draft.soundRules = draft.soundRules.map { $0.soundId == updated.soundId ? updated : $0 }
                                    }
                                ),
                                sound: sound
                            )
                        }
                    }

                    if !errors.isEmpty {
                        MaterialCard(container: scheme.errorContainer, contentColor: scheme.onErrorContainer) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Before saving").font(MaterialType.titleMedium)
                                ForEach(errors, id: \.self) { Text("• \($0)").font(MaterialType.bodyLarge) }
                            }
                            .padding(16)
                        }
                    }

                    FilledButton(label: "Save profile", icon: "square.and.arrow.down", enabled: errors.isEmpty, height: 52) {
                        onSave(profileForSave)
                    }
                }
                .pagePadding()
                .padding(.top, 8)
                .padding(.bottom, 32)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .background(scheme.background)
    }
}

struct EditorSection<Content: View>: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var icon: String? = nil
    @ViewBuilder var content: () -> Content

    var body: some View {
        MaterialCard(container: scheme.surfaceContainer) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    if let icon { Image(systemName: icon).font(.system(size: 20)) }
                    Text(title).font(MaterialType.titleLarge)
                }
                content()
            }
            .padding(16)
        }
    }
}

struct OptionChips<T: Hashable>: View {
    var options: [T]
    var selected: T
    var label: KeyPath<T, String>
    var enabled: Bool = true
    var onSelected: (T) -> Void

    var body: some View {
        FlowRowM {
            ForEach(options, id: \.self) { option in
                FilterChipM(selected: option == selected, label: option[keyPath: label], enabled: enabled) {
                    onSelected(option)
                }
            }
        }
    }
}

private struct SettingLabel: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var value: String

    var body: some View {
        HStack {
            Text(title).font(MaterialType.labelLarge)
            Spacer()
            Text(value).font(MaterialType.bodyLarge).fontWeight(.bold).foregroundStyle(scheme.primary)
        }
    }
}

private struct SoundRuleCard: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    @Binding var rule: SoundRule
    var sound: SoundDefinition
    @State private var expanded = false
    @State private var showHapticCreator = false

    var body: some View {
        MaterialCard(container: rule.enabled ? scheme.surfaceContainer : scheme.surfaceContainerLow) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .center, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(sound.displayName).font(MaterialType.titleMedium)
                            if sound.safetyCritical {
                                Text("SAFETY").font(MaterialType.labelSmall).fontWeight(.bold).foregroundStyle(scheme.error)
                            }
                        }
                        Text(sound.descriptionText).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer(minLength: 0)
                    SwitchM(isOn: $rule.enabled)
                }
                HStack {
                    Text(rule.enabled ? "\(Int((rule.confidenceThreshold * 100).rounded()))% • \(rule.priority.displayName)" : "Disabled")
                        .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    Spacer()
                    IconButtonM(
                        systemName: expanded ? "chevron.up" : "chevron.down",
                        label: expanded ? "Hide \(sound.displayName) settings" : "Show \(sound.displayName) settings"
                    ) {
                        withAnimation { expanded.toggle() }
                    }
                }
                if expanded {
                    VStack(alignment: .leading, spacing: 12) {
                        Divider().overlay(scheme.outlineVariant)
                        SettingLabel(title: "Confidence threshold", value: "\(Int((rule.confidenceThreshold * 100).rounded()))%")
                        SliderM(
                            value: Binding(
                                get: { rule.confidenceThreshold },
                                set: { rule.confidenceThreshold = min(max(($0 * 20).rounded() / 20, 0.20), 0.95) }
                            ),
                            range: 0.20...0.95, step: 0.05, enabled: rule.enabled
                        )

                        Text("Alert priority").font(MaterialType.labelLarge)
                        OptionChips(options: AlertPriority.allCases, selected: rule.priority, label: \.displayName, enabled: rule.enabled) { priority in
                            rule.priority = priority
                            switch priority {
                            case .informational: rule.hapticPattern = .twoShort
                            case .attention: rule.hapticPattern = .longPulse
                            case .emergency: rule.hapticPattern = .urgentRepeat
                            }
                            rule.requiresAcknowledgement = priority == .emergency
                        }

                        Text("Haptic pattern").font(MaterialType.labelLarge)
                        OptionChips(options: HapticPattern.allCases, selected: rule.hapticPattern, label: \.displayName, enabled: rule.enabled) { pattern in
                            if pattern == .custom { showHapticCreator = true } else { rule.hapticPattern = pattern }
                        }
                        OutlinedButtonM(
                            label: rule.customHapticPattern.map { "Edit \($0.name)" } ?? "Create touch pattern",
                            enabled: rule.enabled
                        ) { showHapticCreator = true }
                        if rule.hapticPattern == .custom, let custom = rule.customHapticPattern {
                            Text("Using \(custom.name): \(custom.steps.count) pulse\(custom.steps.count == 1 ? "" : "s")")
                                .font(MaterialType.labelLarge).foregroundStyle(scheme.primary)
                        }

                        Text("Haptic strength").font(MaterialType.labelLarge)
                        OptionChips(options: HapticStrength.allCases, selected: rule.hapticStrength, label: \.displayName, enabled: rule.enabled) {
                            rule.hapticStrength = $0
                        }

                        SwitchRow(
                            title: "Require acknowledgement",
                            description: "Keep the alert visible until the user confirms it.",
                            isOn: $rule.requiresAcknowledgement
                        )

                        SettingLabel(title: "Repeat cooldown", value: "\(rule.cooldownSeconds) seconds")
                        SliderM(
                            value: Binding(get: { Float(rule.cooldownSeconds) }, set: { rule.cooldownSeconds = Int($0.rounded()) }),
                            range: 0...120, step: 5, enabled: rule.enabled
                        )
                    }
                    .opacity(rule.enabled ? 1 : 0.55)
                }
            }
            .padding(16)
        }
        .overlay {
            if showHapticCreator {
                HapticPatternCreatorView(
                    existing: rule.customHapticPattern,
                    onDismiss: { showHapticCreator = false },
                    onSave: { pattern in
                        rule.hapticPattern = .custom
                        rule.customHapticPattern = pattern
                        showHapticCreator = false
                    }
                )
            }
        }
    }
}
