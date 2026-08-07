package com.quietcue.app.ui

import android.Manifest
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddLocationAlt
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.LocationOff
import androidx.compose.material.icons.rounded.LocationOn
import androidx.compose.material.icons.rounded.PlayArrow
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.PlaceTransition
import com.quietcue.app.domain.ProfileCatalog
import com.quietcue.app.domain.SmartPlace
import com.quietcue.app.domain.SmartProfileState
import com.quietcue.app.location.GeofenceRegistrationStatus
import com.quietcue.app.location.SmartPlacePermissions

private data class PlaceDraft(
    val name: String,
    val profileId: String,
    val radiusMeters: Float,
)

@Composable
fun SmartPlacesScreen(
    catalog: ProfileCatalog,
    state: SmartProfileState,
    registrationStatus: GeofenceRegistrationStatus,
    contentPadding: PaddingValues,
    onAddCurrentPlace: (String, String, Float) -> Unit,
    onAddDemoPlace: () -> Unit,
    onDeletePlace: (String) -> Unit,
    onSetAutoApply: (String, Boolean) -> Unit,
    onSimulate: (String, PlaceTransition) -> Unit,
    onRefresh: (Boolean) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var permissionRefresh by remember { mutableIntStateOf(0) }
    var showAddDialog by remember { mutableStateOf(false) }
    var showBackgroundEducation by remember { mutableStateOf(false) }
    var pendingDraft by remember { mutableStateOf<PlaceDraft?>(null) }
    @Suppress("UNUSED_EXPRESSION")
    permissionRefresh
    val hasPreciseLocation = SmartPlacePermissions.hasPreciseLocation(context)
    val hasBackgroundLocation = SmartPlacePermissions.hasBackgroundLocation(context)

    val foregroundPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { permissions ->
        permissionRefresh += 1
        val preciseGranted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            SmartPlacePermissions.hasPreciseLocation(context)
        val draft = pendingDraft
        pendingDraft = null
        if (preciseGranted && draft != null) {
            onAddCurrentPlace(draft.name, draft.profileId, draft.radiusMeters)
        }
        onRefresh(false)
    }
    val backgroundPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) {
        permissionRefresh += 1
        onRefresh(true)
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                permissionRefresh += 1
                onRefresh(false)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = 20.dp,
            top = contentPadding.calculateTopPadding() + 12.dp,
            end = 20.dp,
            bottom = contentPadding.calculateBottomPadding() + 24.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Smart places", style = MaterialTheme.typography.headlineMedium)
            Text(
                "QuietCue can suggest a profile when you arrive and switch back when you leave. " +
                    "Saved coordinates stay on this phone.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        item {
            MonitoringCard(
                registrationStatus = registrationStatus,
                hasPreciseLocation = hasPreciseLocation,
                hasBackgroundLocation = hasBackgroundLocation,
                hasRealPlaces = state.places.any { !it.demoOnly },
                onEnable = { showBackgroundEducation = true },
            )
        }

        if (state.manualOverrideActive(System.currentTimeMillis())) {
            item {
                val minutes = ((state.manualOverrideUntilEpochMs - System.currentTimeMillis()) / 60_000L)
                    .coerceAtLeast(1L)
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp)) {
                        Text("Manual choice protected", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Automatic changes are paused for about $minutes minutes. " +
                                "QuietCue can still show suggestions.",
                        )
                    }
                }
            }
        }

        item {
            Button(onClick = { showAddDialog = true }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Rounded.AddLocationAlt, contentDescription = null)
                Text(" Save my current place")
            }
        }

        if (state.places.none { it.demoOnly }) {
            item {
                OutlinedButton(onClick = onAddDemoPlace, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                    Text(" Create hackathon demo place")
                }
            }
        }

        if (state.places.isNotEmpty()) {
            item { SectionTitle("Saved places") }
            items(state.places, key = SmartPlace::id) { place ->
                SmartPlaceCard(
                    place = place,
                    profile = catalog.profiles.firstOrNull { it.id == place.profileId },
                    onDelete = { onDeletePlace(place.id) },
                    onSetAutoApply = { onSetAutoApply(place.id, it) },
                    onSimulateArrival = { onSimulate(place.id, PlaceTransition.ENTER) },
                    onSimulateDeparture = { onSimulate(place.id, PlaceTransition.EXIT) },
                )
            }
        }
    }

    if (showAddDialog) {
        AddPlaceDialog(
            profiles = catalog.profiles,
            defaultProfileId = catalog.activeProfileId,
            onDismiss = { showAddDialog = false },
            onConfirm = { draft ->
                showAddDialog = false
                if (SmartPlacePermissions.hasPreciseLocation(context)) {
                    onAddCurrentPlace(draft.name, draft.profileId, draft.radiusMeters)
                } else {
                    pendingDraft = draft
                    foregroundPermissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                            Manifest.permission.ACCESS_FINE_LOCATION,
                        ),
                    )
                }
            },
        )
    }

    if (showBackgroundEducation) {
        AlertDialog(
            onDismissRequest = { showBackgroundEducation = false },
            icon = { Icon(Icons.Rounded.LocationOn, contentDescription = null) },
            title = { Text("Allow background suggestions") },
            text = {
                Text(
                    "Choose precise location and Allow all the time so Android can notify QuietCue " +
                        "when you cross a saved place boundary. Location remains local and the feature " +
                        "still works in ask-before-switching mode.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showBackgroundEducation = false
                        when {
                            !SmartPlacePermissions.hasPreciseLocation(context) -> {
                                foregroundPermissionLauncher.launch(
                                    arrayOf(
                                        Manifest.permission.ACCESS_COARSE_LOCATION,
                                        Manifest.permission.ACCESS_FINE_LOCATION,
                                    ),
                                )
                            }
                            Build.VERSION.SDK_INT == Build.VERSION_CODES.Q -> {
                                backgroundPermissionLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
                            }
                            Build.VERSION.SDK_INT >= Build.VERSION_CODES.R -> {
                                context.startActivity(
                                    Intent(
                                        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                        "package:${context.packageName}".toUri(),
                                    ),
                                )
                            }
                            else -> onRefresh(true)
                        }
                    },
                ) { Text("Continue") }
            },
            dismissButton = {
                TextButton(onClick = { showBackgroundEducation = false }) { Text("Not now") }
            },
        )
    }
}

