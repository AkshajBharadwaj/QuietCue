package com.quietcue.app.data

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
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
        if (!hasNotificationPermission()) return
        ensureChannel()

        val contentTitle = context.getString(
            R.string.alert_notification_title,
            alert.displayName,
        )
        val contentText = buildContentText(alert)
        val style = NotificationCompat.BigTextStyle()
            .bigText(contentText)

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(contentTitle)
            .setContentText(contentText)
            .setStyle(style)
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
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        notificationManager.notify(alert.notificationId(), notification)
    }

    private fun hasNotificationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
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

    private fun DetectedAlert.notificationId(): Int = eventId.hashCode()

    companion object {
        const val CHANNEL_ID = "quietcue_alerts"
    }
}
