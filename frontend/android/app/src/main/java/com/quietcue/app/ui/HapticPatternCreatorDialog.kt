package com.quietcue.app.ui

import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quietcue.app.domain.CustomHapticPattern
import com.quietcue.app.domain.CustomHapticStep

@Composable
internal fun HapticPatternCreatorDialog(
    existing: CustomHapticPattern?,
    onDismiss: () -> Unit,
    onSave: (CustomHapticPattern) -> Unit,
) {
    val context = LocalContext.current
    var name by remember(existing) { mutableStateOf(existing?.name ?: "My pattern") }
    var steps by remember(existing) { mutableStateOf(existing?.steps.orEmpty()) }
    var lastReleaseAt by remember(existing) { mutableStateOf<Long?>(null) }
    var pressing by remember { mutableStateOf(false) }
    val pattern = CustomHapticPattern(name.trim(), steps)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Create a vibration") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(
                    "Hold the pad while the motor should buzz, then release for a pause. " +
                        "Repeat to record up to ${CustomHapticPattern.MAX_STEPS} pulses.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(30) },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Pattern name") },
                    singleLine = true,
                )
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(150.dp)
                        .clip(RoundedCornerShape(20.dp))
                        .background(
                            if (pressing) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.primaryContainer,
                        )
                        .semantics {
                            contentDescription = "Touch and hold to record a vibration pulse"
                        }
                        .pointerInput(steps.size) {
                            detectTapGestures(
                                onPress = {
                                    if (steps.size < CustomHapticPattern.MAX_STEPS) {
                                        val pressedAt = SystemClock.elapsedRealtime()
                                        lastReleaseAt?.let { releasedAt ->
                                            if (steps.isNotEmpty()) {
                                                val gap = (pressedAt - releasedAt).toInt().coerceIn(
                                                    CustomHapticStep.MIN_OFF_MS,
                                                    CustomHapticStep.MAX_PHASE_MS,
                                                )
                                                steps = steps.dropLast(1) + steps.last().copy(offMs = gap)
                                            }
                                        }
                                        pressing = true
                                        val released = tryAwaitRelease()
                                        val releasedAt = SystemClock.elapsedRealtime()
                                        pressing = false
                                        if (released) {
                                            val onMs = (releasedAt - pressedAt).toInt().coerceIn(
                                                CustomHapticStep.MIN_ON_MS,
                                                CustomHapticStep.MAX_PHASE_MS,
                                            )
                                            steps = steps + CustomHapticStep(
                                                onMs = onMs,
                                                offMs = 200,
                                            )
                                            lastReleaseAt = releasedAt
                                        }
                                    }
                                },
                            )
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        when {
                            pressing -> "BUZZ"
                            steps.size >= CustomHapticPattern.MAX_STEPS -> "6 pulses recorded"
                            else -> "PRESS + HOLD"
                        },
                        color = if (pressing) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onPrimaryContainer,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
                if (steps.isEmpty()) {
                    Text("No pulses recorded yet", style = MaterialTheme.typography.labelLarge)
                } else {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        steps.forEachIndexed { index, step ->
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = MaterialTheme.colorScheme.secondaryContainer,
                            ) {
                                Text(
                                    "${index + 1}: ${step.onMs} ms",
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 6.dp),
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            }
                        }
                    }
                    Text(
                        "${steps.size} pulse${if (steps.size == 1) "" else "s"} • " +
                            "${pattern.totalDurationMs / 1_000f} seconds",
                        color = if (pattern.totalDurationMs > CustomHapticPattern.MAX_TOTAL_MS) {
                            MaterialTheme.colorScheme.error
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        style = MaterialTheme.typography.bodySmall,
                    )
                    if (pattern.totalDurationMs > CustomHapticPattern.MAX_TOTAL_MS) {
                        Text(
                            "Keep the full pattern under 10 seconds.",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                }
                Button(
                    onClick = { previewPattern(context, pattern) },
                    enabled = pattern.isValid(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Preview on phone")
                }
                TextButton(
                    onClick = {
                        steps = emptyList()
                        lastReleaseAt = null
                        pressing = false
                    },
                    enabled = steps.isNotEmpty(),
                    modifier = Modifier.align(Alignment.CenterHorizontally),
                ) {
                    Text("Clear and record again")
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(pattern) }, enabled = pattern.isValid()) {
                Text("Use pattern")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

private fun previewPattern(context: Context, pattern: CustomHapticPattern) {
    if (!pattern.isValid()) return
    val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        context.getSystemService(VibratorManager::class.java)?.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    } ?: return
    if (!vibrator.hasVibrator()) return

    val timing = buildList {
        add(0L)
        pattern.steps.forEach { step ->
            add(step.onMs.toLong())
            add(step.offMs.toLong())
        }
    }.toLongArray()
    vibrator.vibrate(VibrationEffect.createWaveform(timing, -1))
}
