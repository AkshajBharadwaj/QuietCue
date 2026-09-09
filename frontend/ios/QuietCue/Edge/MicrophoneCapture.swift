import AVFoundation
import Foundation

struct AudioChunk {
    var sequence: Int
    var capturedAtMs: Int64
    var samples: [Int16]

    static let sampleRate = 16_000

    var pcm: Data {
        samples.withUnsafeBufferPointer { Data(buffer: $0) }  // iOS is little-endian: pcm_s16le.
    }

    var durationMs: Int { Int((Double(samples.count) * 1_000 / Double(Self.sampleRate)).rounded()) }

    func toWire() -> [String: Any] {
        [
            "sequence": sequence,
            "captured_at_ms": capturedAtMs,
            "sample_rate": Self.sampleRate,
            "channels": 1,
            "encoding": "pcm_s16le",
            "duration_ms": durationMs,
        ]
    }
}

struct MicrophoneError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// Captures the phone microphone and hands out 16 kHz mono PCM16 chunks, the
/// same bytes the Uno Q ALSA source produces. Raw audio is never written to disk.
final class MicrophoneCapture {
    private let engine = AVAudioEngine()
    private let chunkMs: Int
    private var converter: AVAudioConverter?
    private var pending: [Int16] = []
    private var sequence = 0
    private let lock = NSLock()
    private var continuation: AsyncStream<AudioChunk>.Continuation?

    init(chunkMs: Int = 1_000) {
        self.chunkMs = chunkMs
    }

    static func requestPermission() async -> Bool {
        if #available(iOS 17.0, *) {
            return await AVAudioApplication.requestRecordPermission()
        } else {
            return await withCheckedContinuation { continuation in
                AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
            }
        }
    }

    /// Starts capture and returns the chunk stream. Only the newest few chunks
    /// are buffered so a slow hub never builds up unbounded latency.
    func start() throws -> AsyncStream<AudioChunk> {
        let session = AVAudioSession.sharedInstance()
        // `.default` rather than `.measurement`: the haptic engine sets
        // `playsHapticsOnly`, so it shares this session instead of owning one, and
        // `.measurement` strips the output path that Core Haptics plays through —
        // patterns then start without error but never reach the Taptic Engine.
        try session.setCategory(.playAndRecord, mode: .default, options: [.mixWithOthers, .allowBluetoothHFP, .defaultToSpeaker])
        // iOS silences every haptic (Core Haptics included) while a session is
        // recording unless the app opts in. Without this the Taptic Engine stays
        // quiet for previews and detections the whole time the mic is streaming.
        try session.setAllowHapticsAndSystemSoundsDuringRecording(true)
        try session.setActive(true)

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw MicrophoneError(message: "No microphone input is available")
        }
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: Double(AudioChunk.sampleRate),
            channels: 1,
            interleaved: true
        ), let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            throw MicrophoneError(message: "Could not configure 16 kHz mono capture")
        }
        self.converter = converter
        pending.removeAll()
        sequence = 0

        let stream = AsyncStream<AudioChunk>(bufferingPolicy: .bufferingNewest(4)) { continuation in
            self.continuation = continuation
        }
        let samplesPerChunk = AudioChunk.sampleRate * chunkMs / 1_000
        input.installTap(onBus: 0, bufferSize: 4096, format: inputFormat) { [weak self] buffer, _ in
            self?.handle(buffer: buffer, targetFormat: targetFormat, samplesPerChunk: samplesPerChunk)
        }
        engine.prepare()
        try engine.start()
        return stream
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        continuation?.finish()
        continuation = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func handle(buffer: AVAudioPCMBuffer, targetFormat: AVAudioFormat, samplesPerChunk: Int) {
        guard let converter else { return }
        let ratio = targetFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 16
        guard let output = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return }
        var consumed = false
        var conversionError: NSError?
        converter.convert(to: output, error: &conversionError) { _, status in
            if consumed {
                status.pointee = .noDataNow
                return nil
            }
            consumed = true
            status.pointee = .haveData
            return buffer
        }
        guard conversionError == nil, output.frameLength > 0, let channel = output.int16ChannelData else { return }
        let converted = Array(UnsafeBufferPointer(start: channel[0], count: Int(output.frameLength)))

        lock.lock()
        pending.append(contentsOf: converted)
        var ready: [AudioChunk] = []
        while pending.count >= samplesPerChunk {
            let chunk = AudioChunk(
                sequence: sequence,
                capturedAtMs: Int64(Date().timeIntervalSince1970 * 1_000),
                samples: Array(pending.prefix(samplesPerChunk))
            )
            pending.removeFirst(samplesPerChunk)
            sequence += 1
            ready.append(chunk)
        }
        lock.unlock()
        for chunk in ready { continuation?.yield(chunk) }
    }
}
