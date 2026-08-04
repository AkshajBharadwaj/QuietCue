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
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

private val Context.profileDataStore by preferencesDataStore(name = "quietcue_profiles")

class ProfileRepository(private val context: Context) {
    private object Keys {
        val profilesJson = stringPreferencesKey("profiles_json")
        val activeProfileId = stringPreferencesKey("active_profile_id")
    }

    val catalog: Flow<ProfileCatalog> = context.profileDataStore.data
        .catch { error ->
            if (error is IOException) emit(androidx.datastore.preferences.core.emptyPreferences())
            else throw error
        }
        .map(::catalogFrom)

    suspend fun save(profile: AlertProfile) {
        val cleaned = profile.copy(
            name = profile.name.trim(),
            description = profile.description.trim(),
            phraseTriggers = profile.phraseTriggers.map(String::trim).filter(String::isNotEmpty).distinct(),
            soundRules = ProfileDefaults.completeRules(profile.soundRules),
        )
        val errors = ProfileValidator.validate(cleaned)
        require(errors.isEmpty()) { errors.joinToString(" ") }

        context.profileDataStore.edit { preferences ->
            val profiles = profilesFrom(preferences).toMutableList()
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
            require(profilesFrom(preferences).any { it.id == profileId }) { "Unknown profile: $profileId" }
            preferences[Keys.activeProfileId] = profileId
        }
    }

    suspend fun delete(profileId: String) {
        context.profileDataStore.edit { preferences ->
            val profiles = profilesFrom(preferences)
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
            val profiles = profilesFrom(preferences).toMutableList()
            val index = profiles.indexOfFirst { it.id == profileId }
            val builtIn = profiles.getOrNull(index)?.builtIn ?: return@edit
            profiles[index] = ProfileDefaults.forBuiltIn(builtIn)
            preferences[Keys.profilesJson] = ProfileJsonCodec.encode(sortProfiles(profiles))
        }
    }

    private fun catalogFrom(preferences: Preferences): ProfileCatalog {
        val profiles = profilesFrom(preferences)
        val requestedActiveId = preferences[Keys.activeProfileId]
        val activeId = requestedActiveId?.takeIf { id -> profiles.any { it.id == id } }
            ?: ProfileDefaults.HOME_ID
        return ProfileCatalog(profiles = profiles, activeProfileId = activeId)
    }

    private fun profilesFrom(preferences: Preferences): List<AlertProfile> {
        val stored = preferences[Keys.profilesJson]
        val decoded = stored?.let { runCatching { ProfileJsonCodec.decode(it) }.getOrNull() }.orEmpty()
        if (decoded.isEmpty()) return ProfileDefaults.all()

        val profilesByBuiltIn = decoded.filter { it.builtIn != null }.associateBy { it.builtIn }
        val completedBuiltIns = ProfileDefaults.all().map { default ->
            profilesByBuiltIn[default.builtIn] ?: default
        }
        return completedBuiltIns + decoded.filter { it.builtIn == null }
    }

    private fun sortProfiles(profiles: List<AlertProfile>): List<AlertProfile> {
        val builtInOrder = ProfileDefaults.all().mapIndexed { index, profile -> profile.builtIn to index }.toMap()
        return profiles.sortedWith(
            compareBy<AlertProfile> { it.builtIn == null }
                .thenBy { builtInOrder[it.builtIn] ?: Int.MAX_VALUE }
                .thenBy { it.name.lowercase() },
        )
    }
}
