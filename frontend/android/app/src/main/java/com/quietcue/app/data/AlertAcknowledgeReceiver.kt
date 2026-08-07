package com.quietcue.app.data

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class AlertAcknowledgeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_STOP_HAPTIC) return
        val eventId = intent.getStringExtra(EXTRA_EVENT_ID)?.takeIf(String::isNotBlank) ?: return
        val pendingResult = goAsync()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        scope.launch {
            try {
                AlertRepository().stopHaptic(eventId)
                AlertNotificationManager(context.applicationContext).cancel(eventId)
            } catch (error: Exception) {
                Log.w(TAG, "Could not stop haptic for $eventId", error)
            } finally {
                pendingResult.finish()
                scope.cancel()
            }
        }
    }

    companion object {
        const val ACTION_STOP_HAPTIC = "com.quietcue.app.action.STOP_HAPTIC"
        const val EXTRA_EVENT_ID = "event_id"
        private const val TAG = "QuietCueAlert"
    }
}
