package com.quietcue.app.data

import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.ProfileDefaults
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
}
