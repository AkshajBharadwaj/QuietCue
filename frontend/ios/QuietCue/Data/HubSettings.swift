import Foundation
import UIKit

/// Where the Mac hub lives. The Android app reaches it through `adb reverse`
/// on localhost; the iPhone needs the Mac's LAN address instead.
struct HubSettings: Codable, Equatable {
    var host: String = ""
    var audioPort: UInt16 = 8765
    var statePort: UInt16 = 8787
    var pairingToken: String = ""
    var deviceId: String = "iphone-\(UIDevice.current.name.lowercased().replacingOccurrences(of: " ", with: "-").prefix(24))"

    var stateBaseURL: URL? {
        guard !host.isEmpty else { return nil }
        return URL(string: "http://\(host):\(statePort)")
    }

    private static let key = "quietcue.hub.settings"

    static func load() -> HubSettings {
        var settings = HubSettings()
        if let data = UserDefaults.standard.data(forKey: key),
           let decoded = try? JSONDecoder().decode(HubSettings.self, from: data) {
            settings = decoded
        }
        // Development override so the simulator can be launched pre-pointed at
        // a hub: SIMCTL_CHILD_QUIETCUE_HUB_HOST=127.0.0.1 xcrun simctl launch ...
        let environment = ProcessInfo.processInfo.environment
        if let host = environment["QUIETCUE_HUB_HOST"], !host.isEmpty { settings.host = host }
        if let token = environment["QUIETCUE_PAIRING_TOKEN"] { settings.pairingToken = token }
        return settings
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: Self.key)
        }
    }
}
