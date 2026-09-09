import SwiftUI

/// Touch-recorded vibration pattern: hold the pad while the motor should buzz,
/// release for a pause. Port of the Android `HapticPatternCreatorDialog`.
struct HapticPatternCreatorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    var existing: CustomHapticPattern?
    var onDismiss: () -> Void
    var onSave: (CustomHapticPattern) -> Void

    @State private var name: String
    @State private var steps: [CustomHapticStep]
    @State private var lastReleaseAt: TimeInterval? = nil
    @State private var pressedAt: TimeInterval? = nil

    init(existing: CustomHapticPattern?, onDismiss: @escaping () -> Void, onSave: @escaping (CustomHapticPattern) -> Void) {
        self.existing = existing
        self.onDismiss = onDismiss
        self.onSave = onSave
        _name = State(initialValue: existing?.name ?? "My pattern")
        _steps = State(initialValue: existing?.steps ?? [])
    }

    private var pattern: CustomHapticPattern {
        CustomHapticPattern(name: name.trimmingCharacters(in: .whitespacesAndNewlines), steps: steps)
    }

    private var pressing: Bool { pressedAt != nil }

    var body: some View {
        MaterialDialog(
            title: "Create a vibration",
            confirmLabel: "Use pattern",
            confirmEnabled: pattern.isValid,
            onConfirm: { onSave(pattern) },
            onDismiss: onDismiss
        ) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Hold the pad while the motor should buzz, then release for a pause. Repeat to record up to \(CustomHapticPattern.maxSteps) pulses.")
                        .font(MaterialType.bodyMedium).foregroundStyle(scheme.onSurfaceVariant)
                    MaterialTextField(label: "Pattern name", text: $name, limit: 30)
                    pad
                    if steps.isEmpty {
                        Text("No pulses recorded yet").font(MaterialType.labelLarge).foregroundStyle(scheme.onSurface)
                    } else {
                        FlowRowM(spacing: 6) {
                            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                                Text("\(index + 1): \(step.onMs) ms")
                                    .font(MaterialType.labelMedium)
                                    .padding(.horizontal, 9).padding(.vertical, 6)
                                    .foregroundStyle(scheme.onSecondaryContainer)
                                    .background(scheme.secondaryContainer)
                                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                            }
                        }
                        let over = pattern.totalDurationMs > CustomHapticPattern.maxTotalMs
                        Text("\(steps.count) pulse\(steps.count == 1 ? "" : "s") • \(Double(pattern.totalDurationMs) / 1_000) seconds")
                            .font(MaterialType.bodySmall).foregroundStyle(over ? scheme.error : scheme.onSurfaceVariant)
                        if over {
                            Text("Keep the full pattern under 10 seconds.").font(MaterialType.labelMedium).foregroundStyle(scheme.error)
                        }
                    }
                    FilledButton(label: "Preview on phone", enabled: pattern.isValid) { model.previewHaptic(pattern) }
                    HStack {
                        Spacer()
                        TextButtonM(label: "Clear and record again", enabled: !steps.isEmpty) {
                            steps = []
                            lastReleaseAt = nil
                            pressedAt = nil
                        }
                        Spacer()
                    }
                }
            }
            .frame(maxHeight: 460)
        }
    }

    private var pad: some View {
        let full = steps.count >= CustomHapticPattern.maxSteps
        return ZStack {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(pressing ? scheme.primary : scheme.primaryContainer)
            Text(pressing ? "BUZZ" : (full ? "6 pulses recorded" : "PRESS + HOLD"))
                .font(MaterialType.titleMedium).fontWeight(.bold)
                .foregroundStyle(pressing ? scheme.onPrimary : scheme.onPrimaryContainer)
        }
        .frame(height: 150)
        .accessibilityLabel("Touch and hold to record a vibration pulse")
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { _ in
                    guard pressedAt == nil, !full else { return }
                    let now = ProcessInfo.processInfo.systemUptime
                    if let released = lastReleaseAt, !steps.isEmpty {
                        let gap = Int((now - released) * 1_000)
                        steps[steps.count - 1].offMs = min(max(gap, CustomHapticStep.minOffMs), CustomHapticStep.maxPhaseMs)
                    }
                    pressedAt = now
                }
                .onEnded { _ in
                    guard let started = pressedAt else { return }
                    let now = ProcessInfo.processInfo.systemUptime
                    pressedAt = nil
                    let onMs = Int((now - started) * 1_000)
                    steps.append(CustomHapticStep(onMs: min(max(onMs, CustomHapticStep.minOnMs), CustomHapticStep.maxPhaseMs), offMs: 200))
                    lastReleaseAt = now
                }
        )
    }
}
