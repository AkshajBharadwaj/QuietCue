import Foundation
import Observation

/// Central state for the app: the iPhone counterpart of `ProfileViewModel`,
/// plus the edge session the Uno Q normally provides.
@MainActor
@Observable
final class AppModel {
    private let profileStore = ProfileStore()
    private let memoryStore = MemoryStore()
    private let smartStore = SmartProfileStore()
    let edge: EdgeSession
    let hapticEngine: HapticEngine
    let notifier = AlertNotifier()

    private(set) var catalog: ProfileCatalog
    private(set) var memoryBank: MemoryBank
    private(set) var smartProfileState: SmartProfileState
    private(set) var runtimeState = RuntimeState()
    private(set) var hubSpeech = HubSpeechStatus()
    var hubSettings: HubSettings {
        didSet {
            hubSettings.save()
            edge.updateSettings(hubSettings)
            lastSyncedPayload = nil
        }
    }
    var message: String? = nil
    private(set) var geofenceStatus: GeofenceRegistrationStatus = .permissionRequired

    private var pollTask: Task<Void, Never>?
    private var lastSyncedPayload: Data?
    private var lastNotifiedEventId: String?
    @ObservationIgnored private let placeMonitor = SmartPlaceMonitor()
    @ObservationIgnored private let smartCoordinator: SmartProfileCoordinator

    init() {
        let engine = HapticEngine()
        hapticEngine = engine
        let settings = HubSettings.load()
        hubSettings = settings
        edge = EdgeSession(settings: settings, dispatcher: AlertDispatcher(engine: engine))
        catalog = profileStore.catalog
        memoryBank = memoryStore.bank
        smartProfileState = smartStore.state
        smartCoordinator = SmartProfileCoordinator(profiles: profileStore, smart: smartStore)
        edge.updatePhraseTriggers(catalog.activeProfile?.phraseTriggers ?? [])
        placeMonitor.onTransition = { [weak self] placeId, transition in
            Task { @MainActor in
                guard let self else { return }
                let result = try? self.smartCoordinator.handleTransition(placeId: placeId, transition: transition)
                if let result, result.type != .ignored {
                    self.notifier.notifySmartPlace(title: result.title, body: result.message)
                }
                self.reloadSmartState()
            }
        }
    }

    // MARK: Lifecycle

