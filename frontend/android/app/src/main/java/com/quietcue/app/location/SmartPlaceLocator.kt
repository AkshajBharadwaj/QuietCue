package com.quietcue.app.location

import com.quietcue.app.domain.SmartPlace
import kotlin.math.PI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/** Pure location math used by foreground reconciliation and unit tests. */
object SmartPlaceLocator {
    fun containingPlace(
        places: List<SmartPlace>,
        latitude: Double,
        longitude: Double,
    ): SmartPlace? = places
        .asSequence()
        .filter { it.enabled && !it.demoOnly }
        .map { it to distanceMeters(latitude, longitude, it.latitude, it.longitude) }
        .filter { (place, distance) -> distance <= place.radiusMeters }
        .minByOrNull { (_, distance) -> distance }
        ?.first

    fun distanceMeters(
        firstLatitude: Double,
        firstLongitude: Double,
        secondLatitude: Double,
        secondLongitude: Double,
    ): Double {
        val firstLat = firstLatitude.radians()
        val secondLat = secondLatitude.radians()
        val latitudeDelta = (secondLatitude - firstLatitude).radians()
        val longitudeDelta = (secondLongitude - firstLongitude).radians()
        val haversine = sin(latitudeDelta / 2) * sin(latitudeDelta / 2) +
            cos(firstLat) * cos(secondLat) *
            sin(longitudeDelta / 2) * sin(longitudeDelta / 2)
        return EARTH_RADIUS_METERS * 2 * atan2(
            sqrt(haversine.coerceIn(0.0, 1.0)),
            sqrt((1 - haversine).coerceAtLeast(0.0)),
        )
    }

    private fun Double.radians(): Double = this * PI / 180.0

    private const val EARTH_RADIUS_METERS = 6_371_000.0
}
