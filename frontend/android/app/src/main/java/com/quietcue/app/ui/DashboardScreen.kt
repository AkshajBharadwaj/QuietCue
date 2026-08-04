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
import androidx.compose.material.icons.rounded.Hearing
import androidx.compose.material.icons.rounded.NotificationsNone
import androidx.compose.material.icons.rounded.Watch
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.ProfileCatalog

@Composable
fun DashboardScreen(catalog: ProfileCatalog, contentPadding: PaddingValues) {
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

        item { SectionTitle("System status") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusRow(Icons.Rounded.Hearing, "Phone app", "Profile controls available", true)
                StatusRow(Icons.Rounded.CloudOff, "Snapdragon PC", "Not connected yet", false)
                StatusRow(Icons.Rounded.Watch, "Uno Q wearable", "Not connected yet", false)
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
                    Icon(
                        Icons.Rounded.NotificationsNone,
                        contentDescription = null,
                        modifier = Modifier.size(32.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Column {
                        Text("No alerts yet", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Detected sounds, confidence, latency, and acknowledgement will appear here.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
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
