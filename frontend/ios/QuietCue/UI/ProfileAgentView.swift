import SwiftUI

/// Port of the Android `ProfileAgentScreen`.
struct ProfileAgentView: View {
    @Environment(\.scheme) private var scheme
    var activeProfile: AlertProfile
    var soundLibrary: [SoundDefinition]
    var onBack: () -> Void
    var onReview: (AlertProfile) -> Void

    @State private var prompt = ""
    @State private var result: ProfileAgentResult? = nil
    @State private var error: String? = nil
    private let agent = LocalProfileTextAgent()

    var body: some View {
        EditorScaffold(title: "Profile assistant", onBack: onBack) {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Describe the situation").font(MaterialType.headlineSmall).foregroundStyle(scheme.onSurface)
                    Text("QuietCue creates a constrained profile draft from your words. Nothing is saved or activated until you review it.")
                        .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                }
                MaterialTextField(
                    label: "Where are you going and what matters?",
                    text: $prompt,
                    placeholder: "I'm studying in a crowded library. Ignore phones, alert me to fire alarms and my name, Akshaj.",
                    supporting: "\(prompt.count)/500 • processed locally",
                    isError: error != nil,
                    minLines: 6,
                    limit: 500
                )
                .onChange(of: prompt) { _, _ in
                    result = nil
                    error = nil
                }
                if let error { Text(error).font(MaterialType.bodyLarge).foregroundStyle(scheme.error) }
                FilledButton(label: "Create draft", icon: "sparkles", enabled: !prompt.trimmingCharacters(in: .whitespaces).isEmpty) {
                    do {
                        result = try agent.generate(description: prompt, activeProfile: activeProfile, soundLibrary: soundLibrary)
                        error = nil
                    } catch {
                        self.error = error.localizedDescription
                    }
                }
                if let generated = result {
                    MaterialCard {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(generated.profile.name).font(MaterialType.titleLarge)
                            Text(generated.explanation).font(MaterialType.bodyLarge)
                            Text("Assumptions").font(MaterialType.titleSmall)
                            ForEach(generated.assumptions, id: \.self) { Text("• \($0)").font(MaterialType.bodyLarge) }
                            FilledButton(label: "Review every setting") { onReview(generated.profile) }
                        }
                        .padding(16)
                    }
                }
            }
        }
    }
}
