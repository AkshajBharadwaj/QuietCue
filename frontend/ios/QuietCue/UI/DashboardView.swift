import SwiftUI

/// Home tab: port of the Android `DashboardScreen`, plus the hub address card
/// the iPhone needs because it cannot reach the Mac over localhost.
struct DashboardView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    @State private var hostDraft = ""
    @State private var tokenDraft = ""
    @State private var showToken = false

    var body: some View {
        let catalog = model.catalog
        let runtime = model.runtimeState
        let edge = model.edge.state
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Good to see you").font(MaterialType.headlineMedium).foregroundStyle(scheme.onSurface)
                    Text("QuietCue is ready to show the alerts that matter.")
                        .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                }

                if let profile = catalog.activeProfile {
                    MaterialCard(container: profile.color.color, contentColor: .white) {
                        HStack(spacing: 16) {
                            ZStack {
                                Circle().fill(Color.white.opacity(0.18)).frame(width: 52, height: 52)
                                Image(systemName: profile.icon.symbolName).font(.system(size: 24))
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Active profile").font(MaterialType.labelLarge)
                                Text(profile.name).font(MaterialType.headlineSmall)
                                Text("\(profile.enabledSoundCount) sounds monitored").font(MaterialType.bodyLarge)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(20)
                    }
                }

                if let suggestion = model.smartProfileState.suggestion {
                    MaterialCard(container: scheme.tertiaryContainer, contentColor: scheme.onTertiaryContainer) {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(alignment: .center, spacing: 10) {
                                Image(systemName: "mappin").font(.system(size: 22))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(suggestion.transition == .enter ? "You arrived at \(suggestion.placeName)" : "You left \(suggestion.placeName)")
                                        .font(MaterialType.titleMedium)
                                    Text("Switch to \(suggestion.targetProfileName)?" + (suggestion.simulated ? " • demo event" : ""))
                                        .font(MaterialType.bodyLarge)
                                }
                            }
                            FilledButton(label: "Switch to \(suggestion.targetProfileName)") {
                                model.acceptSmartProfileSuggestion(always: false)
                            }
                            if suggestion.transition == .enter {
                                OutlinedButtonM(label: "Always switch here") { model.acceptSmartProfileSuggestion(always: true) }
                            }
                            TextButtonM(label: "Not now", fullWidth: true) { model.dismissSmartProfileSuggestion() }
                        }
                        .padding(16)
                    }
                }

                SectionTitle("System status")
                VStack(spacing: 10) {
                    hubAddressCard
                    StatusRow(icon: "ear.fill", title: "Phone app", status: "Profile controls available", connected: true)
                    inferenceDeviceCard(runtime)
                    StatusRow(
                        icon: "icloud.slash",
                        title: "Inference hub",
                        status: runtime.backendConnected
                            ? "Connected • \(runtime.backendProfileName ?? "Profile unavailable")"
                            : (model.hubSettings.host.isEmpty ? "Enter the Mac's address above" : "Run the local QuietCue hub"),
                        connected: runtime.backendConnected
                    )
                    StatusRow(
                        icon: "waveform",
                        title: "Speech and name detection",
                        status: speechStatus,
                        connected: model.hubSpeech.inferenceMs != nil && model.hubSpeech.error == nil
                    )
                    StatusRow(
                        icon: "applewatch",
                        title: "Audio source",
                        status: audioSourceStatus(edge, runtime),
                        connected: edge.isStreaming
                    )
                }

                SectionTitle("Latest alert")
                latestAlertCard(runtime)
            }
            .pagePadding()
            .padding(.top, 12)
            .padding(.bottom, 24)
        }
        .onAppear {
            hostDraft = model.hubSettings.host
            tokenDraft = model.hubSettings.pairingToken
        }
    }

    // MARK: Hub address

    private var hubAddressCard: some View {
        let edge = model.edge.state
        return MaterialCard(container: scheme.surfaceContainer) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: "desktopcomputer").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Mac hub").font(MaterialType.titleSmall).foregroundStyle(scheme.onSurface)
                        Text(edgePhaseText(edge)).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer(minLength: 0)
                    Circle().fill(edge.isStreaming ? scheme.primary : scheme.outline).frame(width: 12, height: 12)
                }
                MaterialTextField(label: "Mac address on this Wi-Fi", text: $hostDraft, placeholder: "192.168.1.20")
                    .keyboardType(.asciiCapable)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                if showToken {
                    MaterialTextField(label: "Pairing token (optional)", text: $tokenDraft, placeholder: "QUIETCUE_PAIRING_TOKEN")
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                HStack(spacing: 8) {
                    FilledButton(label: model.edge.isRunning && hostDraft == model.hubSettings.host ? "Reconnect" : "Connect") {
                        model.connect(host: hostDraft, pairingToken: tokenDraft)
                    }
                    OutlinedButtonM(label: showToken ? "Hide token" : "Token", fullWidth: false) { showToken.toggle() }
                }
            }
            .padding(16)
        }
    }

    private func edgePhaseText(_ edge: EdgeStreamState) -> String {
        switch edge.phase {
        case .idle: return "Enter the Mac's address to start streaming"
        case .connecting: return "Connecting to \(model.hubSettings.host)…"
        case .streaming:
            var parts = ["Streaming \(edge.chunksSent) chunks"]
            if let rtt = edge.lastRoundTripMs { parts.append("\(rtt) ms round trip") }
            if let rms = edge.lastRmsDbfs { parts.append("\(Int(rms)) dBFS") }
            return parts.joined(separator: " • ")
        case .retrying(let seconds): return "Hub unreachable; retrying in \(seconds)s"
        case .failed(let reason): return reason
        }
    }

    private var speechStatus: String {
        let speech = model.hubSpeech
        if let error = speech.error { return error }
        if speech.pending { return "Transcribing locally…" }
        if let ms = speech.inferenceMs { return "Model ready • last decode \(Int(ms)) ms" }
        return "Loads only when an enabled profile hears speech"
    }

    private func audioSourceStatus(_ edge: EdgeStreamState, _ runtime: RuntimeState) -> String {
        if edge.isStreaming { return "iPhone microphone streaming to the hub" }
        if runtime.audioSourceConnected { return "WAV replay or Uno Q stream connected" }
        return "Waiting for the iPhone microphone stream"
    }

    // MARK: Inference device

    private func inferenceDeviceCard(_ runtime: RuntimeState) -> some View {
        let requested = runtime.requestedInferenceDevice
        let active = runtime.activeInferenceDevice
        let status: String
        if let error = runtime.inferenceRoutingError {
            status = error
        } else if runtime.inferenceSwitchPending {
            status = "Switching to \(requested.displayName) • \(active.displayName) is handling audio"
        } else if active == .phone {
            status = "iPhone • on-device inference"
        } else {
            status = "PC • local ONNX inference"
        }
        return MaterialCard(container: scheme.surfaceContainer) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: "waveform").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Inference device").font(MaterialType.titleSmall).foregroundStyle(scheme.onSurface)
                        Text(status).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer(minLength: 0)
                    Circle().fill(runtime.backendConnected ? scheme.primary : scheme.outline).frame(width: 12, height: 12)
                }
                HStack(spacing: 8) {
                    if requested == .copilotPC {
                        FilledButton(label: "PC", enabled: runtime.backendConnected) {}
                    } else {
                        OutlinedButtonM(label: "PC", enabled: runtime.backendConnected) { model.setInferenceDevice(.copilotPC) }
                    }
                    if requested == .phone {
                        FilledButton(label: "iPhone", enabled: runtime.backendConnected) {}
                    } else {
                        OutlinedButtonM(label: "iPhone", enabled: false) {}
                    }
                }
                Text("On-device inference is not part of the iPhone demo; the Mac classifies every chunk.")
                    .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
            }
            .padding(16)
        }
    }

    // MARK: Latest alert

    private func latestAlertCard(_ runtime: RuntimeState) -> some View {
        MaterialCard {
            HStack(alignment: .center, spacing: 16) {
                let alert = runtime.latestAlert
                Image(systemName: alert == nil ? "bell" : "bell.and.waves.left.and.right.fill")
                    .font(.system(size: 28))
                    .frame(width: 32, height: 32)
                    .foregroundStyle(alert == nil ? scheme.onSurfaceVariant : scheme.primary)
                VStack(alignment: .leading, spacing: 3) {
                    if let alert {
                        Text(alert.displayName).font(MaterialType.titleMedium).foregroundStyle(scheme.onSurface)
                        Text("\(Int(alert.confidence * 100))% • \(alert.category.capitalized) • \(alert.profileName)")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        Text(deliveryLine(alert))
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                        if alert.hapticActive {
                            Spacer().frame(height: 8)
                            FilledButton(
                                label: runtime.stopInProgress
                                    ? "Stopping…"
                                    : (alert.requiresAcknowledgement ? "Acknowledge & stop vibration" : "Stop vibration"),
                                enabled: !runtime.stopInProgress && runtime.backendConnected,
                                fullWidth: false
                            ) {
                                model.stopHaptic(eventId: alert.eventId)
                            }
                        } else if alert.acknowledgedAtMs != nil {
                            Text("Vibration stopped").font(MaterialType.bodyLarge).foregroundStyle(scheme.primary)
                        }
                    } else {
                        Text("No alerts yet").font(MaterialType.titleMedium).foregroundStyle(scheme.onSurface)
                        Text("Make a sound near the iPhone to show confidence, latency, and haptic output here.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(20)
        }
    }

    private func deliveryLine(_ alert: DetectedAlert) -> String {
        var line = "\(alert.totalLatencyMs) ms • \(alert.pattern.replacingOccurrences(of: "_", with: " "))"
        if alert.fallbackToPhone {
            line += " • check phone for details"
        } else if alert.simulated {
            line += " • awaiting haptic delivery"
        } else {
            line += " • delivered to iPhone"
        }
        return line
    }
}

struct StatusRow: View {
    @Environment(\.scheme) private var scheme
    var icon: String
    var title: String
    var status: String
    var connected: Bool

    var body: some View {
        MaterialCard(container: scheme.surfaceContainer) {
            HStack(spacing: 12) {
                Image(systemName: icon).font(.system(size: 22)).frame(width: 28).foregroundStyle(scheme.onSurfaceVariant)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(MaterialType.titleSmall).foregroundStyle(scheme.onSurface)
                    Text(status).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                }
                Spacer(minLength: 0)
                Circle().fill(connected ? scheme.primary : scheme.outline).frame(width: 12, height: 12)
            }
            .padding(16)
        }
    }
}
