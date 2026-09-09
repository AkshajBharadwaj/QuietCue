import SwiftUI

/// Places tab: port of the Android `SmartPlacesScreen`.
struct SmartPlacesView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scheme) private var scheme
    @Environment(\.scenePhase) private var scenePhase
    @State private var showAddDialog = false
    @State private var showBackgroundEducation = false

    var body: some View {
        let state = model.smartProfileState
        let permission = model.locationPermission
        ZStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Smart places").font(MaterialType.headlineMedium).foregroundStyle(scheme.onSurface)
                        Text("QuietCue can suggest a profile when you arrive and switch back when you leave. Saved coordinates stay on this phone.")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }

                    monitoringCard(
                        status: model.geofenceStatus,
                        hasPrecise: permission.hasPrecise,
                        hasBackground: permission.hasBackground,
                        hasRealPlaces: state.places.contains { !$0.demoOnly }
                    )

                    let now = nowEpochMs()
                    if state.manualOverrideActive(nowEpochMs: now) {
                        let minutes = max(1, (state.manualOverrideUntilEpochMs - now) / 60_000)
                        MaterialCard(container: scheme.tertiaryContainer, contentColor: scheme.onTertiaryContainer) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Manual choice protected").font(MaterialType.titleMedium)
                                Text("Automatic changes are paused for about \(minutes) minutes. QuietCue can still show suggestions.")
                                    .font(MaterialType.bodyLarge)
                            }
                            .padding(16)
                        }
                    }

                    FilledButton(label: "Save my current place", icon: "mappin.and.ellipse") { showAddDialog = true }
                    if !state.places.contains(where: \.demoOnly) {
                        OutlinedButtonM(label: "Create hackathon demo place", icon: "play.fill") { model.addDemoSmartPlace() }
                    }

                    if !state.places.isEmpty {
                        SectionTitle("Saved places")
                        ForEach(state.places) { place in
                            SmartPlaceCard(
                                place: place,
                                profile: model.catalog.profiles.first { $0.id == place.profileId },
                                onDelete: { model.deleteSmartPlace(place.id) },
                                onSetAutoApply: { model.setSmartPlaceAutoApply(place.id, enabled: $0) },
                                onSimulateArrival: { model.simulateSmartPlace(place.id, transition: .enter) },
                                onSimulateDeparture: { model.simulateSmartPlace(place.id, transition: .exit) }
                            )
                        }
                    }
                }
                .pagePadding()
                .padding(.top, 12)
                .padding(.bottom, 24)
            }

            if showAddDialog {
                AddPlaceDialog(
                    profiles: model.catalog.profiles,
                    defaultProfileId: model.catalog.activeProfileId,
                    onDismiss: { showAddDialog = false },
                    onConfirm: { name, profileId, radius in
                        showAddDialog = false
                        if permission.hasPrecise {
                            model.addCurrentSmartPlace(name: name, profileId: profileId, radiusMeters: radius)
                        } else {
                            model.requestLocationPermission()
                            model.message = "Allow location access, then save the place again"
                        }
                    }
                )
            }

            if showBackgroundEducation {
                MaterialDialog(
                    icon: "mappin",
                    title: "Allow background suggestions",
                    confirmLabel: "Continue",
                    dismissLabel: "Not now",
                    onConfirm: {
                        showBackgroundEducation = false
                        if permission == .denied {
                            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                        } else {
                            model.requestLocationPermission()
                        }
                    },
                    onDismiss: { showBackgroundEducation = false }
                ) {
                    Text("Choose precise location and Always so iOS can notify QuietCue when you cross a saved place boundary. Location remains local and the feature still works in ask-before-switching mode.")
                }
            }
        }
        .onAppear { model.refreshSmartPlaces(showMessage: false) }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { model.refreshSmartPlaces(showMessage: false) }
        }
    }

    private func monitoringCard(status: GeofenceRegistrationStatus, hasPrecise: Bool, hasBackground: Bool, hasRealPlaces: Bool) -> some View {
        let active = status == .active
        let detail: String
        if !hasPrecise {
            detail = "Precise location is needed to define reliable boundaries."
        } else if !hasBackground {
            detail = "Allow all-time access for arrival and departure events."
        } else if !hasRealPlaces {
            detail = "Permission is ready. Save a real place to begin."
        } else if status == .registrationFailed {
            detail = "iOS could not register the saved boundaries. Check location settings and try again."
        } else {
            detail = "Low-power geofences are registered on this phone."
        }
        return MaterialCard(container: active ? scheme.primaryContainer : scheme.surfaceContainer,
                            contentColor: active ? scheme.onPrimaryContainer : scheme.onSurface) {
            HStack(spacing: 12) {
                Image(systemName: active ? "mappin" : "location.slash").font(.system(size: 22))
                VStack(alignment: .leading, spacing: 3) {
                    Text(active ? "Background suggestions active" : "Background suggestions need setup").font(MaterialType.titleMedium)
                    Text(detail).font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                }
                Spacer(minLength: 0)
                if !active && (!hasPrecise || !hasBackground) {
                    TextButtonM(label: "Enable") { showBackgroundEducation = true }
                }
            }
            .padding(16)
        }
    }
}

