package com.quietcue.app.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val LightColors = lightColorScheme(
    primary = Color(0xFF006B5E),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF79F8E1),
    onPrimaryContainer = Color(0xFF00201B),
    secondary = Color(0xFF43637B),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFCBE6FF),
    onSecondaryContainer = Color(0xFF001E2D),
    tertiary = Color(0xFF795900),
    tertiaryContainer = Color(0xFFFFDFA0),
    error = Color(0xFFBA1A1A),
    background = Color(0xFFF6FAF9),
    onBackground = Color(0xFF171D1B),
    surface = Color(0xFFF6FAF9),
    surfaceVariant = Color(0xFFDAE5E1),
    onSurfaceVariant = Color(0xFF3F4946),
    outline = Color(0xFF6F7976),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF5ADBC5),
    onPrimary = Color(0xFF00382F),
    primaryContainer = Color(0xFF005046),
    onPrimaryContainer = Color(0xFF79F8E1),
    secondary = Color(0xFFAFCBE5),
    onSecondary = Color(0xFF123348),
    secondaryContainer = Color(0xFF2C4A61),
    onSecondaryContainer = Color(0xFFCBE6FF),
    tertiary = Color(0xFFF5BE46),
    background = Color(0xFF0F1513),
    onBackground = Color(0xFFDEE4E1),
    surface = Color(0xFF0F1513),
    surfaceVariant = Color(0xFF3F4946),
    onSurfaceVariant = Color(0xFFBEC9C5),
    outline = Color(0xFF89938F),
)

@Composable
fun QuietCueTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colors = when {
        dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            val context = LocalContext.current
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> DarkColors
        else -> LightColors
    }

    MaterialTheme(colorScheme = colors, content = content)
}
