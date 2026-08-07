package com.quietcue.app.location

import com.quietcue.app.domain.SmartPlace
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SmartPlaceLocatorTest {
    @Test
    fun `finds enabled real place containing current location`() {
        val nearby = place("nearby", 37.7749, -122.4194, 100f)
        val far = place("far", 37.7849, -122.4194, 100f)

        val match = SmartPlaceLocator.containingPlace(
            listOf(far, nearby),
            latitude = 37.77495,
            longitude = -122.4194,
        )

        assertEquals("nearby", match?.id)
    }

    @Test
    fun `ignores demo and disabled places during real reconciliation`() {
        val disabled = place("disabled", 37.7749, -122.4194, 100f).copy(enabled = false)
        val demo = place("demo", 37.7749, -122.4194, 100f).copy(demoOnly = true)

        assertNull(
            SmartPlaceLocator.containingPlace(
                listOf(disabled, demo),
                latitude = 37.7749,
                longitude = -122.4194,
            ),
        )
    }

    @Test
    fun `distance calculation is accurate enough for geofence radii`() {
        val distance = SmartPlaceLocator.distanceMeters(
            37.7749,
            -122.4194,
            37.7758,
            -122.4194,
        )

        assertTrue(distance in 99.0..102.0)
    }

    private fun place(
        id: String,
        latitude: Double,
        longitude: Double,
        radius: Float,
    ) = SmartPlace(
        id = id,
        name = id,
        latitude = latitude,
        longitude = longitude,
        radiusMeters = radius,
        profileId = "profile",
    )
}