private struct SmartPlaceCard: View {
    @Environment(\.scheme) private var scheme
    var place: SmartPlace
    var profile: AlertProfile?
    var onDelete: () -> Void
    var onSetAutoApply: (Bool) -> Void
    var onSimulateArrival: () -> Void
    var onSimulateDeparture: () -> Void

    var body: some View {
        MaterialCard(container: scheme.surfaceContainer) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "mappin").font(.system(size: 22)).foregroundStyle(scheme.onSurfaceVariant)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(place.name).font(MaterialType.titleMedium)
                        Text(place.demoOnly ? "Demo only • no GPS monitoring" : "\(Int(place.radiusMeters)) m boundary • coordinates stored locally")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer(minLength: 0)
                    IconButtonM(systemName: "trash", label: "Delete \(place.name)", action: onDelete)
                }
                Text("Profile: \(profile?.name ?? "Unavailable profile")").font(MaterialType.bodyLarge)
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Switch automatically").font(MaterialType.labelLarge)
                        Text(place.autoApply ? "After an explicit Always here choice" : "Ask before changing")
                            .font(MaterialType.bodyLarge).foregroundStyle(scheme.onSurfaceVariant)
                    }
                    Spacer()
                    SwitchM(isOn: Binding(get: { place.autoApply }, set: onSetAutoApply))
                }
                HStack(spacing: 8) {
                    OutlinedButtonM(label: "Test arrival", action: onSimulateArrival)
                    OutlinedButtonM(label: "Test departure", action: onSimulateDeparture)
                }
            }
            .padding(16)
        }
    }
}

private struct AddPlaceDialog: View {
    @Environment(\.scheme) private var scheme
    var profiles: [AlertProfile]
    var defaultProfileId: String
    var onDismiss: () -> Void
    var onConfirm: (String, String, Float) -> Void
    @State private var name = ""
    @State private var profileId: String
    @State private var radius: Float = 150

    init(profiles: [AlertProfile], defaultProfileId: String, onDismiss: @escaping () -> Void, onConfirm: @escaping (String, String, Float) -> Void) {
        self.profiles = profiles
        self.defaultProfileId = defaultProfileId
        self.onDismiss = onDismiss
        self.onConfirm = onConfirm
        _profileId = State(initialValue: defaultProfileId)
    }

    private var profile: AlertProfile? { profiles.first { $0.id == profileId } ?? profiles.first }

    var body: some View {
        MaterialDialog(
            icon: "mappin.and.ellipse",
            title: "Save this place",
            confirmLabel: "Use current location",
            confirmEnabled: !name.trimmingCharacters(in: .whitespaces).isEmpty && profile != nil,
            onConfirm: {
                if let profile { onConfirm(name.trimmingCharacters(in: .whitespaces), profile.id, radius) }
            },
            onDismiss: onDismiss
        ) {
            VStack(alignment: .leading, spacing: 12) {
                Text("QuietCue captures your current position once, then stores the boundary only on this phone.")
                MaterialTextField(label: "Place name", text: $name, placeholder: "Work, school, or home", limit: 40)
                Menu {
                    ForEach(profiles) { item in
                        Button(item.name) { profileId = item.id }
                    }
                } label: {
                    HStack {
                        Text("Profile: \(profile?.name ?? "Choose")").font(MaterialType.labelLarge)
                    }
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .foregroundStyle(scheme.primary)
                    .overlay(Capsule().stroke(scheme.outline, lineWidth: 1))
                }
                Text("Boundary radius: \(Int(radius)) m")
                SliderM(value: $radius, range: 15...500, step: 1)
                if radius < 100 {
                    Text("Boundaries below 100 m are intended for simulation; real phone location may not trigger reliably.")
                        .font(MaterialType.bodySmall).foregroundStyle(scheme.error)
                }
            }
        }
    }
}
