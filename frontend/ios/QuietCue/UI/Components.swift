import SwiftUI

// Material 3 components rebuilt in SwiftUI so the iPhone app matches the
// Android app's layout: cards, filled/outlined/text buttons, filter chips,
// outlined text fields, switches, and the section headers.

private struct CardContainerKey: EnvironmentKey {
    static let defaultValue: Color? = nil
}

extension EnvironmentValues {
    /// Background color of the enclosing card, so floating field labels can
    /// mask the outline with the right color.
    var cardContainer: Color? {
        get { self[CardContainerKey.self] }
        set { self[CardContainerKey.self] = newValue }
    }
}

struct MaterialCard<Content: View>: View {
    @Environment(\.scheme) private var scheme
    var container: Color? = nil
    var contentColor: Color? = nil
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .environment(\.cardContainer, container ?? scheme.surfaceContainerHigh)
            .foregroundStyle(contentColor ?? scheme.onSurface)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(container ?? scheme.surfaceContainerHigh)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

struct SectionTitle: View {
    @Environment(\.scheme) private var scheme
    var text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(MaterialType.titleLarge).foregroundStyle(scheme.onSurface)
    }
}

struct FilledButton: View {
    @Environment(\.scheme) private var scheme
    var label: String
    var icon: String? = nil
    var enabled: Bool = true
    var fullWidth: Bool = true
    var height: CGFloat = 40
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let icon { Image(systemName: icon).font(.system(size: 18)) }
                Text(label).font(MaterialType.labelLarge)
            }
            .padding(.horizontal, 24)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: height)
            .foregroundStyle(enabled ? scheme.onPrimary : scheme.onSurface.opacity(0.38))
            .background(enabled ? scheme.primary : scheme.onSurface.opacity(0.12))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

struct OutlinedButtonM: View {
    @Environment(\.scheme) private var scheme
    var label: String
    var icon: String? = nil
    var enabled: Bool = true
    var fullWidth: Bool = true
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let icon { Image(systemName: icon).font(.system(size: 18)) }
                Text(label).font(MaterialType.labelLarge)
            }
            .padding(.horizontal, 24)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: 40)
            .foregroundStyle(enabled ? scheme.primary : scheme.onSurface.opacity(0.38))
            .overlay(Capsule().stroke(enabled ? scheme.outline : scheme.onSurface.opacity(0.12), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

struct TextButtonM: View {
    @Environment(\.scheme) private var scheme
    var label: String
    var enabled: Bool = true
    var fullWidth: Bool = false
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(MaterialType.labelLarge)
                .padding(.horizontal, 12)
                .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: 40)
                .foregroundStyle(enabled ? scheme.primary : scheme.onSurface.opacity(0.38))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

struct IconButtonM: View {
    @Environment(\.scheme) private var scheme
    var systemName: String
    var label: String
    var enabled: Bool = true
    var tint: Color? = nil
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 22))
                .frame(width: 48, height: 48)
                .foregroundStyle(enabled ? (tint ?? scheme.onSurfaceVariant) : scheme.onSurface.opacity(0.38))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .accessibilityLabel(label)
    }
}

struct FilterChipM<Leading: View>: View {
    @Environment(\.scheme) private var scheme
    var selected: Bool
    var label: String
    var enabled: Bool = true
    var action: () -> Void
    @ViewBuilder var leading: () -> Leading

    init(selected: Bool, label: String, enabled: Bool = true, action: @escaping () -> Void, @ViewBuilder leading: @escaping () -> Leading) {
        self.selected = selected
        self.label = label
        self.enabled = enabled
        self.action = action
        self.leading = leading
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if selected {
                    Image(systemName: "checkmark").font(.system(size: 14, weight: .semibold))
                } else {
                    leading()
                }
                Text(label).font(MaterialType.labelLarge)
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 32)
            .foregroundStyle(enabled ? (selected ? scheme.onSecondaryContainer : scheme.onSurfaceVariant) : scheme.onSurface.opacity(0.38))
            .background(selected ? scheme.secondaryContainer : Color.clear)
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(selected ? Color.clear : (enabled ? scheme.outline : scheme.onSurface.opacity(0.12)), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

extension FilterChipM where Leading == EmptyView {
    init(selected: Bool, label: String, enabled: Bool = true, action: @escaping () -> Void) {
        self.init(selected: selected, label: label, enabled: enabled, action: action) { EmptyView() }
    }
}

/// Wraps chips onto multiple lines like Compose's `FlowRow`.
struct FlowRowM: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width == .infinity ? x : width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

struct SwitchM: View {
    @Environment(\.scheme) private var scheme
    @Binding var isOn: Bool
    var enabled: Bool = true

    var body: some View {
        Toggle("", isOn: $isOn)
            .labelsHidden()
            .tint(scheme.primary)
            .disabled(!enabled)
    }
}

struct SwitchRow: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var description: String
    @Binding var isOn: Bool
    var enabled: Bool = true

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(MaterialType.titleMedium).foregroundStyle(scheme.onSurface)
                Text(description).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
            }
            Spacer(minLength: 0)
            SwitchM(isOn: $isOn, enabled: enabled)
        }
    }
}

