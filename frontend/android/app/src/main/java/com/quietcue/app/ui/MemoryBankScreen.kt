package com.quietcue.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.MenuBook
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Badge
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.DeleteForever
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.ContextMemory
import com.quietcue.app.domain.MemoryBank
import com.quietcue.app.domain.PersonMemory

@Composable
fun MemoryBankScreen(
    bank: MemoryBank,
    contentPadding: PaddingValues,
    onEditIdentity: () -> Unit,
    onEditPerson: (PersonMemory?) -> Unit,
    onDeletePerson: (String) -> Unit,
    onEditContext: (ContextMemory?) -> Unit,
    onDeleteContext: (String) -> Unit,
    onDeleteIdentity: () -> Unit,
    onClearAll: () -> Unit,
) {
    var deletePerson by remember { mutableStateOf<PersonMemory?>(null) }
    var deleteContext by remember { mutableStateOf<ContextMemory?>(null) }
    var confirmIdentityDelete by remember { mutableStateOf(false) }
    var confirmClear by remember { mutableStateOf(false) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = 20.dp,
            top = contentPadding.calculateTopPadding() + 12.dp,
            end = 20.dp,
            bottom = contentPadding.calculateBottomPadding() + 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("My context", style = MaterialTheme.typography.headlineMedium)
            Text(
                "Teach QuietCue the names and details you choose so local speech recognition has the right context.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Row(
                    Modifier.fillMaxWidth().padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Icon(Icons.Rounded.Lock, contentDescription = null)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("Private and user-controlled", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "This bank is encrypted on your phone. QuietCue never creates memories from background conversations, and enrollment audio is not saved.",
                            color = MaterialTheme.colorScheme.onSecondaryContainer,
                        )
                    }
                }
            }
        }

        item { SectionTitle("Your name") }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
                Row(
                    Modifier.fillMaxWidth().padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Rounded.Badge, contentDescription = null)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        val identity = bank.identity
                        Text(identity?.displayName ?: "No name enrolled", style = MaterialTheme.typography.titleMedium)
                        Text(
                            when {
                                identity == null -> "Add your name, pronunciation, aliases, and optional voice checks."
                                identity.pronunciation.isNotBlank() -> "Pronounced ${identity.pronunciation}"
                                else -> "${identity.aliases.size} aliases • ${identity.recognitionPhrases.size} voice checks"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    IconButton(onClick = onEditIdentity) {
                        Icon(Icons.Rounded.Edit, contentDescription = "Edit your name")
                    }
                    if (bank.identity != null) {
                        IconButton(onClick = { confirmIdentityDelete = true }) {
                            Icon(Icons.Rounded.Delete, contentDescription = "Delete name enrollment")
                        }
                    }
                }
            }
        }

        item { SectionTitle("People") }
        if (bank.people.isEmpty()) {
            item { EmptyMemoryCard("No people added", "Add family, friends, coworkers, or other important names.") }
        } else {
            items(bank.people, key = { it.id }) { person ->
                MemoryItemCard(
                    icon = { Icon(Icons.Rounded.Groups, contentDescription = null) },
                    title = person.name,
                    subtitle = listOf(person.relationship, person.pronunciation)
                        .filter(String::isNotBlank).joinToString(" • ").ifBlank { "Known person" },
                    onEdit = { onEditPerson(person) },
                    onDelete = { deletePerson = person },
                )
            }
        }
        item {
            OutlinedButton(onClick = { onEditPerson(null) }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Rounded.Add, contentDescription = null)
                Text(" Add a person")
            }
        }

        item { SectionTitle("Manual context") }
        if (bank.contexts.isEmpty()) {
            item { EmptyMemoryCard("No context added", "Add places, routines, projects, or other details you want QuietCue to know.") }
        } else {
            items(bank.contexts, key = { it.id }) { context ->
                MemoryItemCard(
                    icon = { Icon(Icons.AutoMirrored.Rounded.MenuBook, contentDescription = null) },
                    title = context.title,
                    subtitle = context.details,
                    onEdit = { onEditContext(context) },
                    onDelete = { deleteContext = context },
                )
            }
        }
        item {
            OutlinedButton(onClick = { onEditContext(null) }, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Rounded.Add, contentDescription = null)
                Text(" Add context")
            }
        }

        if (!bank.isEmpty) {
            item { SectionTitle("Privacy controls") }
            item {
                Button(onClick = { confirmClear = true }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Rounded.DeleteForever, contentDescription = null)
                    Text(" Delete entire memory bank")
                }
            }
        }
    }

    deletePerson?.let { person ->
        DeleteMemoryDialog(
            title = "Delete ${person.name}?",
            detail = "This person will be removed from transcription context.",
            onDismiss = { deletePerson = null },
            onConfirm = {
                onDeletePerson(person.id)
                deletePerson = null
            },
        )
    }
    deleteContext?.let { context ->
        DeleteMemoryDialog(
            title = "Delete ${context.title}?",
            detail = "This manual context entry will be permanently removed.",
            onDismiss = { deleteContext = null },
            onConfirm = {
                onDeleteContext(context.id)
                deleteContext = null
            },
        )
    }
    if (confirmIdentityDelete) {
        DeleteMemoryDialog(
            title = "Delete name enrollment?",
            detail = "Your name, pronunciation, aliases, and voice-check text will be removed from name detection.",
            onDismiss = { confirmIdentityDelete = false },
            onConfirm = {
                onDeleteIdentity()
                confirmIdentityDelete = false
            },
        )
    }
    if (confirmClear) {
        DeleteMemoryDialog(
            title = "Delete the entire memory bank?",
            detail = "Your name enrollment, people, and manual context will be permanently removed. Profiles and enrolled sounds are not affected.",
            onDismiss = { confirmClear = false },
            onConfirm = {
                onClearAll()
                confirmClear = false
            },
        )
    }
}

@Composable
private fun MemoryItemCard(
    icon: @Composable () -> Unit,
    title: String,
    subtitle: String,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            icon()
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 3)
            }
            IconButton(onClick = onEdit) { Icon(Icons.Rounded.Edit, contentDescription = "Edit $title") }
            IconButton(onClick = onDelete) { Icon(Icons.Rounded.Delete, contentDescription = "Delete $title") }
        }
    }
}

@Composable
private fun EmptyMemoryCard(title: String, detail: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun DeleteMemoryDialog(
    title: String,
    detail: String,
    onDismiss: () -> Unit,
    onConfirm: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(detail) },
        confirmButton = { TextButton(onClick = onConfirm) { Text("Delete") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
