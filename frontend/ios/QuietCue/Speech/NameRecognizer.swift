import AVFoundation
import Foundation
import Speech

struct NameRecognizerError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// One-shot on-device speech recognition for identity voice checks; the iOS
/// version of `OnDeviceNameRecognizer`. Only the recognized text is kept.
final class NameRecognizer {
    func recognize(timeout: TimeInterval = 8) async throws -> String {
        let status = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard status == .authorized else {
            throw NameRecognizerError(message: "Speech recognition permission is required. Add pronunciation aliases manually.")
        }
        guard let recognizer = SFSpeechRecognizer(locale: Locale.current) ?? SFSpeechRecognizer(), recognizer.isAvailable else {
            throw NameRecognizerError(message: "On-device speech recognition is unavailable. Add pronunciation aliases manually.")
        }
        guard recognizer.supportsOnDeviceRecognition else {
            throw NameRecognizerError(message: "This language is not supported by the phone's on-device recognizer. Add pronunciation aliases manually.")
        }

        let engine = AVAudioEngine()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 2048, format: format) { buffer, _ in request.append(buffer) }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            throw NameRecognizerError(message: "The microphone could not capture the sample.")
        }
        defer {
            input.removeTap(onBus: 0)
            engine.stop()
        }

        let box = ResultBox()
        return try await withThrowingTaskGroup(of: String.self) { group in
            group.addTask {
                try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
                    let task = recognizer.recognitionTask(with: request) { result, error in
                        if let result {
                            box.latest = result.bestTranscription.formattedString
                            if result.isFinal, box.claim() {
                                continuation.resume(returning: result.bestTranscription.formattedString)
                            }
                        }
                        if let error, box.claim() {
                            if let latest = box.latest, !latest.isEmpty {
                                continuation.resume(returning: latest)
                            } else {
                                continuation.resume(throwing: NameRecognizerError(message: "The name was not recognized. Try speaking clearly and closer to the phone. (\(error.localizedDescription))"))
                            }
                        }
                    }
                    box.task = task
                }
            }
            group.addTask {
                try await Task.sleep(for: .seconds(timeout))
                request.endAudio()
                box.task?.finish()
                try await Task.sleep(for: .seconds(2))
                if box.claim() {
                    if let latest = box.latest, !latest.isEmpty { return latest }
                    throw NameRecognizerError(message: "No speech was heard.")
                }
                throw CancellationError()
            }
            var result: String?
            while result == nil, let next = try await group.next() { result = next }
            group.cancelAll()
            box.task?.cancel()
            let text = (result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { throw NameRecognizerError(message: "No speech was recognized.") }
            return text
        }
    }

    private final class ResultBox: @unchecked Sendable {
        private let lock = NSLock()
        private var claimed = false
        var latest: String? {
            get { lock.lock(); defer { lock.unlock() }; return _latest }
            set { lock.lock(); _latest = newValue; lock.unlock() }
        }
        private var _latest: String?
        var task: SFSpeechRecognitionTask?

        func claim() -> Bool {
            lock.lock()
            defer { lock.unlock() }
            if claimed { return false }
            claimed = true
            return true
        }
    }
}
