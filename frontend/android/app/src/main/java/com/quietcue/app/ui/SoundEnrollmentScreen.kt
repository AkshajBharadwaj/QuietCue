package com.quietcue.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.AcousticFingerprint
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.CapturedFingerprint
import com.quietcue.app.domain.EnrollmentCapture
import com.quietcue.app.domain.SoundDefinition
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SoundEnrollmentScreen(
    recordSession: suspend (Int) -> EnrollmentCapture,
    initialName: String = "",
    initialDescription: String = "",
    onBack: () -> Unit,
    onEnroll: (SoundDefinition) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var name by rememberSaveable(initialName) { mutableStateOf(initialName) }
    var description by rememberSaveable(initialDescription) { mutableStateOf(initialDescription) }
    var priorityName by rememberSaveable { mutableStateOf(AlertPriority.ATTENTION.name) }
    val priority = AlertPriority.valueOf(priorityName)
    val positives = remember { mutableStateListOf<CapturedFingerprint>() }
    var background by remember { mutableStateOf<CapturedFingerprint?>(null) }
    val confusingSounds = remember { mutableStateListOf<CapturedFingerprint>() }
    var testResult by remember { mutableStateOf<String?>(null) }
    var captureSummary by remember { mutableStateOf<String?>(null) }
    var recordingLabel by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun capture(label: String, durationMs: Int, onCaptured: (EnrollmentCapture) -> Unit) {
        scope.launch {
            recordingLabel = label
            error = null
            runCatching { recordSession(durationMs) }
                .onSuccess(onCaptured)
                .onFailure { error = it.message ?: "Recording failed" }
            recordingLabel = null
        }
    }

    BackHandler(onBack = onBack)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Enroll a sound") },
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
                Text(
                    "Tap once, then play the same sound 4–6 times with a short pause between repeats. QuietCue listens through the Arduino microphone, groups matching repeats, ignores speech and incidental sounds, and immediately discards raw audio.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it.take(40) },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Sound name") },
                            placeholder = { Text("Apartment buzzer") },
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = description,
                            onValueChange = { description = it.take(120) },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Description") },
                            placeholder = { Text("The buzzer near my front door") },
                            minLines = 2,
                        )
                        Text("Urgency", style = MaterialTheme.typography.labelLarge)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            AlertPriority.entries.forEach { option ->
                                FilterChip(
                                    selected = priority == option,
                                    onClick = { priorityName = option.name },
                                    label = { Text(option.displayName) },
                                )
                            }
                        }
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(Icons.Rounded.GraphicEq, contentDescription = null)
                            Text("Sound examples", style = MaterialTheme.typography.titleLarge)
                        }
                        Text("Keep normal room noise present, but do not talk during teaching. Vary the sound's distance or angle between repeats.")
                        positives.forEachIndexed { index, sample ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("✓ Example ${index + 1}: ${sample.rmsDbfs.roundToInt()} dBFS")
                                TextButton(onClick = { positives.removeAt(index); testResult = null }) { Text("Remove") }
                            }
                        }
                        if (positives.size in AcousticFingerprint.MIN_POSITIVE_SAMPLES until AcousticFingerprint.RECOMMENDED_POSITIVE_SAMPLES) {
                            Text("Usable, but add ${AcousticFingerprint.RECOMMENDED_POSITIVE_SAMPLES - positives.size} more varied example(s) for better coverage.")
                        }
                        captureSummary?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
                        Button(
                            onClick = {
                                capture("Listening for repeated sounds", 10_000) { session ->
                                    val room = AcousticFingerprint.MAX_POSITIVE_SAMPLES - positives.size
                                    positives.addAll(session.positives.take(room))
                                    background = session.background
                                    captureSummary = buildString {
                                        append("Found ${session.positives.size} sound repeat(s) and calibrated the room")
                                        if (session.speechRejectedMs > 0) {
                                            append("; ignored ${session.speechRejectedMs / 1_000.0} seconds of speech")
                                        }
                                        append(".")
                                    }
                                    if (session.positives.isEmpty()) {
                                        error = "No clear sound was found. Move it closer to the Arduino microphone and leave a short pause between repeats."
                                    }
                                }
                            },
                            enabled = recordingLabel == null && positives.size < AcousticFingerprint.MAX_POSITIVE_SAMPLES,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Rounded.Mic, contentDescription = null)
                            Text(
                                if (recordingLabel != null) " ${recordingLabel}…"
                                else if (positives.isEmpty()) " Start 10-second guided capture"
                                else " Add another guided capture",
                            )
                        }
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Automatic background calibration", style = MaterialTheme.typography.titleLarge)
                        Text("QuietCue uses the quietest part of each guided session as the room baseline.")
                        background?.let { Text("✓ Room baseline: ${it.rmsDbfs.roundToInt()} dBFS") }
                            ?: Text("The baseline will be captured with your first teaching session.")
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Confusing sounds (optional)", style = MaterialTheme.typography.titleLarge)
                        Text("Add sounds that resemble this one but should not trigger it. These help set a safer threshold.")
                        confusingSounds.forEachIndexed { index, sample ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("Non-match ${index + 1}: ${sample.rmsDbfs.roundToInt()} dBFS")
                                TextButton(onClick = { confusingSounds.removeAt(index) }) { Text("Remove") }
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                capture("Listening for non-matches", 4_000) { session ->
                                    confusingSounds.addAll(session.positives.take(10 - confusingSounds.size))
                                    if (session.positives.isEmpty()) {
                                        error = "No clear non-match was found. Play it closer to the Arduino microphone."
                                    }
                                }
                            },
                            enabled = recordingLabel == null && confusingSounds.size < 10,
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("Add confusing sound") }
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Test before saving", style = MaterialTheme.typography.titleLarge)
                        Text("Play the enrolled sound again to check whether the current examples recognize it.")
                        OutlinedButton(
                            onClick = {
                                capture("Listening for the test sound", 4_000) { session ->
                                    val draftEnrollment = runCatching {
                                        AcousticFingerprint.enroll(
                                            name = name.ifBlank { "Test sound" },
                                            description = description,
                                            priority = priority,
                                            positives = positives,
                                            background = requireNotNull(background),
                                            confusingSounds = confusingSounds,
                                        ).enrollment
                                    }.getOrNull()
                                    val rawBest = session.positives.maxOfOrNull { sample ->
                                        positives.maxOfOrNull { example ->
                                            AcousticFingerprint.similarity(sample.features, example.features)
                                        } ?: 0f
                                    } ?: 0f
                                    val matched = draftEnrollment?.let { enrollment ->
                                        session.positives.mapNotNull { sample ->
                                            AcousticFingerprint.matchConfidence(sample.features, enrollment)
                                        }.maxOrNull()
                                    }
                                    testResult = if (matched != null) {
                                        "Match ${(matched * 100).roundToInt()}% across multiple examples"
                                    } else {
                                        "No reliable match ${(rawBest * 100).roundToInt()}% — add another clean repeat"
                                    }
                                }
                            },
                            enabled = recordingLabel == null && positives.size >= AcousticFingerprint.MIN_POSITIVE_SAMPLES,
                            modifier = Modifier.fillMaxWidth(),
                        ) { Text("Record test") }
                        testResult?.let { Text(it) }
                    }
                }
            }
            error?.let { message ->
                item { Text(message, color = MaterialTheme.colorScheme.error) }
            }
            item {
                Button(
                    onClick = {
                        runCatching {
                            AcousticFingerprint.enroll(
                                name = name,
                                description = description,
                                priority = priority,
                                positives = positives,
                                background = requireNotNull(background),
                                confusingSounds = confusingSounds,
                            )
                        }.onSuccess(onEnroll).onFailure { error = it.message }
                    },
                    enabled = name.isNotBlank() && positives.size >= AcousticFingerprint.MIN_POSITIVE_SAMPLES && background != null && recordingLabel == null,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Create enrolled sound")
                }
            }
            item {
                Text(
                    "Enrollment matching is an experimental local fingerprint and must not be used as the only detector for safety-critical sounds.",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.labelMedium,
                )
            }
        }
    }
}
