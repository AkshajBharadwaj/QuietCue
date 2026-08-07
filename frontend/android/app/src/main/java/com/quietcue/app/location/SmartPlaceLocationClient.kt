package com.quietcue.app.location

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.Task
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

data class CapturedPlaceLocation(
    val latitude: Double,
    val longitude: Double,
)

class SmartPlaceLocationClient(context: Context) {
    private val applicationContext = context.applicationContext
    private val client = LocationServices.getFusedLocationProviderClient(applicationContext)

    @SuppressLint("MissingPermission")
    suspend fun captureCurrentLocation(): CapturedPlaceLocation {
        require(SmartPlacePermissions.hasPreciseLocation(applicationContext)) {
            "Precise location permission is required to save this place"
        }
        val request = CurrentLocationRequest.Builder()
            .setPriority(Priority.PRIORITY_HIGH_ACCURACY)
            .setMaxUpdateAgeMillis(MAX_CURRENT_AGE_MS)
            .setDurationMillis(LOCATION_TIMEOUT_MS)
            .build()
        val current = runCatching { client.getCurrentLocation(request, null).awaitLocation() }
            .getOrNull()
        val last = if (current == null) {
            runCatching { client.lastLocation.awaitLocation() }.getOrNull()?.takeIf {
                System.currentTimeMillis() - it.time in 0..MAX_FALLBACK_AGE_MS
            }
        } else {
            null
        }
        val location = current ?: last ?: throw IllegalStateException(
            "Current location is unavailable. Turn on location, wait for a fresh fix, and try again.",
        )
        return CapturedPlaceLocation(location.latitude, location.longitude)
    }

    companion object {
        private const val MAX_CURRENT_AGE_MS = 2 * 60 * 1_000L
        private const val MAX_FALLBACK_AGE_MS = 15 * 60 * 1_000L
        private const val LOCATION_TIMEOUT_MS = 12_000L
    }
}

private suspend fun Task<Location>.awaitLocation(): Location? = suspendCoroutine { continuation ->
    addOnSuccessListener(continuation::resume)
    addOnFailureListener(continuation::resumeWithException)
}
