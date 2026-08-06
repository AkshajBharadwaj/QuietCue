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
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.CapturedFingerprint
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.SoundDiscoveryCandidate
import com.quietcue.app.domain.UserIdentity
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

    private val _message = MutableStateFlow<String?>(null)
    val message: StateFlow<String?> = _message.asStateFlow()

    private val _runtimeState = MutableStateFlow(RuntimeState())
    val runtimeState: StateFlow<RuntimeState> = _runtimeState.asStateFlow()

    init {
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

    fun activate(profileId: String) = runAction("Active profile changed") {
        repository.setActive(profileId)
    }

    fun delete(profileId: String) = runAction("Profile deleted") {
        repository.delete(profileId)
    }

    fun reset(profileId: String) = runAction("Built-in profile restored") {
        repository.resetBuiltIn(profileId)
    }

    fun enrollSound(sound: SoundDefinition, discoveryId: String? = null) {
        viewModelScope.launch {
            runCatching { repository.addEnrolledSound(sound) }
                .onSuccess {
                    if (discoveryId != null) {
                        runCatching { alertRepository.updateDiscovery(discoveryId, "taught") }
                    }
                    _message.value = "${sound.displayName} enrolled"
                }
                .onFailure { _message.value = it.message ?: "Something went wrong" }
        }
    }

    fun deleteEnrolledSound(soundId: String) = runAction("Enrolled sound deleted") {
        repository.deleteEnrolledSound(soundId)
    }

    fun dismissDiscovery(candidateId: String) = runAction("Sound suggestion dismissed") {
        alertRepository.updateDiscovery(candidateId, "dismiss")
    }

    fun addDiscovery(candidate: SoundDiscoveryCandidate) {
        viewModelScope.launch {
            runCatching { repository.addDiscoveredSound(candidate) }
                .onSuccess {
                    runCatching { alertRepository.updateDiscovery(candidate.id, "taught") }
                    _message.value = "${candidate.label} added to the active profile"
                }
                .onFailure { _message.value = it.message ?: "Something went wrong" }
        }
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

    companion object {
        fun factory(context: Context): ViewModelProvider.Factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                require(modelClass.isAssignableFrom(ProfileViewModel::class.java))
                return ProfileViewModel(
                    ProfileRepository(context.applicationContext),
                    AlertRepository(),
                    PhoneEnrollmentRecorder(),
                    MemoryRepository(context.applicationContext),
                    OnDeviceNameRecognizer(context.applicationContext),
                ) as T
            }
        }
    }
}
