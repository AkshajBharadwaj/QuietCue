package com.quietcue.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.LocationOn
import androidx.compose.material.icons.rounded.RecordVoiceOver
import androidx.compose.material.icons.rounded.Save
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quietcue.app.data.ProfileJsonCodec
import com.quietcue.app.domain.ActivationRule
import com.quietcue.app.domain.ActivityContext
import com.quietcue.app.domain.AlertPriority
import com.quietcue.app.domain.AlertProfile
import com.quietcue.app.domain.HapticPattern
import com.quietcue.app.domain.HapticStrength
import com.quietcue.app.domain.ProfileColor
import com.quietcue.app.domain.ProfileIcon
import com.quietcue.app.domain.ProfileValidator
import com.quietcue.app.domain.QuietHours
import com.quietcue.app.domain.SoundRule
import com.quietcue.app.domain.SoundDefinition
import com.quietcue.app.domain.SpeechMode
import com.quietcue.app.domain.formatTime
import com.quietcue.app.domain.parseTime
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileEditorScreen(
    initialProfile: AlertProfile,
    soundLibrary: List<SoundDefinition>,
    onBack: () -> Unit,
    onSave: (AlertProfile) -> Unit,
) {
    var draftJson by rememberSaveable(initialProfile.id) {
        mutableStateOf(ProfileJsonCodec.encode(listOf(initialProfile)))
    }
    val draft = remember(draftJson) { ProfileJsonCodec.decode(draftJson).first() }
    fun updateDraft(updated: AlertProfile) {
        draftJson = ProfileJsonCodec.encode(listOf(updated))
    }

    var startTimeText by rememberSaveable(initialProfile.id) {
        mutableStateOf(formatTime(initialProfile.quietHours.startMinutes))
    }
    var endTimeText by rememberSaveable(initialProfile.id) {
        mutableStateOf(formatTime(initialProfile.quietHours.endMinutes))
    }
    val parsedStart = parseTime(startTimeText)
    val parsedEnd = parseTime(endTimeText)
    val profileForSave = if (parsedStart != null && parsedEnd != null) {
        draft.copy(quietHours = draft.quietHours.copy(startMinutes = parsedStart, endMinutes = parsedEnd))
    } else draft
    val validationErrors = ProfileValidator.validate(profileForSave, soundLibrary) + buildList {
        if (draft.quietHours.enabled && parsedStart == null) add("Use a valid quiet-hours start time, such as 10:00 PM.")
        if (draft.quietHours.enabled && parsedEnd == null) add("Use a valid quiet-hours end time, such as 7:00 AM.")
    }

    BackHandler(onBack = onBack)
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (draft.isBuiltIn) "Customize ${draft.name}" else "Edit profile") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Go back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = { onSave(profileForSave) },
                        enabled = validationErrors.isEmpty(),
                    ) {
                        Icon(Icons.Rounded.Save, contentDescription = "Save profile")
                    }
                },
            )
        },
    ) { contentPadding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = 20.dp,
                top = contentPadding.calculateTopPadding() + 8.dp,
                end = 20.dp,
                bottom = contentPadding.calculateBottomPadding() + 32.dp,
            ),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            item {
                if (draft.isBuiltIn) {
                    Text(
                        "Built-in profile • Your changes are saved locally and can be restored later.",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelLarge,
                    )
                }
            }

            item {
                EditorSection(title = "Profile details", icon = Icons.Rounded.Tune) {
                    OutlinedTextField(
                        value = draft.name,
                        onValueChange = { updateDraft(draft.copy(name = it.take(40))) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Profile name") },
                        singleLine = true,
                    )
                    OutlinedTextField(
                        value = draft.description,
                        onValueChange = { updateDraft(draft.copy(description = it.take(120))) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Description") },
                        minLines = 2,
                        supportingText = { Text("${draft.description.length}/120") },
                    )
                }
            }

            item {
                EditorSection(title = "Appearance") {
                    Text("Icon", style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ProfileIcon.entries.forEach { icon ->
                            FilterChip(
                                selected = draft.icon == icon,
                                onClick = { updateDraft(draft.copy(icon = icon)) },
                                label = { Text(icon.displayName) },
                                leadingIcon = {
                                    Icon(icon.imageVector(), contentDescription = null, modifier = Modifier.size(18.dp))
                                },
                            )
                        }
                    }
                    Text("Color", style = MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ProfileColor.entries.forEach { color ->
                            FilterChip(
                                selected = draft.color == color,
                                onClick = { updateDraft(draft.copy(color = color)) },
                                label = { Text(color.displayName) },
                                leadingIcon = {
                                    Surface(
                                        modifier = Modifier.size(16.dp),
                                        shape = CircleShape,
                                        color = color.color(),
                                    ) {}
                                },
                            )
                        }
                    }
                }
            }

            item {
                EditorSection(title = "Automatic activation", icon = Icons.Rounded.LocationOn) {
                    SwitchRow(
                        title = "Switch to this profile automatically",
                        description = "The backend will use this rule when context detection is connected.",
                        checked = draft.activation.enabled,
                        onCheckedChange = {
                            updateDraft(draft.copy(activation = draft.activation.copy(enabled = it)))
                        },
                    )
                    AnimatedVisibility(draft.activation.enabled) {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("Activity", style = MaterialTheme.typography.labelLarge)
                            OptionChips(
                                options = ActivityContext.entries,
                                selected = draft.activation.activity,
                                label = ActivityContext::displayName,
                                onSelected = {
                                    updateDraft(draft.copy(activation = draft.activation.copy(activity = it)))
                                },
                            )
                            OutlinedTextField(
                                value = draft.activation.locationLabel,
                                onValueChange = {
                                    updateDraft(
                                        draft.copy(
                                            activation = draft.activation.copy(locationLabel = it.take(60)),
                                        ),
                                    )
                                },
                                modifier = Modifier.fillMaxWidth(),
                                label = { Text("Location label (optional)") },
                                placeholder = { Text("Home, office, campus…") },
                                singleLine = true,
                            )
                        }
                    }
                }
            }

            item {
                EditorSection(title = "Quiet hours", icon = Icons.Rounded.Schedule) {
                    SwitchRow(
                        title = "Use quiet hours",
                        description = "Non-emergency alerts are suppressed during this window.",
                        checked = draft.quietHours.enabled,
                        onCheckedChange = {
                            updateDraft(draft.copy(quietHours = draft.quietHours.copy(enabled = it)))
                        },
                    )
                    AnimatedVisibility(draft.quietHours.enabled) {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedTextField(
                                    value = startTimeText,
                                    onValueChange = { startTimeText = it.take(10) },
                                    modifier = Modifier.weight(1f),
                                    label = { Text("Starts") },
                                    supportingText = if (parsedStart == null) ({ Text("Example: 10:00 PM") }) else null,
                                    isError = parsedStart == null,
                                    singleLine = true,
                                )
                                OutlinedTextField(
                                    value = endTimeText,
                                    onValueChange = { endTimeText = it.take(10) },
                                    modifier = Modifier.weight(1f),
                                    label = { Text("Ends") },
                                    supportingText = if (parsedEnd == null) ({ Text("Example: 7:00 AM") }) else null,
                                    isError = parsedEnd == null,
                                    singleLine = true,
                                )
                            }
                            Text(
                                "Emergency alerts always break through quiet hours.",
                                color = MaterialTheme.colorScheme.primary,
                                style = MaterialTheme.typography.labelLarge,
                            )
                        }
                    }
                }
            }

            item {
                EditorSection(title = "Name and phrase detection", icon = Icons.Rounded.RecordVoiceOver) {
                    Text("Speech processing", style = MaterialTheme.typography.labelLarge)
                    OptionChips(
                        options = SpeechMode.entries,
                        selected = draft.speechMode,
                        label = SpeechMode::displayName,
                        onSelected = { updateDraft(draft.copy(speechMode = it)) },
                    )
                    OutlinedTextField(
                        value = draft.phraseTriggers.joinToString(", "),
                        onValueChange = { value ->
                            updateDraft(
                                draft.copy(
                                    phraseTriggers = value.split(",").map(String::trim).filter(String::isNotEmpty),
                                ),
                            )
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Trigger phrases") },
                        placeholder = { Text("Alex, front desk, excuse me") },
                        supportingText = { Text("Separate phrases with commas. Speech processing stays separate from sound classification.") },
                        minLines = 2,
                    )
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    SectionTitle("Sounds and alerts")
                    Text(
                        "Tune each event independently. Lower thresholds are more sensitive and may create more false alerts.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            items(count = draft.soundRules.size, key = { draft.soundRules[it].soundId }) { index ->
                val rule = draft.soundRules[index]
                val sound = soundLibrary.firstOrNull { it.id == rule.soundId } ?: return@items
                SoundRuleCard(
                    rule = rule,
                    sound = sound,
                    onChange = { updatedRule ->
                        updateDraft(
                            draft.copy(
                                soundRules = draft.soundRules.map {
                                    if (it.soundId == updatedRule.soundId) updatedRule else it
                                },
                            ),
                        )
                    },
                )
            }

            if (validationErrors.isNotEmpty()) {
                item {
                    Card(
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer,
                            contentColor = MaterialTheme.colorScheme.onErrorContainer,
                        ),
                    ) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("Before saving", style = MaterialTheme.typography.titleMedium)
                            validationErrors.distinct().forEach { Text("• $it") }
                        }
                    }
                }
            }

            item {
                Button(
                    onClick = { onSave(profileForSave) },
                    enabled = validationErrors.isEmpty(),
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Icon(Icons.Rounded.Save, contentDescription = null)
                    Text(" Save profile")
                }
            }
        }
    }
}