struct SliderM: View {
    @Environment(\.scheme) private var scheme
    @Binding var value: Float
    var range: ClosedRange<Float>
    var step: Float
    var enabled: Bool = true

    var body: some View {
        Slider(value: $value, in: range, step: step)
            .tint(scheme.primary)
            .disabled(!enabled)
    }
}

/// Material outlined text field with a floating label.
struct MaterialTextField: View {
    @Environment(\.scheme) private var scheme
    @Environment(\.cardContainer) private var cardContainer
    var label: String
    @Binding var text: String
    var placeholder: String = ""
    var supporting: String? = nil
    var isError: Bool = false
    var minLines: Int = 1
    var limit: Int? = nil
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(borderColor, lineWidth: focused ? 2 : 1)
                Group {
                    if minLines > 1 {
                        TextField(placeholder, text: $text, axis: .vertical)
                            .lineLimit(minLines...max(minLines, 12))
                    } else {
                        TextField(placeholder, text: $text)
                    }
                }
                .font(MaterialType.bodyLarge)
                .foregroundStyle(scheme.onSurface)
                .focused($focused)
                .padding(.horizontal, 16)
                .padding(.vertical, 16)
                .onChange(of: text) { _, newValue in
                    if let limit, newValue.count > limit { text = String(newValue.prefix(limit)) }
                }
                Text(label)
                    .font(MaterialType.bodySmall)
                    .foregroundStyle(labelColor)
                    .padding(.horizontal, 4)
                    .background(cardContainer ?? scheme.background)
                    .offset(x: 12, y: -8)
            }
            .contentShape(Rectangle())
            .onTapGesture { focused = true }
            if let supporting {
                Text(supporting)
                    .font(MaterialType.bodySmall)
                    .foregroundStyle(isError ? scheme.error : scheme.onSurfaceVariant)
                    .padding(.horizontal, 16)
            }
        }
    }

    private var borderColor: Color {
        if isError { return scheme.error }
        return focused ? scheme.primary : scheme.outline
    }

    private var labelColor: Color {
        if isError { return scheme.error }
        return focused ? scheme.primary : scheme.onSurfaceVariant
    }
}

/// Material "AlertDialog" presented as a centered card over a scrim.
struct MaterialDialog<Content: View>: View {
    @Environment(\.scheme) private var scheme
    var icon: String? = nil
    var title: String
    var confirmLabel: String
    var confirmEnabled: Bool = true
    var dismissLabel: String = "Cancel"
    var onConfirm: () -> Void
    var onDismiss: () -> Void
    @ViewBuilder var content: () -> Content

    var body: some View {
        ZStack {
            Color.black.opacity(0.32).ignoresSafeArea().onTapGesture(perform: onDismiss)
            VStack(alignment: icon == nil ? .leading : .center, spacing: 16) {
                if let icon {
                    Image(systemName: icon).font(.system(size: 24)).foregroundStyle(scheme.secondary)
                }
                Text(title).font(MaterialType.headlineSmall).foregroundStyle(scheme.onSurface)
                    .multilineTextAlignment(icon == nil ? .leading : .center)
                content()
                    .font(MaterialType.bodyMedium)
                    .foregroundStyle(scheme.onSurfaceVariant)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 8) {
                    Spacer()
                    TextButtonM(label: dismissLabel, action: onDismiss)
                    TextButtonM(label: confirmLabel, enabled: confirmEnabled, action: onConfirm)
                }
            }
            .padding(24)
            .frame(maxWidth: 320)
            .background(scheme.surfaceContainerHigh)
            .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
            .padding(24)
        }
    }
}

/// Material snackbar.
struct SnackbarM: View {
    @Environment(\.scheme) private var scheme
    var text: String

    var body: some View {
        Text(text)
            .font(MaterialType.bodyMedium)
            .foregroundStyle(scheme.inverseOnSurface)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(scheme.inverseSurface)
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .padding(.horizontal, 12)
            .shadow(color: .black.opacity(0.2), radius: 6, y: 3)
    }
}

/// Material top app bar for sub-screens with a back arrow.
struct EditorTopBar<Trailing: View>: View {
    @Environment(\.scheme) private var scheme
    var title: String
    var onBack: () -> Void
    @ViewBuilder var trailing: () -> Trailing

    init(title: String, onBack: @escaping () -> Void, @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }) {
        self.title = title
        self.onBack = onBack
        self.trailing = trailing
    }

    var body: some View {
        HStack(spacing: 4) {
            IconButtonM(systemName: "arrow.backward", label: "Go back", tint: scheme.onSurface, action: onBack)
            Text(title).font(MaterialType.titleLarge).foregroundStyle(scheme.onSurface).lineLimit(1)
            Spacer()
            trailing()
        }
        .padding(.horizontal, 4)
        .frame(height: 64)
        .background(scheme.surface)
    }
}

extension View {
    /// Consistent horizontal page padding used by every screen (20dp on Android).
    func pagePadding() -> some View { padding(.horizontal, 20) }
}
