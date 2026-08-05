package com.quietcue.app.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.quietcue.app.data.ProfileJsonCodec
import com.quietcue.app.domain.ProfileDefaults

private enum class MainTab(val label: String) {
    HOME("Home"),
    PROFILES("Profiles"),
}

private enum class CreationFlow {
    PROFILE_AGENT,
    SOUND_ENROLLMENT,
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuietCueApp(viewModel: ProfileViewModel) {
    val catalog by viewModel.catalog.collectAsStateWithLifecycle()
    val runtimeState by viewModel.runtimeState.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    var selectedTabName by rememberSaveable { mutableStateOf(MainTab.HOME.name) }
    val selectedTab = MainTab.valueOf(selectedTabName)
    var editorProfileJson by rememberSaveable { mutableStateOf<String?>(null) }
    var creationFlowName by rememberSaveable { mutableStateOf<String?>(null) }
    val creationFlow = creationFlowName?.let(CreationFlow::valueOf)
    val editorProfile = editorProfileJson?.let {
        runCatching { ProfileJsonCodec.decode(it).firstOrNull() }.getOrNull()
    }

    LaunchedEffect(message) {
        message?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearMessage()
        }
    }

    if (creationFlow == CreationFlow.PROFILE_AGENT) {
        val activeProfile = catalog.activeProfile ?: ProfileDefaults.all().first()
        ProfileAgentScreen(
            activeProfile = activeProfile,
            soundLibrary = catalog.soundLibrary,
            onBack = { creationFlowName = null },
            onReview = { profile ->
                editorProfileJson = ProfileJsonCodec.encode(listOf(profile))
                creationFlowName = null
            },
        )
        return
    }

    if (creationFlow == CreationFlow.SOUND_ENROLLMENT) {
        SoundEnrollmentScreen(
            recordFingerprint = viewModel::recordEnrollmentFingerprint,
            onBack = { creationFlowName = null },
            onEnroll = { sound ->
                viewModel.enrollSound(sound)
                creationFlowName = null
            },
        )
        return
    }

    if (editorProfile != null) {
        ProfileEditorScreen(
            initialProfile = editorProfile,
            soundLibrary = catalog.soundLibrary,
            onBack = { editorProfileJson = null },
            onSave = { profile ->
                viewModel.save(profile)
                editorProfileJson = null
            },
        )
        return
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("QuietCue") }) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    selected = selectedTab == MainTab.HOME,
                    onClick = { selectedTabName = MainTab.HOME.name },
                    icon = { Icon(Icons.Rounded.Home, contentDescription = null) },
                    label = { Text(MainTab.HOME.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.PROFILES,
                    onClick = { selectedTabName = MainTab.PROFILES.name },
                    icon = { Icon(Icons.Rounded.Tune, contentDescription = null) },
                    label = { Text(MainTab.PROFILES.label) },
                )
            }
        },
        floatingActionButton = {
            if (selectedTab == MainTab.PROFILES) {
                ExtendedFloatingActionButton(
                    onClick = {
                        val template = catalog.activeProfile ?: ProfileDefaults.all().first()
                        val profile = ProfileDefaults.newCustom(template).copy(
                            soundRules = ProfileDefaults.completeRules(template.soundRules, catalog.soundLibrary),
                        )
                        editorProfileJson = ProfileJsonCodec.encode(listOf(profile))
                    },
                    icon = { Icon(Icons.Rounded.Add, contentDescription = null) },
                    text = { Text("New profile") },
                )
            }
        },
    ) { contentPadding ->
        when (selectedTab) {
            MainTab.HOME -> DashboardScreen(
                catalog = catalog,
                runtimeState = runtimeState,
                contentPadding = contentPadding,
            )
            MainTab.PROFILES -> ProfilesScreen(
                catalog = catalog,
                contentPadding = contentPadding,
                onEdit = { editorProfileJson = ProfileJsonCodec.encode(listOf(it)) },
                onActivate = viewModel::activate,
                onDuplicate = {
                    val profile = ProfileDefaults.duplicate(it).copy(
                        soundRules = ProfileDefaults.completeRules(it.soundRules, catalog.soundLibrary),
                    )
                    editorProfileJson = ProfileJsonCodec.encode(listOf(profile))
                },
                onDelete = viewModel::delete,
                onReset = viewModel::reset,
                onGenerateFromText = { creationFlowName = CreationFlow.PROFILE_AGENT.name },
                onEnrollSound = { creationFlowName = CreationFlow.SOUND_ENROLLMENT.name },
                onDeleteSound = viewModel::deleteEnrolledSound,
            )
        }
    }
}
