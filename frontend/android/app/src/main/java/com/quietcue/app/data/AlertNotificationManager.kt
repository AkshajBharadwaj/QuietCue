package com.quietcue.app.data

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.quietcue.app.MainActivity
import com.quietcue.app.R
import com.quietcue.app.domain.DetectedAlert

class AlertNotificationManager(private val context: Context) {
    private val notificationManager =
        NotificationManagerCompat.from(context.applicationContext)

    fun ensureChannel() {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return

        val channel = NotificationChannel(
            CHANNEL_ID,
            context.getString(R.string.alert_notification_channel_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = context.getString(R.string.alert_notification_channel_description)
            enableVibration(true)
            enableLights(true)
            setShowBadge(true)
        }
        manager.createNotificationChannel(channel)
    }

    fun notify(alert: DetectedAlert) {
        if (
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        ensureChannel()

        val contentTitle = context.getString(
            R.string.alert_notification_title,
            alert.displayName,
        )
        val contentText = buildContentText(alert)
        val style = NotificationCompat.BigTextStyle()
            .bigText(contentText)
        val contentIntent = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
            ),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(contentTitle)
            .setContentText(contentText)
            .setStyle(style)
            .setContentIntent(contentIntent)
            .setCategory(
                if (alert.requiresAcknowledgement || alert.category == "emergency") {
                    NotificationCompat.CATEGORY_ALARM
                } else {
                    NotificationCompat.CATEGORY_STATUS
                },
            )
            .setPriority(
                if (alert.requiresAcknowledgement || alert.category == "emergency") {
                    NotificationCompat.PRIORITY_HIGH
                } else {
                    NotificationCompat.PRIORITY_DEFAULT
                },
            )
            .setAutoCancel(!alert.hapticActive)
            .setOngoing(alert.hapticActive)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        if (alert.hapticActive) {
            val stopIntent = Intent(context, AlertAcknowledgeReceiver::class.java)
                .setAction(AlertAcknowledgeReceiver.ACTION_STOP_HAPTIC)
                .putExtra(AlertAcknowledgeReceiver.EXTRA_EVENT_ID, alert.eventId)
            val stopPendingIntent = PendingIntent.getBroadcast(
                context,
                notificationId(alert.eventId),
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            builder.addAction(
                R.drawable.ic_launcher,
                context.getString(R.string.alert_notification_stop_action),
                stopPendingIntent,
            )
        }

        notificationManager.notify(notificationId(alert.eventId), builder.build())
    }

    fun cancel(eventId: String) {
        notificationManager.cancel(notificationId(eventId))
    }

    fun cancelAllAlerts() {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.activeNotifications
            .filter { it.notification.channelId == CHANNEL_ID }
            .forEach { manager.cancel(it.id) }
    }

    private fun buildContentText(alert: DetectedAlert): String {
        val confidence = (alert.confidence * 100).toInt()
        val urgency = when (alert.category) {
            "emergency" -> "Emergency"
            "attention" -> "Attention"
            else -> "Informational"
        }
        return "$urgency alert in ${alert.profileName} • $confidence% confidence • ${alert.totalLatencyMs} ms"
    }

    companion object {
        const val CHANNEL_ID = "quietcue_alerts"

        fun notificationId(eventId: String): Int = eventId.hashCode()
    }
}