@Composable
private fun EditorSection(
    title: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                icon?.let { Icon(it, contentDescription = null, modifier = Modifier.size(22.dp)) }
                Text(title, style = MaterialTheme.typography.titleLarge)
            }
            content()
        }
    }
}

@Composable
private fun SwitchRow(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(description, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

@Composable
private fun SoundRuleCard(
    rule: SoundRule,
    sound: SoundDefinition,
    onChange: (SoundRule) -> Unit,
) {
    var expanded by rememberSaveable(rule.soundId) { mutableStateOf(false) }
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (rule.enabled) MaterialTheme.colorScheme.surfaceContainer
            else MaterialTheme.colorScheme.surfaceContainerLow,
        ),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(sound.displayName, style = MaterialTheme.typography.titleMedium)
                        if (sound.safetyCritical) {
                            Text(
                                "SAFETY",
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Text(sound.description, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(
                    checked = rule.enabled,
                    onCheckedChange = { onChange(rule.copy(enabled = it)) },
                )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (rule.enabled) "${(rule.confidenceThreshold * 100).roundToInt()}% • ${rule.priority.displayName}"
                    else "Disabled",
                    modifier = Modifier.weight(1f),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                IconButton(onClick = { expanded = !expanded }) {
                    Icon(
                        if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                        contentDescription = if (expanded) "Hide ${sound.displayName} settings"
                        else "Show ${sound.displayName} settings",
                    )
                }
            }

            AnimatedVisibility(expanded) {
                Column(
                    modifier = Modifier.alpha(if (rule.enabled) 1f else 0.55f),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    HorizontalDivider()
                    SettingLabel(
                        "Confidence threshold",
                        "${(rule.confidenceThreshold * 100).roundToInt()}%",
                    )
                    Slider(
                        value = rule.confidenceThreshold,
                        onValueChange = { value ->
                            val stepped = (value * 20).roundToInt() / 20f
                            onChange(rule.copy(confidenceThreshold = stepped.coerceIn(0.20f, 0.95f)))
                        },
                        valueRange = 0.20f..0.95f,
                        steps = 14,
                        enabled = rule.enabled,
                    )

                    Text("Alert priority", style = MaterialTheme.typography.labelLarge)
                    OptionChips(
                        options = AlertPriority.entries,
                        selected = rule.priority,
                        label = AlertPriority::displayName,
                        enabled = rule.enabled,
                        onSelected = { priority ->
                            val recommendedPattern = when (priority) {
                                AlertPriority.INFORMATIONAL -> HapticPattern.TWO_SHORT
                                AlertPriority.ATTENTION -> HapticPattern.LONG_PULSE
                                AlertPriority.EMERGENCY -> HapticPattern.URGENT_REPEAT
                            }
                            onChange(
                                rule.copy(
                                    priority = priority,
                                    hapticPattern = recommendedPattern,
                                    requiresAcknowledgement = priority == AlertPriority.EMERGENCY,
                                ),
                            )
                        },
                    )

                    Text("Haptic pattern", style = MaterialTheme.typography.labelLarge)
                    OptionChips(
                        options = HapticPattern.entries,
                        selected = rule.hapticPattern,
                        label = HapticPattern::displayName,
                        enabled = rule.enabled,
                        onSelected = { onChange(rule.copy(hapticPattern = it)) },
                    )

                    Text("Haptic strength", style = MaterialTheme.typography.labelLarge)
                    OptionChips(
                        options = HapticStrength.entries,
                        selected = rule.hapticStrength,
                        label = HapticStrength::displayName,
                        enabled = rule.enabled,
                        onSelected = { onChange(rule.copy(hapticStrength = it)) },
                    )

                    SwitchRow(
                        title = "Require acknowledgement",
                        description = "Keep the alert visible until the user confirms it.",
                        checked = rule.requiresAcknowledgement,
                        onCheckedChange = { onChange(rule.copy(requiresAcknowledgement = it)) },
                    )

                    SettingLabel("Repeat cooldown", "${rule.cooldownSeconds} seconds")
                    Slider(
                        value = rule.cooldownSeconds.toFloat(),
                        onValueChange = { onChange(rule.copy(cooldownSeconds = it.roundToInt())) },
                        valueRange = 0f..120f,
                        steps = 23,
                        enabled = rule.enabled,
                    )
                }
            }
        }
    }
}

@Composable
private fun SettingLabel(title: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title, style = MaterialTheme.typography.labelLarge)
        Text(value, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun <T> OptionChips(
    options: List<T>,
    selected: T,
    label: (T) -> String,
    enabled: Boolean = true,
    onSelected: (T) -> Unit,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            FilterChip(
                selected = option == selected,
                onClick = { onSelected(option) },
                label = { Text(label(option)) },
                enabled = enabled,
            )
        }
    }
}
