package com.quietcue.app.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.quietcue.app.data.AlertRepository
import com.quietcue.app.data.MemoryRepository
import com.quietcue.app.data.ProfileRepository
import com.quietcue.app.data.SmartProfileCoordinator
import com.quietcue.app.data.SmartProfileRepository
import com.quietcue.app.data.SmartTransitionResultType
import com.quietcue.app.domain.PlaceTransition
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class SmartPlaceGeofenceReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) {
            Log.w(TAG, "Geofence callback failed with code ${event.errorCode}")
            return
        }
        val transition = when (event.geofenceTransition) {
            Geofence.GEOFENCE_TRANSITION_ENTER -> PlaceTransition.ENTER
            Geofence.GEOFENCE_TRANSITION_EXIT -> PlaceTransition.EXIT
            else -> return
        }
        val placeIds = event.triggeringGeofences?.map { it.requestId }.orEmpty()
        if (placeIds.isEmpty()) return

        val pending = goAsync()
        val applicationContext = context.applicationContext
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val profileRepository = ProfileRepository(applicationContext)
                val smartRepository = SmartProfileRepository(applicationContext)
                val coordinator = SmartProfileCoordinator(profileRepository, smartRepository)
                placeIds.forEach { placeId ->
                    val result = coordinator.handleTransition(placeId, transition)
                    if (result.type == SmartTransitionResultType.ACTIVATED) {
                        runCatching {
                            AlertRepository().syncProfile(
                                profileRepository.catalog.first(),
                                MemoryRepository(applicationContext).bank.first(),
                            )
                        }.onFailure { error ->
                            Log.w(TAG, "Could not sync the automatically activated profile", error)
                        }
                    }
                    Log.i(TAG, "$placeId ${transition.name}: ${result.type}")
                    SmartProfileNotification.show(
                        applicationContext,
                        result,
                        "$placeId:${transition.name}",
                    )
                }
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        private const val TAG = "QuietCuePlaces"
    }
}
