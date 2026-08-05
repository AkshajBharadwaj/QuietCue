package com.quietcue.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Mic
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
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.PersonMemory
import com.quietcue.app.domain.UserIdentity
import java.util.UUID
import kotlinx.coroutines.launch

@Composable
fun IdentityEnrollmentScreen(
    initial: UserIdentity?,
    recognizeSample: suspend () -> String,
    onBack: () -> Unit,
    onSave: (UserIdentity) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var hasPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        hasPermission = it
    }
    var name by rememberSaveable(initial) { mutableStateOf(initial?.displayName.orEmpty()) }
    var pronunciation by rememberSaveable(initial) { mutableStateOf(initial?.pronunciation.orEmpty()) }
    var aliases by rememberSaveable(initial) { mutableStateOf(initial?.aliases?.joinToString(", ").orEmpty()) }
    val samples = remember(initial) {
        mutableStateListOf<String>().apply { addAll(initial?.recognitionPhrases.orEmpty()) }
    }
    var listening by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    EditorScaffold("Enroll your name", onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = editorPadding(padding),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                Text(
                    "Your name and approved variants help the local speech model recognize when someone calls you.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it.take(60) },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Your name") },
                            placeholder = { Text("Akshaj") },
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = pronunciation,
                            onValueChange = { pronunciation = it.take(80) },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Pronunciation guide") },
                            placeholder = { Text("Ak-shudge") },
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = aliases,
                            onValueChange = { aliases = it.take(320) },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Nicknames or aliases") },
                            supportingText = { Text("Separate entries with commas.") },
                        )
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Voice checks", style = MaterialTheme.typography.titleLarge)
                        Text(
                            "Have someone say your name naturally. The phone keeps only the recognized text, never the recording. You can save up to three checks.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        samples.forEachIndexed { index, sample ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("${index + 1}. “$sample”", modifier = Modifier.weight(1f))
                                IconButton(onClick = { samples.removeAt(index) }) {
                                    Icon(Icons.Rounded.Delete, contentDescription = "Remove voice check ${index + 1}")
                                }
                            }
                        }
                        Button(
                            onClick = {
                                if (!hasPermission) {
                                    permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                                } else {
                                    scope.launch {
                                        listening = true
                                        error = null
                                        runCatching { recognizeSample() }
                                            .onSuccess { text ->
                                                if (samples.none { it.equals(text, ignoreCase = true) }) samples += text
                                            }
                                            .onFailure { error = it.message ?: "Recognition failed" }
                                        listening = false
                                    }
                                }
                            },
                            enabled = !listening && samples.size < 3,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Rounded.Mic, contentDescription = null)
                            Text(if (listening) " Listening…" else " Record voice check ${samples.size + 1}")
                        }
                    }
                }
            }
            error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            item {
                Button(
                    onClick = {
                        onSave(
                            UserIdentity(
                                displayName = name.trim(),
                                pronunciation = pronunciation.trim(),
                                aliases = parseCommaList(aliases, 10),
                                recognitionPhrases = samples.toList(),
                            ),
                        )
                    },
                    enabled = name.isNotBlank() && !listening,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Save name enrollment") }
            }
        }
    }
}

@Composable
fun PersonMemoryEditorScreen(
    initial: PersonMemory?,
    onBack: () -> Unit,
    onSave: (PersonMemory) -> Unit,
) {
    val id by rememberSaveable(initial?.id) { mutableStateOf(initial?.id ?: UUID.randomUUID().toString()) }
    var name by rememberSaveable(initial) { mutableStateOf(initial?.name.orEmpty()) }
    var relationship by rememberSaveable(initial) { mutableStateOf(initial?.relationship.orEmpty()) }
    var pronunciation by rememberSaveable(initial) { mutableStateOf(initial?.pronunciation.orEmpty()) }
    var aliases by rememberSaveable(initial) { mutableStateOf(initial?.aliases?.joinToString(", ").orEmpty()) }
    var notes by rememberSaveable(initial) { mutableStateOf(initial?.notes.orEmpty()) }

    EditorScaffold(if (initial == null) "Add a person" else "Edit ${initial.name}", onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = editorPadding(padding),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    "People are added only when you enter them here. Their names help local transcription; they do not trigger your name alert.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item { MemoryTextField(name, { name = it.take(60) }, "Name", "Maya") }
            item { MemoryTextField(relationship, { relationship = it.take(80) }, "Relationship", "Sister") }
            item { MemoryTextField(pronunciation, { pronunciation = it.take(80) }, "Pronunciation", "My-uh") }
            item { MemoryTextField(aliases, { aliases = it.take(320) }, "Aliases", "May, M") }
            item {
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it.take(280) },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Notes") },
                    placeholder = { Text("Lives nearby and usually visits on weekends") },
                    minLines = 3,
                    supportingText = { Text("${notes.length}/280") },
                )
            }
            item {
                Button(
                    onClick = {
                        onSave(
                            PersonMemory(
                                id = id,
                                name = name.trim(),
                                relationship = relationship.trim(),
                                pronunciation = pronunciation.trim(),
                                aliases = parseCommaList(aliases, 10),
                                notes = notes.trim(),
                            ),
                        )
                    },
                    enabled = name.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Save person") }
            }
        }
    }
}

@Composable
fun ContextMemoryEditorScreen(
    initial: ContextMemory?,
    onBack: () -> Unit,
    onSave: (ContextMemory) -> Unit,
) {
    val id by rememberSaveable(initial?.id) { mutableStateOf(initial?.id ?: UUID.randomUUID().toString()) }
    var title by rememberSaveable(initial) { mutableStateOf(initial?.title.orEmpty()) }
    var details by rememberSaveable(initial) { mutableStateOf(initial?.details.orEmpty()) }

    EditorScaffold(if (initial == null) "Add context" else "Edit ${initial.title}", onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = editorPadding(padding),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    "Add only details you want QuietCue to use as local transcription context. Nothing is inferred automatically.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item { MemoryTextField(title, { title = it.take(80) }, "Title", "Tuesday class") }
            item {
                OutlinedTextField(
                    value = details,
                    onValueChange = { details = it.take(500) },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Details") },
                    placeholder = { Text("My Tuesday accessibility design class is in Building 4.") },
                    minLines = 5,
                    supportingText = { Text("${details.length}/500") },
                )
            }
            item {
                Button(
                    onClick = { onSave(ContextMemory(id, title.trim(), details.trim())) },
                    enabled = title.isNotBlank() && details.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Save context") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EditorScaffold(
    title: String,
    onBack: () -> Unit,
    content: @Composable (PaddingValues) -> Unit,
) {
    BackHandler(onBack = onBack)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Go back")
                    }
                },
            )
        },
        content = content,
    )
}

@Composable
private fun MemoryTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    placeholder: String,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        placeholder = { Text(placeholder) },
        singleLine = true,
    )
}

private fun editorPadding(padding: PaddingValues) = PaddingValues(
    start = 20.dp,
    top = padding.calculateTopPadding() + 12.dp,
    end = 20.dp,
    bottom = padding.calculateBottomPadding() + 28.dp,
)

private fun parseCommaList(value: String, maximum: Int): List<String> = value
    .split(',')
    .map(String::trim)
    .filter(String::isNotEmpty)
    .distinctBy { it.lowercase() }
    .take(maximum)
