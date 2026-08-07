package com.quietcue.app.location

import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
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
        val location = suspendCoroutine { continuation ->
            client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
                .addOnSuccessListener { value ->
                    if (value == null) {
                        continuation.resumeWithException(
                            IllegalStateException("Current location is unavailable. Turn on location and try again."),
                        )
                    } else {
                        continuation.resume(value)
                    }
                }
                .addOnFailureListener(continuation::resumeWithException)
        }
        return CapturedPlaceLocation(location.latitude, location.longitude)
    }
}
