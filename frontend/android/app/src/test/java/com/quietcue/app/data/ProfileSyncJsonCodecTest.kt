package com.quietcue.app.data

import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.HapticStrength
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.SoundLibrary
import com.quietcue.app.domain.UserIdentity
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileSyncJsonCodecTest {
    @Test
    fun `sync includes only manually stored speech context`() {
        val profiles = ProfileDefaults.all()
        val catalog = ProfileCatalog(profiles, ProfileDefaults.HOME_ID)
        val bank = MemoryBank(
            identity = UserIdentity("Akshaj", "Ak-shudge", listOf("Ak"), listOf("Hey oxides"), 1),
            people = listOf(PersonMemory("p1", "Maya", "Sister", updatedAtEpochMs = 2)),
            contexts = listOf(ContextMemory("c1", "Tuesday class", "Building 4", 3)),
        )

        val context = JSONObject(ProfileSyncJsonCodec.encode(catalog, bank)).getJSONObject("speech_context")

        assertEquals("Akshaj", context.getJSONObject("identity").getString("name"))
        assertEquals("Maya", context.getJSONArray("people").getJSONObject(0).getString("name"))
        assertEquals("Building 4", context.getJSONArray("contexts").getJSONObject(0).getString("details"))
        assertFalse(context.has("suggestions"))
        val emptyContext = JSONObject(ProfileSyncJsonCodec.encode(catalog)).getJSONObject("speech_context")
        assertFalse(emptyContext.has("identity"))
        assertEquals(0, emptyContext.getJSONArray("people").length())
        assertEquals(0, emptyContext.getJSONArray("contexts").length())
    }

    @Test
    fun `sync includes approved classifier label rules`() {
        val sound = SoundDefinition(
            id = "custom:label:vacuum",
            displayName = "Vacuum cleaner",
            description = "Found by Sound Scout",
            defaultPriority = AlertPriority.INFORMATIONAL,
            defaultHapticPattern = HapticPattern.TWO_SHORT,
            defaultHapticStrength = HapticStrength.GENTLE,
            classifierLabels = listOf("Vacuum cleaner"),
        )
        val library = SoundLibrary.complete(listOf(sound))
        val profiles = ProfileDefaults.all().map { profile ->
            profile.copy(soundRules = ProfileDefaults.completeRules(profile.soundRules, library))
        }
        val catalog = ProfileCatalog(profiles, ProfileDefaults.HOME_ID, library)

        val document = JSONObject(ProfileSyncJsonCodec.encode(catalog))
        val rule = document.getJSONArray("classifier_label_rules").getJSONObject(0)

        assertEquals(sound.id, rule.getString("event"))
        assertEquals("Vacuum cleaner", rule.getString("label"))
    }
}
