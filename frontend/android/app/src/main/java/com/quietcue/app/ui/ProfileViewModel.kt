package com.quietcue.app.ui

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quietcue.app.data.AlertRepository
import com.quietcue.app.data.MemoryRepository
import com.quietcue.app.data.OnDeviceNameRecognizer
import com.quietcue.app.data.ProfileRepository
import com.quietcue.app.data.PhoneEnrollmentRecorder
import com.quietcue.app.data.ProfileSyncJsonCodec
import com.quietcue.app.data.SmartProfileCoordinator
import com.quietcue.app.data.SmartProfileRepository
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.CapturedFingerprint
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartPlace
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.domain.UserIdentity
import com.quietcue.app.location.GeofenceRegistrationStatus
import com.quietcue.app.location.SmartPlaceGeofenceManager
import com.quietcue.app.location.SmartPlaceLocationClient
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class ProfileViewModel(
    private val repository: ProfileRepository,
    private val alertRepository: AlertRepository,
    private val enrollmentRecorder: PhoneEnrollmentRecorder,
    private val memoryRepository: MemoryRepository,
    private val nameRecognizer: OnDeviceNameRecognizer,
    private val smartRepository: SmartProfileRepository,
    private val smartCoordinator: SmartProfileCoordinator,
    private val geofenceManager: SmartPlaceGeofenceManager,
    private val locationClient: SmartPlaceLocationClient,
) : ViewModel() {
    val catalog: StateFlow<ProfileCatalog> = repository.catalog.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = ProfileCatalog(ProfileDefaults.all(), ProfileDefaults.HOME_ID),
    )

    val memoryBank: StateFlow<MemoryBank> = memoryRepository.bank.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = MemoryBank(),
    )

    val smartProfileState: StateFlow<SmartProfileState> = smartRepository.state.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = SmartProfileState(),
    )

    private val _geofenceStatus = MutableStateFlow(GeofenceRegistrationStatus.PERMISSION_REQUIRED)
    val geofenceStatus: StateFlow<GeofenceRegistrationStatus> = _geofenceStatus.asStateFlow()

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _runtimeState = MutableStateFlow(RuntimeState())
    val runtimeState: StateFlow<RuntimeState> = _runtimeState.asStateFlow()

    init {
        refreshSmartPlaces(showMessage = false)
        viewModelScope.launch {
            var lastSyncedProfile: String? = null
            while (true) {
                runCatching { alertRepository.fetchState() }
                    .onSuccess { state ->
                        _runtimeState.value = state
                        val currentCatalog = catalog.value
                        val currentMemoryBank = memoryBank.value
                        val payload = runCatching {
                            ProfileSyncJsonCodec.encode(currentCatalog, currentMemoryBank)
                        }.getOrNull()
                        if (payload != null && payload != lastSyncedProfile) {
                            runCatching { alertRepository.syncProfile(currentCatalog, currentMemoryBank) }
                                .onSuccess { lastSyncedProfile = payload }
                                .onFailure { lastSyncedProfile = null }
                        }
                    }
                    .onFailure { error ->
                        lastSyncedProfile = null
                        _runtimeState.value = _runtimeState.value.copy(
                            backendConnected = false,
                            audioSourceConnected = false,
                            errorMessage = error.message,
                        )
                    }
                delay(1_000)
            }
        }
    }

    fun save(profile: AlertProfile) = runAction("Profile saved") { repository.save(profile) }

    fun activate(profileId: String) = runAction("Active profile changed; location automation paused for two hours") {
        smartCoordinator.activateManually(profileId)
    }

    fun delete(profileId: String) = runAction("Profile deleted") {
        repository.delete(profileId)
        smartRepository.removeProfile(profileId)
        refreshGeofences()
    }

    fun reset(profileId: String) = runAction("Built-in profile restored") {
        repository.resetBuiltIn(profileId)
    }

    fun enrollSound(sound: SoundDefinition) {
        viewModelScope.launch {
            runCatching { repository.addEnrolledSound(sound) }
                .onSuccess {
                    _message.value = "${sound.displayName} enrolled"
                }
                .onFailure { _message.value = it.message ?: "Something went wrong" }
        }
    }

    fun deleteEnrolledSound(soundId: String) = runAction("Enrolled sound deleted") {
        repository.deleteEnrolledSound(soundId)
    }

    fun saveIdentity(identity: UserIdentity) = runAction("Name enrollment saved") {
        memoryRepository.saveIdentity(identity)
    }

    fun deleteIdentity() = runAction("Name enrollment removed") { memoryRepository.deleteIdentity() }

    fun savePerson(person: PersonMemory) = runAction("Person saved") { memoryRepository.savePerson(person) }

    fun deletePerson(personId: String) = runAction("Person removed") {
        memoryRepository.deletePerson(personId)
    }

    fun saveContext(context: ContextMemory) = runAction("Context saved") {
        memoryRepository.saveContext(context)
    }

    fun deleteContext(contextId: String) = runAction("Context removed") {
        memoryRepository.deleteContext(contextId)
    }

    fun clearMemoryBank() = runAction("Private memory bank deleted") { memoryRepository.clearAll() }

    fun addCurrentSmartPlace(
        name: String,
        profileId: String,
        radiusMeters: Float,
    ) {
        viewModelScope.launch {
            runCatching {
                require(catalog.value.profiles.any { it.id == profileId }) { "Choose a valid profile" }
                val location = locationClient.captureCurrentLocation()
                smartRepository.savePlace(
                    SmartPlace(
                        name = name,
                        latitude = location.latitude,
                        longitude = location.longitude,
                        radiusMeters = radiusMeters,
                        profileId = profileId,
                    ),
                )
                refreshGeofences()
            }.onSuccess {
                _message.value = "$name saved; QuietCue will suggest the selected profile here"
            }.onFailure { error ->
                _message.value = error.message ?: "Could not save this place"
            }
        }
    }

    fun addDemoSmartPlace() {
        viewModelScope.launch {
            runCatching {
                val profiles = catalog.value.profiles
                val target = profiles.firstOrNull { it.name.contains("Work", ignoreCase = true) }
                    ?: profiles.firstOrNull { it.id != catalog.value.activeProfileId }
                    ?: error("Create another profile before running the location demo")
                smartRepository.savePlace(
                    SmartPlace(
                        id = DEMO_PLACE_ID,
                        name = "Hackathon venue",
                        latitude = 0.0,
                        longitude = 0.0,
                        radiusMeters = 150f,
                        profileId = target.id,
                        demoOnly = true,
                    ),
                )
            }.onSuccess {
                _message.value = "Demo place ready; tap Simulate arrival"
            }.onFailure { error ->
                _message.value = error.message ?: "Could not create the demo place"
            }
        }
    }

    fun deleteSmartPlace(placeId: String) {
        viewModelScope.launch {
            runCatching {
                smartRepository.deletePlace(placeId)
                refreshGeofences()
            }.onSuccess { _message.value = "Place removed" }
                .onFailure { _message.value = it.message ?: "Could not remove the place" }
        }
    }

    fun setSmartPlaceAutoApply(placeId: String, enabled: Boolean) = runAction(
        if (enabled) "Automatic switching enabled" else "Profile suggestions enabled",
    ) {
        smartRepository.setAutoApply(placeId, enabled)
    }

    fun simulateSmartPlace(placeId: String, transition: PlaceTransition) {
        viewModelScope.launch {
            runCatching {
                smartCoordinator.handleTransition(placeId, transition, simulated = true)
            }.onSuccess { result ->
                _message.value = result.message
            }.onFailure { error ->
                _message.value = error.message ?: "Could not simulate this place"
            }
        }
    }

    fun acceptSmartProfileSuggestion(always: Boolean) {
        viewModelScope.launch {
            runCatching { smartCoordinator.acceptSuggestion(always) }
                .onSuccess { suggestion ->
                    _message.value = suggestion?.let {
                        if (always && it.transition == PlaceTransition.ENTER) {
                            "${it.targetProfileName} active; future arrivals will switch automatically"
                        } else {
                            "${it.targetProfileName} is now active"
                        }
                    } ?: "That suggestion is no longer available"
                }
                .onFailure { _message.value = it.message ?: "Could not change profiles" }
        }
    }

    fun dismissSmartProfileSuggestion() = runAction("Location suggestion dismissed") {
        smartCoordinator.dismissSuggestion()
    }

    fun refreshSmartPlaces(showMessage: Boolean = false) {
        viewModelScope.launch {
            runCatching { refreshGeofences() }
                .onSuccess { status ->
                    if (showMessage) {
                        _message.value = when (status) {
                            GeofenceRegistrationStatus.ACTIVE -> "Background place suggestions are active"
                            GeofenceRegistrationStatus.NO_PLACES -> "Add a real place to start monitoring"
                            GeofenceRegistrationStatus.PERMISSION_REQUIRED -> "Allow precise and all-time location access"
                            GeofenceRegistrationStatus.PLAY_SERVICES_UNAVAILABLE -> "Google Play location services are unavailable"
                            GeofenceRegistrationStatus.REGISTRATION_FAILED -> "Android could not register the saved boundaries"
                        }
                    }
                }
                .onFailure { error -> if (showMessage) _message.value = error.message }
        }
    }

    suspend fun recordEnrollmentFingerprint(): CapturedFingerprint =
        enrollmentRecorder.recordFingerprint()

    suspend fun recognizeNameSample(): String = nameRecognizer.recognize()

    fun clearMessage() {
        _message.value = null
    }

    private fun runAction(successMessage: String, action: suspend () -> Unit) {
        viewModelScope.launch {
            runCatching { action() }
                .onSuccess { _message.value = successMessage }
                .onFailure { _message.value = it.message ?: "Something went wrong" }
        }
    }

    private suspend fun refreshGeofences(): GeofenceRegistrationStatus = runCatching {
        geofenceManager.refresh()
    }.getOrDefault(GeofenceRegistrationStatus.REGISTRATION_FAILED).also {
        _geofenceStatus.value = it
    }

    companion object {
        fun factory(context: Context): ViewModelProvider.Factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                require(modelClass.isAssignableFrom(ProfileViewModel::class.java))
                val profileRepository = ProfileRepository(context.applicationContext)
                val smartRepository = SmartProfileRepository(context.applicationContext)
                return ProfileViewModel(
                    profileRepository,
                    AlertRepository(),
                    PhoneEnrollmentRecorder(),
                    MemoryRepository(context.applicationContext),
                    OnDeviceNameRecognizer(context.applicationContext),
                    smartRepository,
                    SmartProfileCoordinator(profileRepository, smartRepository),
                    SmartPlaceGeofenceManager(context.applicationContext, smartRepository),
                    SmartPlaceLocationClient(context.applicationContext),
                ) as T
            }
        }

        private const val DEMO_PLACE_ID = "demo-hackathon-venue"
    }
}
