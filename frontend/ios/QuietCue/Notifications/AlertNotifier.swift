import Foundation
import UserNotifications

/// Local notifications for detected alerts with an acknowledge action, the
/// iOS version of `AlertNotificationManager` + `AlertAcknowledgeReceiver`.
final class AlertNotifier: NSObject, UNUserNotificationCenterDelegate {
    static let categoryId = "quietcue_alert"
    static let stopActionId = "quietcue_stop_haptic"

    var onAcknowledge: ((String) -> Void)?
    private var center: UNUserNotificationCenter?
    private var enabled = false

    /// Registers the category, becomes the delegate, and asks for permission.
    /// Nothing touches the notification center until this is called.
    func activate() {
        guard center == nil else { return }
        let center = UNUserNotificationCenter.current()
        self.center = center
        center.delegate = self
        let stop = UNNotificationAction(identifier: Self.stopActionId, title: "Acknowledge & stop", options: [.foreground])
        let category = UNNotificationCategory(identifier: Self.categoryId, actions: [stop], intentIdentifiers: [], options: [])
        center.setNotificationCategories([category])
        center.requestAuthorization(options: [.alert, .sound, .badge]) { [weak self] granted, _ in
            self?.enabled = granted
        }
    }

    func notify(_ alert: DetectedAlert) {
        guard let center, enabled else { return }
        let urgent = alert.requiresAcknowledgement || alert.category == "emergency"
        let content = UNMutableNotificationContent()
        content.title = "\(alert.displayName) detected"
        let urgency: String
        switch alert.category {
        case "emergency": urgency = "Emergency"
        case "attention": urgency = "Attention"
        default: urgency = "Informational"
        }
        content.body = "\(urgency) alert in \(alert.profileName) • \(Int(alert.confidence * 100))% confidence • \(alert.totalLatencyMs) ms"
        content.sound = urgent ? .defaultCritical : .default
        content.interruptionLevel = urgent ? .timeSensitive : .active
        content.categoryIdentifier = alert.hapticActive ? Self.categoryId : ""
        content.userInfo = ["event_id": alert.eventId]
        center.add(UNNotificationRequest(identifier: alert.eventId, content: content, trigger: nil))
    }

    func notifySmartPlace(title: String, body: String) {
        guard let center, enabled else { return }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        center.add(UNNotificationRequest(identifier: "smart-place-\(UUID().uuidString)", content: content, trigger: nil))
    }

    func cancel(eventId: String) {
        center?.removeDeliveredNotifications(withIdentifiers: [eventId])
        center?.removePendingNotificationRequests(withIdentifiers: [eventId])
    }

    // MARK: UNUserNotificationCenterDelegate

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        if response.actionIdentifier == Self.stopActionId,
           let eventId = response.notification.request.content.userInfo["event_id"] as? String {
            onAcknowledge?(eventId)
        }
        completionHandler()
    }
}
