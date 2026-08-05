package com.quietcue.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.LocalProfileTextAgent
import com.quietcue.app.domain.ProfileAgentResult
import com.quietcue.app.domain.SoundDefinition

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileAgentScreen(
    activeProfile: AlertProfile,
    soundLibrary: List<SoundDefinition>,
    onBack: () -> Unit,
    onReview: (AlertProfile) -> Unit,
) {
    val agent = remember { LocalProfileTextAgent() }
    var prompt by rememberSaveable { mutableStateOf("") }
    var result by remember { mutableStateOf<ProfileAgentResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    BackHandler(onBack = onBack)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profile assistant") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Go back")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = 20.dp,
                top = padding.calculateTopPadding() + 12.dp,
                end = 20.dp,
                bottom = padding.calculateBottomPadding() + 28.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Describe the situation", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "QuietCue creates a constrained profile draft from your words. Nothing is saved or activated until you review it.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            item {
                OutlinedTextField(
                    value = prompt,
                    onValueChange = { prompt = it.take(500); result = null; error = null },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Where are you going and what matters?") },
                    placeholder = {
                        Text("I'm studying in a crowded library. Ignore phones, alert me to fire alarms and my name, Akshaj.")
                    },
                    minLines = 6,
                    supportingText = { Text("${prompt.length}/500 • processed locally") },
                    isError = error != null,
                )
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
            item {
                Button(
                    onClick = {
                        runCatching { agent.generate(prompt, activeProfile, soundLibrary) }
                            .onSuccess { result = it; error = null }
                            .onFailure { error = it.message ?: "Could not create a profile" }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = prompt.isNotBlank(),
                ) {
                    Icon(Icons.Rounded.AutoAwesome, contentDescription = null)
                    Text(" Create draft")
                }
            }
            result?.let { generated ->
                item {
                    Card {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Text(generated.profile.name, style = MaterialTheme.typography.titleLarge)
                            Text(generated.explanation)
                            Text("Assumptions", style = MaterialTheme.typography.titleSmall)
                            generated.assumptions.forEach { Text("• $it") }
                            Button(
                                onClick = { onReview(generated.profile) },
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Text("Review every setting")
                            }
                        }
                    }
                }
            }
        }
    }
}
