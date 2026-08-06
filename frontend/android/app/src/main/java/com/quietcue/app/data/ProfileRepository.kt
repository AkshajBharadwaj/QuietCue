package com.quietcue.app.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.ProfileValidator
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.HapticStrength
import com.quietcue.app.domain.SoundDiscoveryCandidate
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.SoundLibrary
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

private val Context.profileDataStore by preferencesDataStore(name = "quietcue_profiles")

class ProfileRepository(private val context: Context) {
    private object Keys {
        val profilesJson = stringPreferencesKey("profiles_json")
        val activeProfileId = stringPreferencesKey("active_profile_id")
        val customSoundsJson = stringPreferencesKey("custom_sounds_json")
    }

    val catalog: Flow<ProfileCatalog> = context.profileDataStore.data
        .catch { error ->
            if (error is IOException) emit(androidx.datastore.preferences.core.emptyPreferences())
            else throw error
        }
        .map(::catalogFrom)

    suspend fun save(profile: AlertProfile) {
        context.profileDataStore.edit { preferences ->
            val soundLibrary = soundLibraryFrom(preferences)
            val cleaned = profile.copy(
                name = profile.name.trim(),
                description = profile.description.trim(),
                phraseTriggers = profile.phraseTriggers.map(String::trim).filter(String::isNotEmpty).distinct(),
                soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary),
            )
            val errors = ProfileValidator.validate(cleaned, soundLibrary)
            require(errors.isEmpty()) { errors.joinToString(" ") }
            val profiles = profilesFrom(preferences, soundLibrary).toMutableList()
            val index = profiles.indexOfFirst { it.id == cleaned.id }
            if (index >= 0) profiles[index] = cleaned else profiles += cleaned
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
            if (preferences[Keys.activeProfileId].isNullOrBlank()) {
                preferences[Keys.activeProfileId] = ProfileDefaults.HOME_ID
            }
        }
    }

    suspend fun setActive(profileId: String) {
        context.profileDataStore.edit { preferences ->
            require(profilesFrom(preferences, soundLibraryFrom(preferences)).any { it.id == profileId }) {
                "Unknown profile: $profileId"
            }
            preferences[Keys.activeProfileId] = profileId
        }
    }

    suspend fun delete(profileId: String) {
        context.profileDataStore.edit { preferences ->
            val profiles = profilesFrom(preferences, soundLibraryFrom(preferences))
            val profile = profiles.firstOrNull { it.id == profileId } ?: return@edit
            require(!profile.isBuiltIn) { "Built-in profiles cannot be deleted" }
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(profiles.filterNot { it.id == profileId })
            if (preferences[Keys.activeProfileId] == profileId) {
                preferences[Keys.activeProfileId] = ProfileDefaults.HOME_ID
            }
        }
    }

    suspend fun resetBuiltIn(profileId: String) {
        context.profileDataStore.edit { preferences ->
            val soundLibrary = soundLibraryFrom(preferences)
            val profiles = profilesFrom(preferences, soundLibrary).toMutableList()
            val index = profiles.indexOfFirst { it.id == profileId }
            val builtIn = profiles.getOrNull(index)?.builtIn ?: return@edit
            profiles[index] = ProfileDefaults.forBuiltIn(builtIn).let { profile ->
                profile.copy(soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary))
            }
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
        }
    }

    suspend fun addEnrolledSound(sound: SoundDefinition) {
        require(sound.id.startsWith("custom:") && sound.enrollment != null) { "Sound must be enrolled" }
        require(sound.displayName.isNotBlank()) { "Give the sound a name" }
        context.profileDataStore.edit { preferences ->
            val existingCustom = customSoundsFrom(preferences)
            require(existingCustom.none { it.displayName.equals(sound.displayName, ignoreCase = true) }) {
                "A sound with that name already exists"
            }
            val customSounds = existingCustom + sound
            val library = SoundLibrary.complete(customSounds)
            val activeId = preferences[Keys.activeProfileId] ?: ProfileDefaults.HOME_ID
            val profiles = profilesFrom(preferences, SoundLibrary.complete(existingCustom)).map { profile ->
                val completed = ProfileDefaults.completeRules(profile.soundRules, library)
                profile.copy(
                    soundRules = completed.map { rule ->
                        if (rule.soundId == sound.id) {
                            ProfileDefaults.ruleForSound(sound, enabled = profile.id == activeId)
                        } else rule
                    },
                )
            }
            preferences[Keys.customSoundsJson] = SoundLibraryJsonCodec.encode(customSounds)
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
        }
    }

    suspend fun addDiscoveredSound(candidate: SoundDiscoveryCandidate) {
        require(candidate.id.startsWith("disc_") && candidate.label.isNotBlank()) {
            "Invalid Sound Scout candidate"
        }
        val sound = SoundDefinition(
            id = "custom:label:${candidate.id.removePrefix("disc_")}",
            displayName = candidate.label.take(40),
            description = "Recurring sound discovered locally by Sound Scout",
            defaultPriority = AlertPriority.INFORMATIONAL,
            defaultHapticPattern = HapticPattern.TWO_SHORT,
            defaultHapticStrength = HapticStrength.GENTLE,
            classifierLabels = listOf(candidate.label.take(100)),
        )
        context.profileDataStore.edit { preferences ->
            val existingCustom = customSoundsFrom(preferences)
            require(existingCustom.none { it.displayName.equals(sound.displayName, ignoreCase = true) }) {
                "A sound with that name already exists"
            }
            require(existingCustom.none { existing ->
                existing.classifierLabels.any { it.equals(candidate.label, ignoreCase = true) }
            }) { "That classifier label is already configured" }
            val customSounds = existingCustom + sound
            val oldLibrary = SoundLibrary.complete(existingCustom)
            val library = SoundLibrary.complete(customSounds)
            val activeId = preferences[Keys.activeProfileId] ?: ProfileDefaults.HOME_ID
            val suggestedThreshold = (candidate.meanConfidence - 0.10f).coerceIn(0.35f, 0.80f)
            val profiles = profilesFrom(preferences, oldLibrary).map { profile ->
                val completed = ProfileDefaults.completeRules(profile.soundRules, library)
                profile.copy(
                    soundRules = completed.map { rule ->
                        if (rule.soundId == sound.id) {
                            ProfileDefaults.ruleForSound(sound, enabled = profile.id == activeId).copy(
                                confidenceThreshold = suggestedThreshold,
                                cooldownSeconds = 30,
                            )
                        } else rule
                    },
                )
            }
            preferences[Keys.customSoundsJson] = SoundLibraryJsonCodec.encode(customSounds)
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
        }
    }

    suspend fun deleteEnrolledSound(soundId: String) {
        context.profileDataStore.edit { preferences ->
            val customSounds = customSoundsFrom(preferences).filterNot { it.id == soundId }
            val oldLibrary = soundLibraryFrom(preferences)
            val profiles = profilesFrom(preferences, oldLibrary).map { profile ->
                profile.copy(soundRules = profile.soundRules.filterNot { it.soundId == soundId })
            }
            preferences[Keys.customSoundsJson] = SoundLibraryJsonCodec.encode(customSounds)
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
        }
    }

    private fun catalogFrom(preferences: Preferences): ProfileCatalog {
        val soundLibrary = soundLibraryFrom(preferences)
        val profiles = profilesFrom(preferences, soundLibrary)
        val requestedActiveId = preferences[Keys.activeProfileId]
        val activeId = requestedActiveId?.takeIf { id -> profiles.any { it.id == id } }
            ?: ProfileDefaults.HOME_ID
        return ProfileCatalog(profiles = profiles, activeProfileId = activeId, soundLibrary = soundLibrary)
    }

    private fun profilesFrom(
        preferences: Preferences,
        soundLibrary: List<SoundDefinition>,
    ): List<AlertProfile> {
        val stored = preferences[Keys.profilesJson]
        val decoded = stored?.let { runCatching { ProfileJsonCodec.decode(it) }.getOrNull() }.orEmpty()
        if (decoded.isEmpty()) {
            return ProfileDefaults.all().map { profile ->
                profile.copy(soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary))
            }
        }

        val profilesByBuiltIn = decoded.filter { it.builtIn != null }.associateBy { it.builtIn }
        val completedBuiltIns = ProfileDefaults.all().map { default ->
            val storedProfile = profilesByBuiltIn[default.builtIn] ?: default
            storedProfile.copy(
                phraseTriggers = storedProfile.phraseTriggers.filterNot { it.equals("my name", ignoreCase = true) },
                soundRules = ProfileDefaults.completeRules(storedProfile.soundRules, soundLibrary),
            )
        }
        return completedBuiltIns + decoded.filter { it.builtIn == null }.map { profile ->
            profile.copy(soundRules = ProfileDefaults.completeRules(profile.soundRules, soundLibrary))
        }
    }

    private fun soundLibraryFrom(preferences: Preferences): List<SoundDefinition> =
        SoundLibrary.complete(customSoundsFrom(preferences))

    private fun customSoundsFrom(preferences: Preferences): List<SoundDefinition> =
        preferences[Keys.customSoundsJson]
            ?.let { runCatching { SoundLibraryJsonCodec.decode(it) }.getOrNull() }
            .orEmpty()

    private fun sortProfiles(profiles: List<AlertProfile>): List<AlertProfile> {
        val builtInOrder = ProfileDefaults.all().mapIndexed { index, profile -> profile.builtIn to index }.toMap()
        return profiles.sortedWith(
            compareBy<AlertProfile> { it.builtIn == null }
                .thenBy { builtInOrder[it.builtIn] ?: Int.MAX_VALUE }
                .thenBy { it.name.lowercase() },
        )
    }
}
