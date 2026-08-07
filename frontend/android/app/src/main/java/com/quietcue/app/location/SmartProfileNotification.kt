package com.quietcue.app.location

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.quietcue.app.MainActivity
import com.quietcue.app.R
import com.quietcue.app.data.SmartTransitionResult
import com.quietcue.app.data.SmartTransitionResultType

object SmartProfileNotification {
    private const val CHANNEL_ID = "quietcue_smart_profiles"

    fun show(context: Context, result: SmartTransitionResult, notificationKey: String) {
        if (result.type == SmartTransitionResultType.IGNORED) return
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Smart profile suggestions",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Profile suggestions when arriving at or leaving saved places"
            },
        )
        val openApp = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP,
            ),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle(result.title)
            .setContentText(result.message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(result.message))
            .setContentIntent(openApp)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()
        NotificationManagerCompat.from(context).notify(notificationKey.hashCode(), notification)
    }
}
