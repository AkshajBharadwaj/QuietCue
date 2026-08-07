package com.quietcue.app.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.MemoryBankValidator
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.SpeechSettings
import com.quietcue.app.domain.UserIdentity
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map

private val Context.memoryDataStore by preferencesDataStore(name = "quietcue_private_memory")

class MemoryRepository(private val context: Context) {
    private object Keys {
        val encryptedBank = stringPreferencesKey("encrypted_memory_bank")
    }

    private val vault = EncryptedMemoryVault()

    val bank: Flow<MemoryBank> = context.memoryDataStore.data
        .catch { error ->
            if (error is IOException) emit(emptyPreferences()) else throw error
        }
        .map(::bankFrom)

    suspend fun saveIdentity(identity: UserIdentity) = update { bank -> bank.copy(identity = identity.cleaned()) }

    suspend fun deleteIdentity() = update { bank -> bank.copy(identity = null) }

    suspend fun savePerson(person: PersonMemory) = update { bank ->
        val cleaned = person.cleaned()
        val people = bank.people.toMutableList()
        val index = people.indexOfFirst { it.id == cleaned.id }
        if (index >= 0) people[index] = cleaned else people += cleaned
        bank.copy(people = people.sortedBy { it.name.lowercase() })
    }

    suspend fun deletePerson(personId: String) = update { bank ->
        bank.copy(people = bank.people.filterNot { it.id == personId })
    }

    suspend fun saveContext(context: ContextMemory) = update { bank ->
        val cleaned = context.cleaned()
        val contexts = bank.contexts.toMutableList()
        val index = contexts.indexOfFirst { it.id == cleaned.id }
        if (index >= 0) contexts[index] = cleaned else contexts += cleaned
        bank.copy(contexts = contexts.sortedBy { it.title.lowercase() })
    }

    suspend fun deleteContext(contextId: String) = update { bank ->
        bank.copy(contexts = bank.contexts.filterNot { it.id == contextId })
    }

    suspend fun saveSpeechSettings(settings: SpeechSettings) = update { bank ->
        bank.copy(
            speechSettings = settings.copy(
                sensitivity = settings.sensitivity.coerceIn(0.4f, 0.95f),
                globalPhrases = settings.globalPhrases.cleanedText(),
            ),
        )
    }

    suspend fun clearAll() {
        context.memoryDataStore.edit { it.remove(Keys.encryptedBank) }
    }

    private suspend fun update(transform: (MemoryBank) -> MemoryBank) {
        context.memoryDataStore.edit { preferences ->
            val updated = transform(bankFrom(preferences))
            val errors = MemoryBankValidator.validate(updated)
            require(errors.isEmpty()) { errors.joinToString(" ") }
            preferences[Keys.encryptedBank] = vault.encrypt(MemoryJsonCodec.encode(updated))
        }
    }

    private fun bankFrom(preferences: Preferences): MemoryBank {
        val encrypted = preferences[Keys.encryptedBank] ?: return MemoryBank()
        return MemoryJsonCodec.decode(vault.decrypt(encrypted))
    }

    private fun UserIdentity.cleaned() = copy(
        displayName = displayName.trim(),
        pronunciation = pronunciation.trim(),
        aliases = aliases.cleanedText(),
        recognitionPhrases = recognitionPhrases.cleanedText(),
        updatedAtEpochMs = System.currentTimeMillis(),
    )

    private fun PersonMemory.cleaned() = copy(
        name = name.trim(),
        relationship = relationship.trim(),
        pronunciation = pronunciation.trim(),
        aliases = aliases.cleanedText(),
        notes = notes.trim(),
        updatedAtEpochMs = System.currentTimeMillis(),
    )

    private fun ContextMemory.cleaned() = copy(
        title = title.trim(),
        details = details.trim(),
        updatedAtEpochMs = System.currentTimeMillis(),
    )

    private fun List<String>.cleanedText(): List<String> =
        map(String::trim).filter(String::isNotEmpty).distinctBy { it.lowercase() }
}
