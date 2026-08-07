# Identity enrollment and manual context

QuietCue's **My context** tab lets a user deliberately teach the local speech
pipeline the names and details that are useful to them. It is a manual memory
bank, not a conversation recorder or an automatic memory generator.

## Included features

- A primary user name, pronunciation guide, and aliases.
- Up to three optional on-device voice checks. The app stores only the recognized
  text and never the enrollment recording.
- Manually entered people with relationship, pronunciation, aliases, and notes.
- Manually entered context such as places, routines, classes, or projects.
- Encrypted speech settings: master switch, on-device model, sensitivity,
  identity/people audiences, and global phrases.
- Edit, individual delete, and delete-everything controls.
- AES-GCM encryption using a non-exportable Android Keystore key.

There is intentionally no suggested-memory queue, background memory extraction,
or automatic approval path.

## Runtime behavior

The Android app synchronizes the approved bank alongside the active profile.
The inference hub keeps that synchronized context in its runtime profile:

- The enrolled user's name, pronunciation, aliases, and approved voice-check
  phrases can trigger `name_called`.
- Other people's names and aliases are transcription hotwords by default. They
  trigger `name_called` only after the user enables the explicit people audience.
- Manual context is included in the bounded local Faster-Whisper prompt on the
  computer. The phone's ONNX path ships without prompt/BPE conditioning and uses
  fuzzy matching over approved trigger phrases.
- The environmental classifier is unchanged and does not depend on memory data.

The prompt is capped at 800 characters. The sync decoder also bounds settings,
field lengths, sensitivity, phrase counts, and no more than 50 people and 50
context entries.

## Voice-check privacy and availability

On Android 12 and newer, QuietCue uses only
`SpeechRecognizer.createOnDeviceSpeechRecognizer`. It does not fall back to the
network recognizer. Some phones require an offline speech-language pack; when it
is missing, the user can install it through phone settings or enter aliases
manually.

## Storage and transport boundary

- Android persistence is encrypted at rest with AES-GCM and Android Keystore.
- Android backup is disabled for the application.
- Raw enrollment and Uno Q audio are not written by this feature.
- The current companion integration sends context through the loopback state API
  (`127.0.0.1`), normally reached through `adb reverse` during development.
- The hub does not persist the bank to disk; it holds the latest synchronized copy
  in memory for local inference.

Before allowing a phone to connect to a remote hub directly, replace the current
development HTTP transport with authenticated encryption such as TLS.
