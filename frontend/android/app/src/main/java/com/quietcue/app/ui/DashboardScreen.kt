package com.quietcue.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.NotificationsNone
import androidx.compose.material.icons.rounded.Watch
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.SoundDiscoveryCandidate
import com.quietcue.app.phone.PhoneInferenceServerState

@Composable
fun DashboardScreen(
    catalog: ProfileCatalog,
    runtimeState: RuntimeState,
    phoneInferenceState: PhoneInferenceServerState,
    contentPadding: PaddingValues,
    onTeachDiscovery: (SoundDiscoveryCandidate) -> Unit,
    onAddDiscovery: (SoundDiscoveryCandidate) -> Unit,
    onDismissDiscovery: (String) -> Unit,
) {
    val profile = catalog.activeProfile
    var addCandidate by remember { mutableStateOf<SoundDiscoveryCandidate?>(null) }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = 20.dp,
            top = contentPadding.calculateTopPadding() + 12.dp,
            end = 20.dp,
            bottom = contentPadding.calculateBottomPadding() + 24.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text("Good to see you", style = MaterialTheme.typography.headlineMedium)
            Text(
                "QuietCue is ready to show the alerts that matter.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (profile != null) {
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = profile.color.color(),
                        contentColor = androidx.compose.ui.graphics.Color.White,
                    ),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(20.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Surface(
                            modifier = Modifier.size(52.dp),
                            shape = CircleShape,
                            color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.18f),
                        ) {
                            Icon(
                                profile.icon.imageVector(),
                                contentDescription = null,
                                modifier = Modifier.padding(13.dp),
                            )
                        }
                        Column(Modifier.weight(1f)) {
                            Text("Active profile", style = MaterialTheme.typography.labelLarge)
                            Text(profile.name, style = MaterialTheme.typography.headlineSmall)
                            Text("${profile.enabledSoundCount} sounds monitored")
                        }
                    }
                }
            }
        }

        if (runtimeState.discoveries.isNotEmpty()) {
            item { SectionTitle("Sound Scout") }
            items(
                count = runtimeState.discoveries.take(3).size,
                key = { index -> runtimeState.discoveries[index].id },
            ) { index ->
                val candidate = runtimeState.discoveries[index]
                DiscoveryCard(
                    candidate = candidate,
                    profileName = profile?.name ?: "active profile",
                    onAdd = { addCandidate = candidate },
                    onTeach = { onTeachDiscovery(candidate) },
                    onDismiss = { onDismissDiscovery(candidate.id) },
                )
            }
        }

        item { SectionTitle("System status") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusRow(Icons.Rounded.Hearing, "Phone app", "Profile controls available", true)
                StatusRow(
                    Icons.Rounded.Hearing,
                    "Phone inference server",
                    when {
                        phoneInferenceState.error != null -> phoneInferenceState.error
                        phoneInferenceState.clientConnected -> {
                            "UNO Q connected • ${phoneInferenceState.provider}" +
                                (phoneInferenceState.inferenceMs?.let { " • ${it.toInt()} ms" } ?: "")
                        }
                        phoneInferenceState.modelReady -> {
                            "Listening on TCP ${phoneInferenceState.port} • ${phoneInferenceState.provider}"
                        }
                        else -> "Loading the quantized sound model"
                    },
                    phoneInferenceState.running && phoneInferenceState.modelReady,
                )
                StatusRow(
                    Icons.Rounded.CloudOff,
                    "Inference hub",
                    if (runtimeState.backendConnected) {
                        "Connected • ${runtimeState.backendProfileName ?: "Profile unavailable"}"
                    } else {
                        "Run the local QuietCue hub"
                    },
                    runtimeState.backendConnected,
                )
                StatusRow(
                    Icons.Rounded.Watch,
                    "Audio source",
                    if (phoneInferenceState.clientConnected) {
                        "UNO Q microphone stream connected to this phone"
                    } else if (runtimeState.audioSourceConnected) {
                        "WAV replay or Uno Q stream connected"
                    } else {
                        "Waiting for replay or microphone stream"
                    },
                    runtimeState.audioSourceConnected || phoneInferenceState.clientConnected,
                )
            }
        }

        item { SectionTitle("Latest alert") }
        item {
            Card {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    val alert = runtimeState.latestAlert
                    Icon(
                        if (alert == null) Icons.Rounded.NotificationsNone else Icons.Rounded.NotificationsActive,
                        contentDescription = null,
                        modifier = Modifier.size(32.dp),
                        tint = if (alert == null) {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        } else {
                            MaterialTheme.colorScheme.primary
                        },
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        if (alert == null) {
                            Text("No alerts yet", style = MaterialTheme.typography.titleMedium)
                            Text(
                                "Replay a WAV to show confidence, latency, and haptic output here.",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            Text(alert.displayName, style = MaterialTheme.typography.titleMedium)
                            Text(
                                "${(alert.confidence * 100).toInt()}% • ${alert.category.replaceFirstChar(Char::uppercase)} • ${alert.profileName}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                "${alert.totalLatencyMs} ms • ${alert.pattern.replace('_', ' ')}" +
                                    when {
                                        alert.fallbackToPhone -> " • check phone for details"
                                        alert.simulated -> " • awaiting haptic delivery"
                                        else -> " • delivered to wearable"
                                    },
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }

    addCandidate?.let { candidate ->
        val suggestedThreshold = ((candidate.meanConfidence - 0.10f).coerceIn(0.35f, 0.80f) * 100).toInt()
        AlertDialog(
            onDismissRequest = { addCandidate = null },
            title = { Text("Add ${candidate.label}?") },
            text = {
                Text(
                    "QuietCue will add it to ${profile?.name ?: "the active profile"} as an " +
                        "informational two-pulse alert with a $suggestedThreshold% threshold and " +
                        "30-second cooldown. Other profiles will keep it disabled.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onAddDiscovery(candidate)
                        addCandidate = null
                    },
                ) { Text("Add sound") }
            },
            dismissButton = {
                TextButton(onClick = { addCandidate = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun DiscoveryCard(
    candidate: SoundDiscoveryCandidate,
    profileName: String,
    onAdd: () -> Unit,
    onTeach: () -> Unit,
    onDismiss: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(Icons.Rounded.AutoAwesome, contentDescription = null)
                Column(Modifier.weight(1f)) {
                    Text("Recurring sound found", style = MaterialTheme.typography.labelLarge)
                    Text(candidate.label, style = MaterialTheme.typography.titleLarge)
                }
                Icon(Icons.Rounded.GraphicEq, contentDescription = null)
            }
            Text(
                "Heard in ${candidate.episodes} separate episodes • " +
                    "${(candidate.meanConfidence * 100).toInt()}% average confidence",
                color = MaterialTheme.colorScheme.onSecondaryContainer,
            )
            if (candidate.profileNames.isNotEmpty()) {
                Text(
                    "Seen while ${candidate.profileNames.joinToString()} was active. " +
                        "QuietCue does not have a configured rule for it yet.",
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
            Button(onClick = onAdd, modifier = Modifier.fillMaxWidth()) {
                Text("Add to $profileName")
            }
            OutlinedButton(onClick = onTeach, modifier = Modifier.fillMaxWidth()) {
                Text("Teach QuietCue this sound")
            }
            OutlinedButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
                Text("Ignore suggestion")
            }
        }
    }
}

@Composable
private fun StatusRow(icon: ImageVector, title: String, status: String, connected: Boolean) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(icon, contentDescription = null)
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall)
                Text(status, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(
                Modifier
                    .size(12.dp)
                    .background(
                        if (connected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                        CircleShape,
                    ),
            )
        }
    }
}

@Composable
fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleLarge)
}
