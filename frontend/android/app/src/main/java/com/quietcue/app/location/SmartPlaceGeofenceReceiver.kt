package com.quietcue.app.location

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.quietcue.app.data.ProfileRepository
import com.quietcue.app.data.SmartProfileCoordinator
import com.quietcue.app.data.SmartProfileRepository
import com.quietcue.app.domain.PlaceTransition
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SmartPlaceGeofenceReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) return
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
                val coordinator = SmartProfileCoordinator(
                    ProfileRepository(applicationContext),
                    SmartProfileRepository(applicationContext),
                )
                placeIds.forEach { placeId ->
                    val result = coordinator.handleTransition(placeId, transition)
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
}
