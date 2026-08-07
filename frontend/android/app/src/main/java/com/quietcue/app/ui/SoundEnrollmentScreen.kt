package com.quietcue.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.quietcue.app.domain.AcousticFingerprint
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.CapturedFingerprint
import com.quietcue.app.domain.SoundDefinition
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SoundEnrollmentScreen(
    recordFingerprint: suspend () -> CapturedFingerprint,
    initialName: String = "",
    initialDescription: String = "",
    onBack: () -> Unit,
    onEnroll: (SoundDefinition) -> Unit,
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
    var name by rememberSaveable(initialName) { mutableStateOf(initialName) }
    var description by rememberSaveable(initialDescription) { mutableStateOf(initialDescription) }
    var priorityName by rememberSaveable { mutableStateOf(AlertPriority.ATTENTION.name) }
    val priority = AlertPriority.valueOf(priorityName)
    val positives = remember { mutableStateListOf<CapturedFingerprint>() }
    var background by remember { mutableStateOf<CapturedFingerprint?>(null) }
    val confusingSounds = remember { mutableStateListOf<CapturedFingerprint>() }
    var testResult by remember { mutableStateOf<String?>(null) }
    var recordingLabel by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun capture(label: String, onCaptured: (CapturedFingerprint) -> Unit) {
        if (!hasPermission) {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        scope.launch {
            recordingLabel = label
            error = null
            runCatching { recordFingerprint() }
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
                    "Record at least 3 examples; 6–10 varied examples are recommended. You can add up to 30. QuietCue keeps only acoustic fingerprints—not raw audio.",
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
                        Text("Vary distance, angle, and normal room noise. Try nearby, across the room, and partly muffled examples.")
                        positives.forEachIndexed { index, sample ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("✓ Example ${index + 1}: ${sample.rmsDbfs.roundToInt()} dBFS")
                                TextButton(onClick = { positives.removeAt(index); testResult = null }) { Text("Remove") }
                            }
                        }
                        if (positives.size in AcousticFingerprint.MIN_POSITIVE_SAMPLES until AcousticFingerprint.RECOMMENDED_POSITIVE_SAMPLES) {
                            Text("Usable, but add ${AcousticFingerprint.RECOMMENDED_POSITIVE_SAMPLES - positives.size} more varied example(s) for better coverage.")
                        }
                        if (positives.indices.any { right ->
                                (0 until right).any { left ->
                                    AcousticFingerprint.similarity(positives[left].features, positives[right].features) > 0.995f
                                }
                            }
                        ) {
                            Text("Some examples are nearly identical. Record from another distance, angle, or noise condition.", color = MaterialTheme.colorScheme.error)
                        }
                        Button(
                            onClick = {
                                capture("Recording example ${positives.size + 1}") { sample -> positives += sample }
                            },
                            enabled = recordingLabel == null && positives.size < AcousticFingerprint.MAX_POSITIVE_SAMPLES,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Rounded.Mic, contentDescription = null)
                            Text(
                                if (recordingLabel != null) " ${recordingLabel}…"
                                else " Add 2-second example ${positives.size + 1}",
                            )
                        }
                    }
                }
            }
            item {
                Card {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Background calibration", style = MaterialTheme.typography.titleLarge)
                        Text("Record the same space without playing the sound. This helps reject false alerts.")
                        background?.let { Text("✓ Background: ${it.rmsDbfs.roundToInt()} dBFS") }
                        OutlinedButton(
                            onClick = { capture("Recording background") { background = it } },
                            enabled = recordingLabel == null,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Rounded.Mic, contentDescription = null)
                            Text(if (background == null) " Record background" else " Replace background")
                        }
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
                            onClick = { capture("Recording non-match") { confusingSounds += it } },
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
                                capture("Testing sound") { sample ->
                                    val best = positives.maxOfOrNull {
                                        AcousticFingerprint.similarity(sample.features, it.features)
                                    } ?: 0f
                                    val negatives = listOfNotNull(background) + confusingSounds
                                    val negativeSimilarity = negatives.maxOfOrNull { negative ->
                                        positives.maxOf { positive ->
                                            AcousticFingerprint.similarity(positive.features, negative.features)
                                        }
                                    } ?: 0f
                                    val threshold = maxOf(0.80f, negativeSimilarity + 0.04f).coerceAtMost(0.95f)
                                    testResult = if (best >= threshold) {
                                        "Match ${(best * 100).roundToInt()}%"
                                    } else {
                                        "No match ${(best * 100).roundToInt()}% (needs ${(threshold * 100).roundToInt()}%) — add a varied example"
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
