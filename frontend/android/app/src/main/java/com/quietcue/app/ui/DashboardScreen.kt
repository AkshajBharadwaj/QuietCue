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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CloudOff
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.LocationOn
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.NotificationsNone
import androidx.compose.material.icons.rounded.Watch
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.InferenceDevice
import com.quietcue.app.domain.RuntimeState
import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.phone.PhoneInferenceServerState

@Composable
fun DashboardScreen(
    catalog: ProfileCatalog,
    runtimeState: RuntimeState,
    smartProfileState: SmartProfileState,
    phoneInferenceState: PhoneInferenceServerState,
    contentPadding: PaddingValues,
    onAcceptSmartSuggestion: () -> Unit,
    onAlwaysSmartSuggestion: () -> Unit,
    onDismissSmartSuggestion: () -> Unit,
    onInferenceDeviceSelected: (InferenceDevice) -> Unit,
    onStopHaptic: (String) -> Unit,
) {
    val profile = catalog.activeProfile
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

        smartProfileState.suggestion?.let { suggestion ->
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.tertiaryContainer,
                    ),
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Icon(Icons.Rounded.LocationOn, contentDescription = null)
                            Column(Modifier.weight(1f)) {
                                Text(
                                    if (suggestion.transition == PlaceTransition.ENTER) {
                                        "You arrived at ${suggestion.placeName}"
                                    } else {
                                        "You left ${suggestion.placeName}"
                                    },
                                    style = MaterialTheme.typography.titleMedium,
                                )
                                Text(
                                    "Switch to ${suggestion.targetProfileName}?" +
                                        if (suggestion.simulated) " • demo event" else "",
                                )
                            }
                        }
                        Button(onClick = onAcceptSmartSuggestion, modifier = Modifier.fillMaxWidth()) {
                            Text("Switch to ${suggestion.targetProfileName}")
                        }
                        if (suggestion.transition == PlaceTransition.ENTER) {
                            OutlinedButton(onClick = onAlwaysSmartSuggestion, modifier = Modifier.fillMaxWidth()) {
                                Text("Always switch here")
                            }
                        }
                        TextButton(onClick = onDismissSmartSuggestion, modifier = Modifier.fillMaxWidth()) {
                            Text("Not now")
                        }
                    }
                }
            }
        }

        item { SectionTitle("System status") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusRow(Icons.Rounded.Hearing, "Phone app", "Profile controls available", true)
                InferenceDeviceCard(
                    runtimeState = runtimeState,
                    phoneInferenceState = phoneInferenceState,
                    onSelected = onInferenceDeviceSelected,
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
                    Icons.Rounded.GraphicEq,
                    "Speech and name detection",
                    when {
                        phoneInferenceState.speechError != null -> phoneInferenceState.speechError
                        phoneInferenceState.speechPending -> "Transcribing locally…"
                        phoneInferenceState.speechListening -> "Listening for configured phrases"
                        phoneInferenceState.speechModelLoaded -> {
                            "Model ready" + (phoneInferenceState.speechInferenceMs?.let { " • last decode ${it.toInt()} ms" } ?: "")
                        }
                        else -> "Loads only when an enabled profile hears speech"
                    },
                    phoneInferenceState.speechModelLoaded && phoneInferenceState.speechError == null,
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
                            if (alert.hapticActive) {
                                Spacer(Modifier.height(8.dp))
                                Button(
                                    onClick = { onStopHaptic(alert.eventId) },
                                    enabled = !runtimeState.stopInProgress && runtimeState.backendConnected,
                                ) {
                                    Text(
                                        if (runtimeState.stopInProgress) {
                                            "Stopping…"
                                        } else if (alert.requiresAcknowledgement) {
                                            "Acknowledge & stop vibration"
                                        } else {
                                            "Stop vibration"
                                        },
                                    )
                                }
                            } else if (alert.acknowledgedAtMs != null) {
                                Text(
                                    "Vibration stopped",
                                    color = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

}

@Composable
private fun InferenceDeviceCard(
    runtimeState: RuntimeState,
    phoneInferenceState: PhoneInferenceServerState,
    onSelected: (InferenceDevice) -> Unit,
) {
    val requested = runtimeState.requestedInferenceDevice
    val active = runtimeState.activeInferenceDevice
    val status = when {
        runtimeState.inferenceRoutingError != null -> runtimeState.inferenceRoutingError
        runtimeState.inferenceSwitchPending -> {
            "Switching to ${requested.displayName} • ${active.displayName} is handling audio"
        }
        active == InferenceDevice.SAMSUNG_PHONE -> {
            "Samsung Galaxy • ${phoneInferenceState.provider}" +
                (phoneInferenceState.inferenceMs?.let { " • ${it.toInt()} ms" } ?: "")
        }
        else -> "PC • local ONNX inference"
    }
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Icon(Icons.Rounded.GraphicEq, contentDescription = null)
                Column(Modifier.weight(1f)) {
                    Text("Inference device", style = MaterialTheme.typography.titleSmall)
                    Text(status, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Spacer(
                    Modifier
                        .size(12.dp)
                        .background(
                            if (runtimeState.backendConnected) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.outline
                            },
                            CircleShape,
                        ),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (requested == InferenceDevice.COPILOT_PC) {
                    Button(
                        onClick = {},
                        enabled = runtimeState.backendConnected,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("PC")
                    }
                } else {
                    OutlinedButton(
                        onClick = { onSelected(InferenceDevice.COPILOT_PC) },
                        enabled = runtimeState.backendConnected,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("PC")
                    }
                }
                if (requested == InferenceDevice.SAMSUNG_PHONE) {
                    Button(
                        onClick = {},
                        enabled = runtimeState.backendConnected,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Samsung")
                    }
                } else {
                    OutlinedButton(
                        onClick = { onSelected(InferenceDevice.SAMSUNG_PHONE) },
                        enabled = runtimeState.backendConnected &&
                            runtimeState.samsungInferenceAvailable &&
                            phoneInferenceState.modelReady,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Samsung")
                    }
                }
            }
            if (!runtimeState.samsungInferenceAvailable) {
                Text(
                    "Connect the Samsung and start the demo to enable phone inference.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else if (!phoneInferenceState.modelReady) {
                Text(
                    "The Samsung sound model is still loading.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
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
