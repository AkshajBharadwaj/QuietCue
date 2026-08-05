package com.quietcue.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.SoundDefinition

@Composable
fun ProfilesScreen(
    catalog: ProfileCatalog,
    contentPadding: PaddingValues,
    onEdit: (AlertProfile) -> Unit,
    onActivate: (String) -> Unit,
    onDuplicate: (AlertProfile) -> Unit,
    onDelete: (String) -> Unit,
    onReset: (String) -> Unit,
    onGenerateFromText: () -> Unit,
    onEnrollSound: () -> Unit,
    onDeleteSound: (String) -> Unit,
) {
    var deleteCandidate by remember { mutableStateOf<AlertProfile?>(null) }
    var soundDeleteCandidate by remember { mutableStateOf<SoundDefinition?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = 20.dp,
            top = contentPadding.calculateTopPadding() + 12.dp,
            end = 20.dp,
            bottom = contentPadding.calculateBottomPadding() + 96.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Profiles", style = MaterialTheme.typography.headlineMedium)
            Text(
                "Choose what QuietCue listens for and how each alert should feel.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(
                    Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("Create for a new situation", style = MaterialTheme.typography.titleLarge)
                    Text("Describe an unfamiliar place or teach QuietCue a sound unique to you.")
                    Button(onClick = onGenerateFromText, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Rounded.AutoAwesome, contentDescription = null)
                        Text(" Describe a situation")
                    }
                    OutlinedButton(onClick = onEnrollSound, modifier = Modifier.fillMaxWidth()) {
                        Icon(Icons.Rounded.GraphicEq, contentDescription = null)
                        Text(" Enroll a sound")
                    }
                }
            }
        }

        val enrolledSounds = catalog.soundLibrary.filter(SoundDefinition::isEnrolled)
        if (enrolledSounds.isNotEmpty()) {
            item { SectionTitle("Enrolled sounds") }
            items(count = enrolledSounds.size, key = { enrolledSounds[it].id }) { index ->
                val sound = enrolledSounds[index]
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Icon(Icons.Rounded.GraphicEq, contentDescription = null)
                        Column(Modifier.weight(1f)) {
                            Text(sound.displayName, style = MaterialTheme.typography.titleMedium)
                            Text(
                                "${sound.enrollment?.positiveSampleCount ?: 0} examples • experimental local match",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        IconButton(onClick = { soundDeleteCandidate = sound }) {
                            Icon(Icons.Rounded.Delete, contentDescription = "Delete ${sound.displayName}")
                        }
                    }
                }
            }
        }

        item { SectionTitle("Built-in") }
        items(
            count = catalog.profiles.count(AlertProfile::isBuiltIn),
            key = { index -> catalog.profiles.filter(AlertProfile::isBuiltIn)[index].id },
        ) { index ->
            val profile = catalog.profiles.filter(AlertProfile::isBuiltIn)[index]
            ProfileCard(
                profile = profile,
                active = profile.id == catalog.activeProfileId,
                onEdit = { onEdit(profile) },
                onActivate = { onActivate(profile.id) },
                onDuplicate = { onDuplicate(profile) },
                onDelete = {},
                onReset = { onReset(profile.id) },
            )
        }

        val customProfiles = catalog.profiles.filterNot(AlertProfile::isBuiltIn)
        if (customProfiles.isNotEmpty()) {
            item { SectionTitle("Custom") }
            items(count = customProfiles.size, key = { customProfiles[it].id }) { index ->
                val profile = customProfiles[index]
                ProfileCard(
                    profile = profile,
                    active = profile.id == catalog.activeProfileId,
                    onEdit = { onEdit(profile) },
                    onActivate = { onActivate(profile.id) },
                    onDuplicate = { onDuplicate(profile) },
                    onDelete = { deleteCandidate = profile },
                    onReset = {},
                )
            }
        }
    }

    deleteCandidate?.let { profile ->
        AlertDialog(
            onDismissRequest = { deleteCandidate = null },
            title = { Text("Delete ${profile.name}?") },
            text = { Text("This custom profile and all of its alert settings will be removed.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDelete(profile.id)
                        deleteCandidate = null
                    },
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { deleteCandidate = null }) { Text("Cancel") }
            },
        )
    }

    soundDeleteCandidate?.let { sound ->
        AlertDialog(
            onDismissRequest = { soundDeleteCandidate = null },
            title = { Text("Delete ${sound.displayName}?") },
            text = {
                Text("Its acoustic fingerprint and alert rule will be removed from every profile. This cannot be undone.")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDeleteSound(sound.id)
                        soundDeleteCandidate = null
                    },
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { soundDeleteCandidate = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun ProfileCard(
    profile: AlertProfile,
    active: Boolean,
    onEdit: () -> Unit,
    onActivate: () -> Unit,
    onDuplicate: () -> Unit,
    onDelete: () -> Unit,
    onReset: () -> Unit,
) {
    var menuExpanded by remember { mutableStateOf(false) }
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (active) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceContainer,
        ),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Surface(
                    modifier = Modifier.size(46.dp),
                    shape = CircleShape,
                    color = profile.color.color(),
                    contentColor = Color.White,
                ) {
                    Icon(
                        profile.icon.imageVector(),
                        contentDescription = null,
                        modifier = Modifier.padding(11.dp),
                    )
                }
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(profile.name, style = MaterialTheme.typography.titleMedium)
                        if (active) {
                            Icon(
                                Icons.Rounded.CheckCircle,
                                contentDescription = "Active profile",
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(19.dp),
                            )
                        }
                    }
                    Text(
                        "${profile.enabledSoundCount} of ${profile.soundRules.size} sounds enabled",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = { menuExpanded = true }) {
                    Icon(Icons.Rounded.MoreVert, contentDescription = "More options for ${profile.name}")
                }
                DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                    DropdownMenuItem(
                        text = { Text("Edit") },
                        leadingIcon = { Icon(Icons.Rounded.Edit, contentDescription = null) },
                        onClick = { menuExpanded = false; onEdit() },
                    )
                    DropdownMenuItem(
                        text = { Text("Duplicate") },
                        leadingIcon = { Icon(Icons.Rounded.ContentCopy, contentDescription = null) },
                        onClick = { menuExpanded = false; onDuplicate() },
                    )
                    if (profile.isBuiltIn) {
                        DropdownMenuItem(
                            text = { Text("Restore defaults") },
                            leadingIcon = { Icon(Icons.Rounded.RestartAlt, contentDescription = null) },
                            onClick = { menuExpanded = false; onReset() },
                        )
                    } else {
                        DropdownMenuItem(
                            text = { Text("Delete") },
                            leadingIcon = { Icon(Icons.Rounded.Delete, contentDescription = null) },
                            onClick = { menuExpanded = false; onDelete() },
                        )
                    }
                }
            }
            Text(profile.description, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (active) {
                OutlinedButton(onClick = onEdit, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Rounded.Edit, contentDescription = null)
                    Text(" Edit active profile")
                }
            } else {
                Button(onClick = onActivate, modifier = Modifier.fillMaxWidth()) {
                    Text("Use this profile")
                }
            }
        }
    }
}
