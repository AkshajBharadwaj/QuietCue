package com.quietcue.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quietcue.app.phone.PhoneInferenceService
import com.quietcue.app.ui.ProfileViewModel
import com.quietcue.app.ui.QuietCueApp
import com.quietcue.app.ui.theme.QuietCueTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startPhoneInference(intent)
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
        enableEdgeToEdge()
        setContent {
            QuietCueTheme {
                val profileViewModel: ProfileViewModel = viewModel(
                    factory = ProfileViewModel.factory(applicationContext),
                )
                QuietCueApp(viewModel = profileViewModel)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        startPhoneInference(intent)
    }

    private fun startPhoneInference(sourceIntent: Intent?) {
        val serviceIntent = Intent(this, PhoneInferenceService::class.java)
        sourceIntent?.getStringExtra(PhoneInferenceService.EXTRA_PAIRING_TOKEN)?.let { token ->
            serviceIntent.putExtra(PhoneInferenceService.EXTRA_PAIRING_TOKEN, token)
        }
        ContextCompat.startForegroundService(this, serviceIntent)
    }
}
