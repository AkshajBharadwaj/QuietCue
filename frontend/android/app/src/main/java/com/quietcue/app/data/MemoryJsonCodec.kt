package com.quietcue.app.data

import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.SpeechModel
import com.quietcue.app.domain.SpeechSettings
import com.quietcue.app.domain.UserIdentity
import org.json.JSONArray
import org.json.JSONObject

object MemoryJsonCodec {
    fun encode(bank: MemoryBank): String = JSONObject()
        .put("version", 2)
        .put("identity", bank.identity?.let(::encodeIdentity))
        .put("people", JSONArray().apply { bank.people.forEach { put(encodePerson(it)) } })
        .put("contexts", JSONArray().apply { bank.contexts.forEach { put(encodeContext(it)) } })
        .put("speechSettings", encodeSpeechSettings(bank.speechSettings))
        .toString()

    fun decode(value: String): MemoryBank {
        if (value.isBlank()) return MemoryBank()
        val root = JSONObject(value)
        val peopleJson = root.optJSONArray("people")
        val contextsJson = root.optJSONArray("contexts")
        return MemoryBank(
            identity = root.optJSONObject("identity")?.let(::decodeIdentity),
            people = buildList {
                if (peopleJson != null) {
                    for (index in 0 until peopleJson.length()) {
                        peopleJson.optJSONObject(index)?.let { add(decodePerson(it)) }
                    }
                }
            },
            contexts = buildList {
                if (contextsJson != null) {
                    for (index in 0 until contextsJson.length()) {
                        contextsJson.optJSONObject(index)?.let { add(decodeContext(it)) }
                    }
                }
            },
            speechSettings = root.optJSONObject("speechSettings")?.let(::decodeSpeechSettings)
                ?: SpeechSettings(),
        )
    }

    private fun encodeSpeechSettings(settings: SpeechSettings) = JSONObject()
        .put("enabled", settings.enabled)
        .put("model", settings.model.name)
        .put("sensitivity", settings.sensitivity.toDouble())
        .put("listenForIdentity", settings.listenForIdentity)
        .put("listenForPeople", settings.listenForPeople)
        .put("globalPhrases", JSONArray(settings.globalPhrases))

    private fun decodeSpeechSettings(json: JSONObject) = SpeechSettings(
        enabled = json.optBoolean("enabled", true),
        model = runCatching { SpeechModel.valueOf(json.optString("model")) }
            .getOrDefault(SpeechModel.TINY_EN),
        sensitivity = json.optDouble("sensitivity", 0.6).toFloat().coerceIn(0.4f, 0.95f),
        listenForIdentity = json.optBoolean("listenForIdentity", true),
        listenForPeople = json.optBoolean("listenForPeople", false),
        globalPhrases = json.textList("globalPhrases"),
    )

    private fun encodeIdentity(identity: UserIdentity) = JSONObject()
        .put("displayName", identity.displayName)
        .put("pronunciation", identity.pronunciation)
        .put("aliases", JSONArray(identity.aliases))
        .put("recognitionPhrases", JSONArray(identity.recognitionPhrases))
        .put("updatedAtEpochMs", identity.updatedAtEpochMs)

    private fun decodeIdentity(json: JSONObject) = UserIdentity(
        displayName = json.getString("displayName"),
        pronunciation = json.optString("pronunciation"),
        aliases = json.textList("aliases"),
        recognitionPhrases = json.textList("recognitionPhrases"),
        updatedAtEpochMs = json.optLong("updatedAtEpochMs", 0L),
    )

    private fun encodePerson(person: PersonMemory) = JSONObject()
        .put("id", person.id)
        .put("name", person.name)
        .put("relationship", person.relationship)
        .put("pronunciation", person.pronunciation)
        .put("aliases", JSONArray(person.aliases))
        .put("notes", person.notes)
        .put("updatedAtEpochMs", person.updatedAtEpochMs)

    private fun decodePerson(json: JSONObject) = PersonMemory(
        id = json.getString("id"),
        name = json.getString("name"),
        relationship = json.optString("relationship"),
        pronunciation = json.optString("pronunciation"),
        aliases = json.textList("aliases"),
        notes = json.optString("notes"),
        updatedAtEpochMs = json.optLong("updatedAtEpochMs", 0L),
    )

    private fun encodeContext(context: ContextMemory) = JSONObject()
        .put("id", context.id)
        .put("title", context.title)
        .put("details", context.details)
        .put("updatedAtEpochMs", context.updatedAtEpochMs)

    private fun decodeContext(json: JSONObject) = ContextMemory(
        id = json.getString("id"),
        title = json.getString("title"),
        details = json.getString("details"),
        updatedAtEpochMs = json.optLong("updatedAtEpochMs", 0L),
    )

    private fun JSONObject.textList(key: String): List<String> {
        val values = optJSONArray(key) ?: return emptyList()
        return buildList {
            for (index in 0 until values.length()) {
                values.optString(index).trim().takeIf(String::isNotEmpty)?.let(::add)
            }
        }
    }
}