@Composable
private fun MonitoringCard(
    registrationStatus: GeofenceRegistrationStatus,
    hasPreciseLocation: Boolean,
    hasBackgroundLocation: Boolean,
    hasRealPlaces: Boolean,
    onEnable: () -> Unit,
) {
    val active = registrationStatus == GeofenceRegistrationStatus.ACTIVE
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (active) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceContainer
            },
        ),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(
                if (active) Icons.Rounded.LocationOn else Icons.Rounded.LocationOff,
                contentDescription = null,
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(
                    if (active) "Background suggestions active" else "Background suggestions need setup",
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    when {
                        !hasPreciseLocation -> "Precise location is needed to define reliable boundaries."
                        !hasBackgroundLocation -> "Allow all-time access for arrival and departure events."
                        !hasRealPlaces -> "Permission is ready. Save a real place to begin."
                        registrationStatus == GeofenceRegistrationStatus.PLAY_SERVICES_UNAVAILABLE -> {
                            "Google Play location services are unavailable on this device."
                        }
                        registrationStatus == GeofenceRegistrationStatus.REGISTRATION_FAILED -> {
                            "Android could not register the saved boundaries. Check location settings and try again."
                        }
                        else -> "Low-power geofences are registered on this phone."
                    },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (!active && (!hasPreciseLocation || !hasBackgroundLocation)) {
                TextButton(onClick = onEnable) { Text("Enable") }
            }
        }
    }
}

@Composable
private fun SmartPlaceCard(
    place: SmartPlace,
    profile: AlertProfile?,
    onDelete: () -> Unit,
    onSetAutoApply: (Boolean) -> Unit,
    onSimulateArrival: () -> Unit,
    onSimulateDeparture: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Icon(Icons.Rounded.LocationOn, contentDescription = null)
                Column(Modifier.weight(1f)) {
                    Text(place.name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        if (place.demoOnly) {
                            "Demo only • no GPS monitoring"
                        } else {
                            "${place.radiusMeters.toInt()} m boundary • coordinates stored locally"
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(Icons.Rounded.Delete, contentDescription = "Delete ${place.name}")
                }
            }
            Text("Profile: ${profile?.name ?: "Unavailable profile"}")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Switch automatically", style = MaterialTheme.typography.labelLarge)
                    Text(
                        if (place.autoApply) "After an explicit Always here choice" else "Ask before changing",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(checked = place.autoApply, onCheckedChange = onSetAutoApply)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onSimulateArrival, modifier = Modifier.weight(1f)) {
                    Text("Test arrival")
                }
                OutlinedButton(onClick = onSimulateDeparture, modifier = Modifier.weight(1f)) {
                    Text("Test departure")
                }
            }
        }
    }
}

@Composable
private fun AddPlaceDialog(
    profiles: List<AlertProfile>,
    defaultProfileId: String,
    onDismiss: () -> Unit,
    onConfirm: (PlaceDraft) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var profileId by remember(defaultProfileId) { mutableStateOf(defaultProfileId) }
    var radius by remember { mutableStateOf(150f) }
    var menuExpanded by remember { mutableStateOf(false) }
    val profile = profiles.firstOrNull { it.id == profileId } ?: profiles.firstOrNull()

    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Rounded.AddLocationAlt, contentDescription = null) },
        title = { Text("Save this place") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("QuietCue captures your current position once, then stores the boundary only on this phone.")
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(40) },
                    label = { Text("Place name") },
                    placeholder = { Text("Work, school, or home") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Box(Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = { menuExpanded = true }, modifier = Modifier.fillMaxWidth()) {
                        Text("Profile: ${profile?.name ?: "Choose"}")
                    }
                    DropdownMenu(
                        expanded = menuExpanded,
                        onDismissRequest = { menuExpanded = false },
                    ) {
                        profiles.forEach { item ->
                            DropdownMenuItem(
                                text = { Text(item.name) },
                                onClick = {
                                    profileId = item.id
                                    menuExpanded = false
                                },
                            )
                        }
                    }
                }
                Text("Boundary radius: ${radius.toInt()} m")
                Slider(
                    value = radius,
                    onValueChange = { radius = it },
                    valueRange = 15f..500f,
                )
                if (radius < 100f) {
                    Text(
                        "Boundaries below 100 m are intended for simulation; real phone location may not trigger reliably.",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = name.isNotBlank() && profile != null,
                onClick = { onConfirm(PlaceDraft(name.trim(), profile!!.id, radius)) },
            ) { Text("Use current location") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
