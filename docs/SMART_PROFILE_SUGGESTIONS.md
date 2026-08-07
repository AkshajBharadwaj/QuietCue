# Smart profile suggestions

QuietCue's Android companion can associate a saved place with any alert profile.
The phone uses Android geofences to notice arrival and departure without sending
coordinates to the PC hub, Uno Q, or a cloud service.

## Product behavior

1. Open **Places** and choose **Save my current place**.
2. Name the place, select its profile, and choose a 15–500 metre boundary. New
   real places default to 150 metres for reliable phone geofencing. Boundaries
   below 100 metres remain available only for explicit simulations and experiments.
   Real places saved with the former 15-metre default migrate to 150 metres;
   demo-only places remain unchanged.
3. Grant precise location to capture the boundary. Grant **Allow all the time**
   if suggestions should arrive while QuietCue is not visible.
4. On arrival, QuietCue initially asks whether to switch profiles.
5. Choose **Always switch here** to make later arrivals automatic. Leaving an
   automatically applied place restores the profile that was active beforehand.

A manual profile choice pauses automatic changes for two hours. Arrival and
departure can still produce a reviewable suggestion during that pause. Duplicate
transition events are suppressed for five minutes.

## Privacy and power

- Place names, coordinates, radii, and decisions are stored only in Android
  DataStore on the phone. Android backup is disabled for the application.
- The hub receives the selected profile through the existing profile sync,
  including when an automatic transition occurs in the background; it never
  receives coordinates.
- QuietCue registers Android geofences instead of polling GPS continuously.
- Location is requested only from the Places feature, never at startup.
- The app remains usable when location access is declined.

Android requires precise foreground location and background location for full
geofence monitoring. On recent Android versions, the user grants background
access from the app's system settings after seeing QuietCue's explanation.
Geofence events can be delayed by the operating system, so this feature must not
control emergency-event detection or other time-critical safety behavior.
The 15-metre option is intentionally available for demonstrations; normal phone
location accuracy may not reliably distinguish adjacent rooms. Use the built-in
simulator when a deterministic transition is required.

References: [Android geofencing guide](https://developer.android.com/develop/sensors-and-location/location/geofencing),
[background location guidance](https://developer.android.com/develop/sensors-and-location/location/permissions/background).

## Hackathon demo without movement

Open **Places**, choose **Create hackathon demo place**, and tap **Test arrival**.
The Home dashboard shows a location suggestion for the Work / School profile.
Demonstrate all three choices:

- **Switch to Work / School** applies it once.
- **Always switch here** applies it and enables future automatic changes.
- **Not now** dismisses the suggestion.

After accepting an arrival, tap **Test departure** on the demo place to show the
return-profile behavior. Demo-only places contain no real coordinates and are
never registered with Android's geofencing service.

## Current boundary

This version supports named circular places and arrival/departure context. It
does not infer driving, sleep, or transit from location alone. Those contexts
should later combine explicit schedules, device state, vehicle Bluetooth, and
activity recognition, with separate permission and user-review flows.
