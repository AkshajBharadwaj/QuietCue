package com.quietcue.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.quietcue.app.ui.ProfileViewModel
import com.quietcue.app.ui.QuietCueApp
import com.quietcue.app.ui.theme.QuietCueTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
}
