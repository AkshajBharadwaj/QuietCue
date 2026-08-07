package com.quietcue.app.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AccountCircle
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.LocationOn
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
import com.quietcue.app.phone.PhoneInferenceStatus

private enum class MainTab(val label: String) {
    HOME("Home"),
    PROFILES("Profiles"),
    PLACES("Places"),
    MEMORY("My context"),
}

private enum class CreationFlow {
    PROFILE_AGENT,
    SOUND_ENROLLMENT,
}

private enum class MemoryEditorFlow {
    SPEECH,
    IDENTITY,
    PERSON,
    CONTEXT,
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuietCueApp(viewModel: ProfileViewModel) {
    val catalog by viewModel.catalog.collectAsStateWithLifecycle()
    val memoryBank by viewModel.memoryBank.collectAsStateWithLifecycle()
    val runtimeState by viewModel.runtimeState.collectAsStateWithLifecycle()
    val smartProfileState by viewModel.smartProfileState.collectAsStateWithLifecycle()
    val geofenceStatus by viewModel.geofenceStatus.collectAsStateWithLifecycle()
    val phoneInferenceState by PhoneInferenceStatus.state.collectAsStateWithLifecycle()
    val message by viewModel.message.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    var selectedTabName by rememberSaveable { mutableStateOf(MainTab.HOME.name) }
    val selectedTab = MainTab.valueOf(selectedTabName)
    var editorProfileJson by rememberSaveable { mutableStateOf<String?>(null) }
    var creationFlowName by rememberSaveable { mutableStateOf<String?>(null) }
    var enrollmentDiscoveryId by rememberSaveable { mutableStateOf<String?>(null) }
    var enrollmentSuggestedName by rememberSaveable { mutableStateOf("") }
    var memoryEditorFlowName by rememberSaveable { mutableStateOf<String?>(null) }
    var memoryEditorItemId by rememberSaveable { mutableStateOf<String?>(null) }
    val creationFlow = creationFlowName?.let(CreationFlow::valueOf)
    val memoryEditorFlow = memoryEditorFlowName?.let(MemoryEditorFlow::valueOf)
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
            initialName = enrollmentSuggestedName,
            initialDescription = enrollmentSuggestedName.takeIf(String::isNotBlank)?.let {
                "Recurring sound QuietCue classified as $it"
            }.orEmpty(),
            onBack = {
                creationFlowName = null
                enrollmentDiscoveryId = null
                enrollmentSuggestedName = ""
            },
            onEnroll = { sound ->
                viewModel.enrollSound(sound, enrollmentDiscoveryId)
                creationFlowName = null
                enrollmentDiscoveryId = null
                enrollmentSuggestedName = ""
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


    if (memoryEditorFlow == MemoryEditorFlow.IDENTITY) {
        IdentityEnrollmentScreen(
            initial = memoryBank.identity,
            recognizeSample = viewModel::recognizeNameSample,
            onBack = { memoryEditorFlowName = null },
            onSave = {
                viewModel.saveIdentity(it)
                memoryEditorFlowName = null
            },
        )
        return
    }

    if (memoryEditorFlow == MemoryEditorFlow.SPEECH) {
        SpeechSettingsScreen(
            initial = memoryBank.speechSettings,
            identityAvailable = memoryBank.identity != null,
            onBack = { memoryEditorFlowName = null },
            onSave = {
                viewModel.saveSpeechSettings(it)
                memoryEditorFlowName = null
            },
        )
        return
    }

    if (memoryEditorFlow == MemoryEditorFlow.PERSON) {
        PersonMemoryEditorScreen(
            initial = memoryBank.people.firstOrNull { it.id == memoryEditorItemId },
            onBack = {
                memoryEditorFlowName = null
                memoryEditorItemId = null
            },
            onSave = {
                viewModel.savePerson(it)
                memoryEditorFlowName = null
                memoryEditorItemId = null
            },
        )
        return
    }

    if (memoryEditorFlow == MemoryEditorFlow.CONTEXT) {
        ContextMemoryEditorScreen(
            initial = memoryBank.contexts.firstOrNull { it.id == memoryEditorItemId },
            onBack = {
                memoryEditorFlowName = null
                memoryEditorItemId = null
            },
            onSave = {
                viewModel.saveContext(it)
                memoryEditorFlowName = null
                memoryEditorItemId = null
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
                NavigationBarItem(
                    selected = selectedTab == MainTab.PLACES,
                    onClick = { selectedTabName = MainTab.PLACES.name },
                    icon = { Icon(Icons.Rounded.LocationOn, contentDescription = null) },
                    label = { Text(MainTab.PLACES.label) },
                )
                NavigationBarItem(
                    selected = selectedTab == MainTab.MEMORY,
                    onClick = { selectedTabName = MainTab.MEMORY.name },
                    icon = { Icon(Icons.Rounded.AccountCircle, contentDescription = null) },
                    label = { Text(MainTab.MEMORY.label) },
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
                smartProfileState = smartProfileState,
                phoneInferenceState = phoneInferenceState,
                contentPadding = contentPadding,
                onTeachDiscovery = { candidate ->
                    enrollmentDiscoveryId = candidate.id
                    enrollmentSuggestedName = candidate.label.take(40)
                    creationFlowName = CreationFlow.SOUND_ENROLLMENT.name
                },
                onAddDiscovery = viewModel::addDiscovery,
                onDismissDiscovery = viewModel::dismissDiscovery,
                onAcceptSmartSuggestion = { viewModel.acceptSmartProfileSuggestion(always = false) },
                onAlwaysSmartSuggestion = { viewModel.acceptSmartProfileSuggestion(always = true) },
                onDismissSmartSuggestion = viewModel::dismissSmartProfileSuggestion,
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
                onEnrollSound = {
                    enrollmentDiscoveryId = null
                    enrollmentSuggestedName = ""
                    creationFlowName = CreationFlow.SOUND_ENROLLMENT.name
                },
                onDeleteSound = viewModel::deleteEnrolledSound,
            )
            MainTab.PLACES -> SmartPlacesScreen(
                catalog = catalog,
                state = smartProfileState,
                registrationStatus = geofenceStatus,
                contentPadding = contentPadding,
                onAddCurrentPlace = viewModel::addCurrentSmartPlace,
                onAddDemoPlace = viewModel::addDemoSmartPlace,
                onDeletePlace = viewModel::deleteSmartPlace,
                onSetAutoApply = viewModel::setSmartPlaceAutoApply,
                onSimulate = viewModel::simulateSmartPlace,
                onRefresh = viewModel::refreshSmartPlaces,
            )
            MainTab.MEMORY -> MemoryBankScreen(
                bank = memoryBank,
                contentPadding = contentPadding,
                onEditSpeech = { memoryEditorFlowName = MemoryEditorFlow.SPEECH.name },
                onEditIdentity = { memoryEditorFlowName = MemoryEditorFlow.IDENTITY.name },
                onEditPerson = { person ->
                    memoryEditorItemId = person?.id
                    memoryEditorFlowName = MemoryEditorFlow.PERSON.name
                },
                onDeletePerson = viewModel::deletePerson,
                onEditContext = { context ->
                    memoryEditorItemId = context?.id
                    memoryEditorFlowName = MemoryEditorFlow.CONTEXT.name
                },
                onDeleteContext = viewModel::deleteContext,
                onDeleteIdentity = viewModel::deleteIdentity,
                onClearAll = viewModel::clearMemoryBank,
            )
        }
    }
}
