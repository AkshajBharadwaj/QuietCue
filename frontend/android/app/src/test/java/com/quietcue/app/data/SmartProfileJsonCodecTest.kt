package com.quietcue.app.data

import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartPlace
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.domain.SmartProfileSuggestion
import org.junit.Assert.assertEquals
import org.junit.Test

class SmartProfileJsonCodecTest {
    @Test
    fun `smart profile state survives persistence round trip`() {
        val place = SmartPlace(
            id = "work-place",
            name = "Work",
            latitude = 37.3317,
            longitude = -122.0307,
            radiusMeters = 200f,
            profileId = "builtin-work-school",
            autoApply = true,
        )
        val state = SmartProfileState(
            places = listOf(place),
            suggestion = SmartProfileSuggestion(
                id = "suggestion-1",
                placeId = place.id,
                placeName = place.name,
                targetProfileId = place.profileId,
                targetProfileName = "Work / School",
                transition = PlaceTransition.ENTER,
                createdAtEpochMs = 123_456L,
                previousProfileId = "builtin-home",
                simulated = true,
            ),
            manualOverrideUntilEpochMs = 500_000L,
            activePlaceId = place.id,
            returnProfileId = "builtin-home",
            lastTransitionKey = "work-place:ENTER",
            lastTransitionAtEpochMs = 123_456L,
            statusMessage = "Arrival detected",
        )

        val restored = SmartProfileJsonCodec.decode(SmartProfileJsonCodec.encode(state))

        assertEquals(state, restored)
    }

    @Test
    fun `blank state restores safe defaults`() {
        assertEquals(SmartProfileState(), SmartProfileJsonCodec.decode(""))
    }

    @Test
    fun `older place data defaults to ask before switching`() {
        val restored = SmartProfileJsonCodec.decode(
            """{"places":[{"id":"home","name":"Home","latitude":1,"longitude":2,"profileId":"builtin-home"}]}""",
        )

        assertEquals(false, restored.places.single().autoApply)
        assertEquals(false, restored.places.single().demoOnly)
        assertEquals(15f, restored.places.single().radiusMeters)
    }
}
