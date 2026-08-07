package com.quietcue.app.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.quietcue.app.R
import com.quietcue.app.data.ProfileRepository
import com.quietcue.app.data.MemoryRepository
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.ProfileDefaults
import com.quietcue.app.domain.SpeechModel
import com.quietcue.app.phone.speech.PhoneTranscriber
import com.quietcue.app.phone.speech.SpeechGate
import com.quietcue.app.phone.speech.WhisperOnnxTranscriber
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class PhoneInferenceService : Service() {
    private val executor = Executors.newSingleThreadExecutor()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val activeProfile = AtomicReference<AlertProfile>(ProfileDefaults.all().first())
    private val memoryBank = AtomicReference(MemoryBank())
    @Volatile private var classifier: PhoneYamnetClassifier? = null
    @Volatile private var transcriber: PhoneTranscriber? = null
    @Volatile private var server: PhoneInferenceServer? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startInForeground("Loading the on-phone sound model")
        val repository = ProfileRepository(applicationContext)
        val memoryRepository = MemoryRepository(applicationContext)
        scope.launch {
            repository.catalog.collectLatest { catalog ->
                catalog.activeProfile?.let(activeProfile::set)
            }
        }
        scope.launch {
            memoryRepository.bank.collectLatest(memoryBank::set)
        }
        executor.execute {
            try {
                val loadedClassifier = PhoneYamnetClassifier(applicationContext)
                classifier = loadedClassifier
                val preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE)
                val speechGate = SpeechGate(
                    transcriberFactory = { model: SpeechModel ->
                        WhisperOnnxTranscriber(applicationContext, model).also { loaded ->
                            transcriber = loaded
                            PhoneInferenceStatus.update {
                                it.copy(speechModelLoaded = true, speechError = null)
                            }
                        }
                    },
                )
                val loadedServer = PhoneInferenceServer(
                    classifier = loadedClassifier,
                    profileProvider = activeProfile::get,
                    memoryBankProvider = memoryBank::get,
                    speechGate = speechGate,
                    pairingToken = preferences.getString(PAIRING_TOKEN, "").orEmpty(),
                )
                server = loadedServer
                updateNotification("Listening on TCP ${PhoneInferenceServer.DEFAULT_PORT} • ${loadedClassifier.provider}")
                loadedServer.serveForever()
            } catch (error: Throwable) {
                PhoneInferenceStatus.update {
                    it.copy(
                        running = false,
                        modelReady = false,
                        error = "${error.javaClass.simpleName}: ${error.message}",
                    )
                }
                updateNotification("Inference server failed: ${error.message}")
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        server?.close()
        transcriber = null
        classifier?.close()
        scope.cancel()
        executor.shutdownNow()
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Phone inference server",
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun startInForeground(message: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification(message),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification(message))
        }
    }

    private fun updateNotification(message: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(message))
    }

    private fun notification(message: String): Notification = NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.drawable.ic_launcher)
        .setContentTitle("QuietCue phone inference")
        .setContentText(message)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .build()

    companion object {
        private const val CHANNEL_ID = "quietcue_phone_inference"
        private const val NOTIFICATION_ID = 2101
        private const val PREFERENCES = "quietcue_inference"
        private const val PAIRING_TOKEN = "pairing_token"
    }
}
