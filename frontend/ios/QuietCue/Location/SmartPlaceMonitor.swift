import CoreLocation
import Foundation

enum GeofenceRegistrationStatus {
    case active, noPlaces, permissionRequired, registrationFailed
}

/// Core Location region monitoring for saved places (the iPhone version of the
/// Android geofence manager). Coordinates never leave the phone.
@MainActor
final class SmartPlaceMonitor: NSObject, CLLocationManagerDelegate {
    enum Permission {
        case notDetermined, denied, whenInUse, always

        var hasPrecise: Bool { self == .whenInUse || self == .always }
        var hasBackground: Bool { self == .always }
    }

    private let manager = CLLocationManager()
    private var locationContinuation: CheckedContinuation<CLLocationCoordinate2D, Error>?
    private var monitoredPlaces: [String: SmartPlace] = [:]
    var onTransition: ((String, PlaceTransition) -> Void)?
    var onPermissionChange: (() -> Void)?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.allowsBackgroundLocationUpdates = false
    }

    var permission: Permission {
        switch manager.authorizationStatus {
        case .notDetermined: return .notDetermined
        case .authorizedAlways: return .always
        case .authorizedWhenInUse: return .whenInUse
        default: return .denied
        }
    }

    var precisionIsFull: Bool { manager.accuracyAuthorization == .fullAccuracy }

    func requestWhenInUseAuthorization() {
        manager.requestWhenInUseAuthorization()
    }

    func requestAlwaysAuthorization() {
        if manager.authorizationStatus == .notDetermined {
            manager.requestWhenInUseAuthorization()
        } else {
            manager.requestAlwaysAuthorization()
        }
    }

    func refresh(places: [SmartPlace]) -> GeofenceRegistrationStatus {
        for region in manager.monitoredRegions { manager.stopMonitoring(for: region) }
        monitoredPlaces = [:]
        guard permission.hasPrecise, precisionIsFull else { return .permissionRequired }
        let real = places.filter { $0.enabled && !$0.demoOnly }
        guard !real.isEmpty else { return .noPlaces }
        guard permission.hasBackground else { return .permissionRequired }
        guard CLLocationManager.isMonitoringAvailable(for: CLCircularRegion.self) else { return .registrationFailed }
        for place in real.prefix(20) {
            let region = CLCircularRegion(
                center: CLLocationCoordinate2D(latitude: place.latitude, longitude: place.longitude),
                radius: CLLocationDistance(place.radiusMeters),
                identifier: place.id
            )
            region.notifyOnEntry = true
            region.notifyOnExit = true
            manager.startMonitoring(for: region)
            monitoredPlaces[place.id] = place
        }
        return .active
    }

    func captureCurrentLocation() async throws -> CLLocationCoordinate2D {
        guard permission.hasPrecise else { throw StoreError(message: "Allow precise location access first") }
        if let recent = manager.location, recent.timestamp.timeIntervalSinceNow > -30 {
            return recent.coordinate
        }
        return try await withCheckedThrowingContinuation { continuation in
            locationContinuation = continuation
            manager.requestLocation()
        }
    }

    static func containingPlace(_ places: [SmartPlace], latitude: Double, longitude: Double) -> SmartPlace? {
        let here = CLLocation(latitude: latitude, longitude: longitude)
        return places
            .map { place -> (SmartPlace, Double) in
                let distance = here.distance(from: CLLocation(latitude: place.latitude, longitude: place.longitude))
                return (place, distance - Double(place.radiusMeters))
            }
            .filter { $0.1 <= 0 }
            .min { $0.1 < $1.1 }?
            .0
    }

    // MARK: CLLocationManagerDelegate

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in self.onPermissionChange?() }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let coordinate = locations.last?.coordinate else { return }
        Task { @MainActor in
            self.locationContinuation?.resume(returning: coordinate)
            self.locationContinuation = nil
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.locationContinuation?.resume(throwing: StoreError(message: "Could not determine the current location"))
            self.locationContinuation = nil
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didEnterRegion region: CLRegion) {
        Task { @MainActor in self.onTransition?(region.identifier, .enter) }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didExitRegion region: CLRegion) {
        Task { @MainActor in self.onTransition?(region.identifier, .exit) }
    }
}
