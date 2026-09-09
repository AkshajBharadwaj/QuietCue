import SwiftUI

/// Material 3 color roles, taken from the Android app's `Theme.kt`. The
/// Android screenshots show Samsung's wallpaper-derived dynamic palette; iOS
/// has no equivalent, so the app's own teal palette is used everywhere.
struct MaterialScheme {
    var primary: Color
    var onPrimary: Color
    var primaryContainer: Color
    var onPrimaryContainer: Color
    var secondary: Color
    var onSecondary: Color
    var secondaryContainer: Color
    var onSecondaryContainer: Color
    var tertiary: Color
    var tertiaryContainer: Color
    var onTertiaryContainer: Color
    var error: Color
    var errorContainer: Color
    var onErrorContainer: Color
    var background: Color
    var onBackground: Color
    var surface: Color
    var onSurface: Color
    var surfaceVariant: Color
    var onSurfaceVariant: Color
    var surfaceContainerLow: Color
    var surfaceContainer: Color
    var surfaceContainerHigh: Color
    var outline: Color
    var outlineVariant: Color
    var inverseSurface: Color
    var inverseOnSurface: Color

    static let light = MaterialScheme(
        primary: Color(hex: 0x006B5E),
        onPrimary: .white,
        primaryContainer: Color(hex: 0x79F8E1),
        onPrimaryContainer: Color(hex: 0x00201B),
        secondary: Color(hex: 0x43637B),
        onSecondary: .white,
        secondaryContainer: Color(hex: 0xCBE6FF),
        onSecondaryContainer: Color(hex: 0x001E2D),
        tertiary: Color(hex: 0x795900),
        tertiaryContainer: Color(hex: 0xFFDFA0),
        onTertiaryContainer: Color(hex: 0x261900),
        error: Color(hex: 0xBA1A1A),
        errorContainer: Color(hex: 0xFFDAD6),
        onErrorContainer: Color(hex: 0x410002),
        background: Color(hex: 0xF6FAF9),
        onBackground: Color(hex: 0x171D1B),
        surface: Color(hex: 0xF6FAF9),
        onSurface: Color(hex: 0x171D1B),
        surfaceVariant: Color(hex: 0xDAE5E1),
        onSurfaceVariant: Color(hex: 0x3F4946),
        surfaceContainerLow: Color(hex: 0xF0F4F3),
        surfaceContainer: Color(hex: 0xEAEFED),
        surfaceContainerHigh: Color(hex: 0xE4E9E7),
        outline: Color(hex: 0x6F7976),
        outlineVariant: Color(hex: 0xBEC9C5),
        inverseSurface: Color(hex: 0x2C3230),
        inverseOnSurface: Color(hex: 0xEDF2EF)
    )

    static let dark = MaterialScheme(
        primary: Color(hex: 0x5ADBC5),
        onPrimary: Color(hex: 0x00382F),
        primaryContainer: Color(hex: 0x005046),
        onPrimaryContainer: Color(hex: 0x79F8E1),
        secondary: Color(hex: 0xAFCBE5),
        onSecondary: Color(hex: 0x123348),
        secondaryContainer: Color(hex: 0x2C4A61),
        onSecondaryContainer: Color(hex: 0xCBE6FF),
        tertiary: Color(hex: 0xF5BE46),
        tertiaryContainer: Color(hex: 0x5C4200),
        onTertiaryContainer: Color(hex: 0xFFDFA0),
        error: Color(hex: 0xFFB4AB),
        errorContainer: Color(hex: 0x93000A),
        onErrorContainer: Color(hex: 0xFFDAD6),
        background: Color(hex: 0x0F1513),
        onBackground: Color(hex: 0xDEE4E1),
        surface: Color(hex: 0x0F1513),
        onSurface: Color(hex: 0xDEE4E1),
        surfaceVariant: Color(hex: 0x3F4946),
        onSurfaceVariant: Color(hex: 0xBEC9C5),
        surfaceContainerLow: Color(hex: 0x171D1B),
        surfaceContainer: Color(hex: 0x1B2220),
        surfaceContainerHigh: Color(hex: 0x252C2A),
        outline: Color(hex: 0x89938F),
        outlineVariant: Color(hex: 0x3F4946),
        inverseSurface: Color(hex: 0xDEE4E1),
        inverseOnSurface: Color(hex: 0x2C3230)
    )
}

private struct MaterialSchemeKey: EnvironmentKey {
    static let defaultValue = MaterialScheme.light
}

extension EnvironmentValues {
    var scheme: MaterialScheme {
        get { self[MaterialSchemeKey.self] }
        set { self[MaterialSchemeKey.self] = newValue }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

/// Material 3 type scale.
enum MaterialType {
    static let headlineMedium = Font.system(size: 28, weight: .regular)
    static let headlineSmall = Font.system(size: 24, weight: .regular)
    static let titleLarge = Font.system(size: 22, weight: .regular)
    static let titleMedium = Font.system(size: 16, weight: .medium)
    static let titleSmall = Font.system(size: 14, weight: .medium)
    static let bodyLarge = Font.system(size: 16, weight: .regular)
    static let bodyMedium = Font.system(size: 14, weight: .regular)
    static let bodySmall = Font.system(size: 12, weight: .regular)
    static let labelLarge = Font.system(size: 14, weight: .medium)
    static let labelMedium = Font.system(size: 12, weight: .medium)
    static let labelSmall = Font.system(size: 11, weight: .medium)
}

extension ProfileColor {
    var color: Color {
        switch self {
        case .ocean: return Color(hex: 0x246B8E)
        case .teal: return Color(hex: 0x00796B)
        case .amber: return Color(hex: 0x9A6500)
        case .violet: return Color(hex: 0x6851A3)
        case .coral: return Color(hex: 0xB84343)
        case .slate: return Color(hex: 0x50616B)
        }
    }
}

extension ProfileIcon {
    var symbolName: String {
        switch self {
        case .home: return "house.fill"
        case .work: return "briefcase.fill"
        case .drive: return "car.fill"
        case .sleep: return "moon.fill"
        case .emergency: return "exclamationmark.triangle.fill"
        case .star: return "star.fill"
        case .heart: return "heart.fill"
        }
    }
}
