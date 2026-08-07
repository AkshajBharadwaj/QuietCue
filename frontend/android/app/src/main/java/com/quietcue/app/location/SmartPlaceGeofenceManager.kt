package com.quietcue.app.location

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.google.android.gms.common.ConnectionResult
import com.google.android.gms.common.GoogleApiAvailability
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.tasks.Task
import com.quietcue.app.data.SmartProfileRepository
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

enum class GeofenceRegistrationStatus {
    ACTIVE,
    NO_PLACES,
    PERMISSION_REQUIRED,
    PLAY_SERVICES_UNAVAILABLE,
    REGISTRATION_FAILED,
}

class SmartPlaceGeofenceManager(
    context: Context,
    private val repository: SmartProfileRepository = SmartProfileRepository(context.applicationContext),
) {
    private val applicationContext = context.applicationContext
    private val client = LocationServices.getGeofencingClient(applicationContext)

    val pendingIntent: PendingIntent by lazy {
        PendingIntent.getBroadcast(
            applicationContext,
            REQUEST_CODE,
            Intent(applicationContext, SmartPlaceGeofenceReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    @SuppressLint("MissingPermission")
    suspend fun refresh(): GeofenceRegistrationStatus {
        if (!SmartPlacePermissions.canMonitorGeofences(applicationContext)) {
            return GeofenceRegistrationStatus.PERMISSION_REQUIRED
        }
        if (
            GoogleApiAvailability.getInstance().isGooglePlayServicesAvailable(applicationContext) !=
            ConnectionResult.SUCCESS
        ) {
            return GeofenceRegistrationStatus.PLAY_SERVICES_UNAVAILABLE
        }

        val places = repository.current().places.filter { it.enabled && !it.demoOnly }
        runCatching { client.removeGeofences(pendingIntent).awaitTask() }
        if (places.isEmpty()) return GeofenceRegistrationStatus.NO_PLACES

        val geofences = places.map { place ->
            Geofence.Builder()
                .setRequestId(place.id)
                .setCircularRegion(place.latitude, place.longitude, place.radiusMeters)
                .setExpirationDuration(Geofence.NEVER_EXPIRE)
                .setTransitionTypes(
                    Geofence.GEOFENCE_TRANSITION_ENTER or Geofence.GEOFENCE_TRANSITION_EXIT,
                )
                .build()
        }
        val request = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(geofences)
            .build()
        client.addGeofences(request, pendingIntent).awaitTask()
        return GeofenceRegistrationStatus.ACTIVE
    }

    companion object {
        private const val REQUEST_CODE = 7301
    }
}

private suspend fun <T> Task<T>.awaitTask(): T = suspendCoroutine { continuation ->
    addOnSuccessListener(continuation::resume)
    addOnFailureListener(continuation::resumeWithException)
}