    func start() {
        guard pollTask == nil else { return }
        // Automated simulator runs cannot tap the system prompt; skip it there.
        notifier.onAcknowledge = { [weak self] eventId in
            Task { @MainActor in self?.stopHaptic(eventId: eventId) }
        }
        if ProcessInfo.processInfo.environment["QUIETCUE_SKIP_NOTIFICATION_PROMPT"] == nil {
            notifier.activate()
        }
        if !hubSettings.host.isEmpty { edge.start() }
        refreshSmartPlaces(showMessage: false)
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.pollOnce()
                try? await Task.sleep(for: .seconds(1))
            }
        }
    }

    var hubClient: HubStatusClient? {
        hubSettings.stateBaseURL.map { HubStatusClient(baseURL: $0) }
    }

    private func pollOnce() async {
        guard let client = hubClient else {
            runtimeState = RuntimeState(errorMessage: "Enter the Mac's address to connect")
            return
        }
        do {
            let (state, speech) = try await client.fetchState()
            runtimeState = state
            hubSpeech = speech
            notifyIfNeeded(state.latestAlert)
            if let payload = try? ProfileSyncCodec.encode(catalog: catalog, memoryBank: memoryBank), payload != lastSyncedPayload {
                do {
                    try await client.syncProfile(payload)
                    lastSyncedPayload = payload
                } catch {
                    lastSyncedPayload = nil
                }
            }
        } catch {
            lastSyncedPayload = nil
            runtimeState.backendConnected = false
            runtimeState.audioSourceConnected = false
            runtimeState.errorMessage = error.localizedDescription
        }
    }

    private func notifyIfNeeded(_ alert: DetectedAlert?) {
        guard let alert, !alert.eventId.isEmpty, alert.eventId != lastNotifiedEventId else { return }
        lastNotifiedEventId = alert.eventId
        notifier.notify(alert)
    }

    // MARK: Hub settings

    func connect(host: String, pairingToken: String) {
        var settings = hubSettings
        settings.host = host.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.pairingToken = pairingToken.trimmingCharacters(in: .whitespacesAndNewlines)
        hubSettings = settings
        if settings.host.isEmpty {
            edge.stop()
            message = "Enter the Mac's address to connect"
        } else {
            edge.start()
            message = "Connecting to \(settings.host)"
        }
    }

    // MARK: Profiles

    func save(_ profile: AlertProfile) {
        run("Profile saved") { try profileStore.save(profile) }
    }

    func activate(_ profileId: String) {
        run("Active profile changed; location automation paused for two hours") {
            try smartCoordinator.activateManually(profileId)
        }
    }

    func delete(_ profileId: String) {
        run("Profile deleted") {
            try profileStore.delete(profileId)
            smartStore.removeProfile(profileId)
            refreshGeofences()
        }
    }

    func reset(_ profileId: String) {
        run("Built-in profile restored") { profileStore.resetBuiltIn(profileId) }
    }

    func enrollSound(_ sound: SoundDefinition) {
        run("\(sound.displayName) enrolled") { try profileStore.addEnrolledSound(sound) }
    }

    func deleteEnrolledSound(_ soundId: String) {
        run("Enrolled sound deleted") { profileStore.deleteEnrolledSound(soundId) }
    }

    // MARK: Memory bank

    func saveIdentity(_ identity: UserIdentity) { run("Name enrollment saved") { try memoryStore.saveIdentity(identity) } }
    func deleteIdentity() { run("Name enrollment removed") { try memoryStore.deleteIdentity() } }
    func savePerson(_ person: PersonMemory) { run("Person saved") { try memoryStore.savePerson(person) } }
    func deletePerson(_ personId: String) { run("Person removed") { try memoryStore.deletePerson(personId) } }
    func saveContext(_ context: ContextMemory) { run("Context saved") { try memoryStore.saveContext(context) } }
    func deleteContext(_ contextId: String) { run("Context removed") { try memoryStore.deleteContext(contextId) } }
    func clearMemoryBank() { run("Private memory bank deleted") { memoryStore.clearAll() } }
    func saveSpeechSettings(_ settings: SpeechSettings) { run("Speech settings saved") { try memoryStore.saveSpeechSettings(settings) } }

    /// Settings-page edits apply immediately; the next poll syncs them to the hub.
    func updateSpeechSettings(_ transform: (inout SpeechSettings) -> Void) {
        var settings = memoryBank.speechSettings
        transform(&settings)
        guard settings != memoryBank.speechSettings else { return }
        do {
            try memoryStore.saveSpeechSettings(settings)
            reloadAll()
        } catch {
            message = error.localizedDescription
        }
    }

    // MARK: Smart places

    func addCurrentSmartPlace(name: String, profileId: String, radiusMeters: Float) {
        Task {
            do {
                guard catalog.profiles.contains(where: { $0.id == profileId }) else { throw StoreError(message: "Choose a valid profile") }
                let location = try await placeMonitor.captureCurrentLocation()
                try smartStore.savePlace(
                    SmartPlace(
                        name: name,
                        latitude: location.latitude,
                        longitude: location.longitude,
                        radiusMeters: radiusMeters,
                        profileId: profileId
                    )
                )
                reloadSmartState()
                await refreshPlaceMonitoring()
                message = "\(name) saved; QuietCue will suggest the selected profile here"
            } catch {
                message = error.localizedDescription
            }
        }
    }

    func addDemoSmartPlace() {
        let profiles = catalog.profiles
        let target = profiles.first { $0.name.localizedCaseInsensitiveContains("Work") }
            ?? profiles.first { $0.id != catalog.activeProfileId }
        guard let target else {
            message = "Create another profile before running the location demo"
            return
        }
        run("Demo place ready; tap Simulate arrival") {
            try smartStore.savePlace(
                SmartPlace(
                    id: Self.demoPlaceId,
                    name: "Hackathon venue",
                    latitude: 0,
                    longitude: 0,
                    radiusMeters: 15,
                    profileId: target.id,
                    demoOnly: true
                )
            )
        }
    }

    func deleteSmartPlace(_ placeId: String) {
        run("Place removed") {
            smartStore.deletePlace(placeId)
            Task { await refreshPlaceMonitoring() }
        }
    }

    func setSmartPlaceAutoApply(_ placeId: String, enabled: Bool) {
        run(enabled ? "Automatic switching enabled" : "Profile suggestions enabled") {
            smartStore.setAutoApply(placeId, enabled: enabled)
            Task { await refreshPlaceMonitoring() }
        }
    }

    func simulateSmartPlace(_ placeId: String, transition: PlaceTransition) {
        do {
            let result = try smartCoordinator.handleTransition(placeId: placeId, transition: transition, simulated: true)
            reloadAll()
            message = result.message
        } catch {
            message = error.localizedDescription
        }
    }

    func acceptSmartProfileSuggestion(always: Bool) {
        do {
            let suggestion = try smartCoordinator.acceptSuggestion(always: always)
            reloadAll()
            if let suggestion {
                message = always && suggestion.transition == .enter
                    ? "\(suggestion.targetProfileName) active; future arrivals will switch automatically"
                    : "\(suggestion.targetProfileName) is now active"
            } else {
                message = "That suggestion is no longer available"
            }
        } catch {
            message = error.localizedDescription
        }
    }

    func dismissSmartProfileSuggestion() {
        run("Location suggestion dismissed") { smartStore.dismissSuggestion() }
    }

    func refreshSmartPlaces(showMessage: Bool) {
        Task {
            let status = await refreshPlaceMonitoring()
            guard showMessage else { return }
            switch status {
            case .active: message = "Background place suggestions are active"
            case .noPlaces: message = "Add a real place to start monitoring"
            case .permissionRequired: message = "Allow precise and all-time location access"
            case .registrationFailed: message = "iOS could not register the saved boundaries"
            }
        }
    }

    func requestLocationPermission() {
        placeMonitor.requestAlwaysAuthorization()
    }

    var locationPermission: SmartPlaceMonitor.Permission { placeMonitor.permission }

    @discardableResult
    private func refreshPlaceMonitoring() async -> GeofenceRegistrationStatus {
        let status = refreshGeofences()
        if status == .active {
            await reconcileCurrentPlace()
        }
        return status
    }

    @discardableResult
    private func refreshGeofences() -> GeofenceRegistrationStatus {
        let status = placeMonitor.refresh(places: smartStore.state.places)
        geofenceStatus = status
        return status
    }

    private func reconcileCurrentPlace() async {
        let state = smartStore.state
        let realPlaces = state.places.filter { $0.enabled && !$0.demoOnly }
        guard !realPlaces.isEmpty, let location = try? await placeMonitor.captureCurrentLocation() else { return }
        let current = SmartPlaceMonitor.containingPlace(realPlaces, latitude: location.latitude, longitude: location.longitude)
        if let active = state.activePlaceId, active != current?.id {
            _ = try? smartCoordinator.handleTransition(placeId: active, transition: .exit)
        }
        if let current, smartStore.state.activePlaceId != current.id {
            _ = try? smartCoordinator.handleTransition(placeId: current.id, transition: .enter)
        }
        reloadAll()
    }

    // MARK: Hub actions

    /// Ask the Mac's Whisper model how it spells the name. The hub listens to
    /// the live iPhone stream, so the edge session must be running.
    func learnNameSpelling(name: String, knownSpellings: [String]) async throws -> NameSpellingResult {
        guard let client = hubClient else { throw HubStatusError(message: "Enter the Mac's address on the Home tab first") }
        guard edge.isRunning else { throw HubStatusError(message: "Connect the iPhone microphone to the hub first") }
        return try await client.learnNameSpelling(name: name, knownSpellings: knownSpellings)
    }

    func captureEnrollmentSession(durationMs: Int, minRepeats: Int = 1) async throws -> EnrollmentCapture {
        guard let client = hubClient else { throw HubStatusError(message: "Enter the Mac's address first") }
        return try await client.captureEnrollmentSession(durationMs: durationMs, minRepeats: minRepeats)
    }

    func setInferenceDevice(_ device: InferenceDevice) {
        if runtimeState.requestedInferenceDevice == device && !runtimeState.inferenceSwitchPending { return }
        runtimeState.requestedInferenceDevice = device
        runtimeState.inferenceSwitchPending = true
        runtimeState.inferenceRoutingError = nil
        Task {
            guard let client = hubClient else { return }
            do {
                try await client.setInferenceDevice(device)
                let (state, speech) = try await client.fetchState()
                runtimeState = state
                hubSpeech = speech
                message = "\(device.displayName) inference selected"
            } catch {
                runtimeState.inferenceSwitchPending = false
                runtimeState.inferenceRoutingError = error.localizedDescription
                message = error.localizedDescription
            }
        }
    }

    func stopHaptic(eventId: String) {
        guard !runtimeState.stopInProgress else { return }
        runtimeState.stopInProgress = true
        // Stop the phone's own motor immediately (the wearable's button), then
        // tell the hub so the dashboard state and control queue agree.
        edge.acknowledge()
        notifier.cancel(eventId: eventId)
        Task {
            defer { runtimeState.stopInProgress = false }
            guard let client = hubClient else { return }
            do {
                try await client.stopHaptic(eventId: eventId)
                if let (state, speech) = try? await client.fetchState() {
                    runtimeState = state
                    hubSpeech = speech
                }
                message = "Vibration stopped"
            } catch {
                message = error.localizedDescription
            }
        }
    }

    func previewHaptic(_ pattern: CustomHapticPattern) {
        hapticEngine.preview(steps: pattern.steps.map { HapticStep(onMs: $0.onMs, offMs: $0.offMs) })
    }

    func clearMessage() { message = nil }

    // MARK: Helpers

    private func run(_ success: String, _ action: () throws -> Void) {
        do {
            try action()
            reloadAll()
            message = success
        } catch {
            message = error.localizedDescription
        }
    }

    private func reloadAll() {
        catalog = profileStore.catalog
        memoryBank = memoryStore.bank
        reloadSmartState()
        edge.updatePhraseTriggers(catalog.activeProfile?.phraseTriggers ?? [])
    }

    private func reloadSmartState() {
        smartProfileState = smartStore.state
    }

    static let demoPlaceId = "demo-hackathon-venue"
}
