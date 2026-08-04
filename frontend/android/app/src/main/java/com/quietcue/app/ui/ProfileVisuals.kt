package com.quietcue.app.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.DirectionsCar
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.WarningAmber
import androidx.compose.material.icons.rounded.Work
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import com.quietcue.app.domain.ProfileColor
import com.quietcue.app.domain.ProfileIcon

fun ProfileIcon.imageVector(): ImageVector = when (this) {
    ProfileIcon.HOME -> Icons.Rounded.Home
    ProfileIcon.WORK -> Icons.Rounded.Work
    ProfileIcon.DRIVE -> Icons.Rounded.DirectionsCar
    ProfileIcon.SLEEP -> Icons.Rounded.Bedtime
    ProfileIcon.EMERGENCY -> Icons.Rounded.WarningAmber
    ProfileIcon.STAR -> Icons.Rounded.Star
    ProfileIcon.HEART -> Icons.Rounded.Favorite
}

fun ProfileColor.color(): Color = when (this) {
    ProfileColor.OCEAN -> Color(0xFF246B8E)
    ProfileColor.TEAL -> Color(0xFF00796B)
    ProfileColor.AMBER -> Color(0xFF9A6500)
    ProfileColor.VIOLET -> Color(0xFF6851A3)
    ProfileColor.CORAL -> Color(0xFFB84343)
    ProfileColor.SLATE -> Color(0xFF50616B)
}
