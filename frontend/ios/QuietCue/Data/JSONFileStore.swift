import Foundation

/// Small Codable-to-disk helper. Files live in Application Support and are
/// protected with iOS data protection (encrypted at rest once the device has a
/// passcode), the iPhone counterpart of Android's encrypted preferences.
struct JSONFileStore<Value: Codable> {
    let url: URL
    let protection: FileProtectionType

    init(fileName: String, protection: FileProtectionType = .completeUntilFirstUserAuthentication) {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("QuietCue", isDirectory: true)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        self.url = base.appendingPathComponent(fileName)
        self.protection = protection
    }

    func load() -> Value? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(Value.self, from: data)
    }

    func save(_ value: Value) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        try? data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try? FileManager.default.setAttributes([.protectionKey: protection], ofItemAtPath: url.path)
    }

    func delete() {
        try? FileManager.default.removeItem(at: url)
    }
}
