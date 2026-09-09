import Foundation

struct CapturedFingerprint: Equatable, Hashable {
    var features: [Float]
    var rmsDbfs: Float
}

struct EnrollmentCapture: Equatable {
    var positives: [CapturedFingerprint]
    var background: CapturedFingerprint
    var speechRejectedMs: Int = 0
}

struct EnrollmentError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

enum AcousticFingerprint {
    static let sampleRate = 16_000
    static let featureCount = 8
    static let minPositiveSamples = 3
    static let recommendedPositiveSamples = 6
    static let maxPositiveSamples = 30
    static let frequencies = [250, 375, 500, 750, 1_000, 1_500, 2_000, 3_000]
    private static let minRepeatSimilarity: Float = 0.86

    static func fromPcm16(_ samples: [Int16]) -> CapturedFingerprint {
        precondition(!samples.isEmpty, "Cannot fingerprint empty audio")
        let sumSquares = samples.reduce(0.0) { $0 + Double($1) * Double($1) }
        let rms = (sumSquares / Double(samples.count)).squareRoot() / 32768.0
        let amplitudes = frequencies.map { goertzelAmplitude(samples, frequency: $0) }
        let norm = max(amplitudes.reduce(0.0) { $0 + $1 * $1 }.squareRoot(), 1e-12)
        return CapturedFingerprint(
            features: amplitudes.map { Float($0 / norm) },
            rmsDbfs: Float(20.0 * log10(max(rms, 1e-9)))
        )
    }

    static func similarity(_ left: [Float], _ right: [Float]) -> Float {
        guard left.count == featureCount, right.count == featureCount else { return 0 }
        var dot = 0.0, leftNorm = 0.0, rightNorm = 0.0
        for index in 0..<featureCount {
            dot += Double(left[index]) * Double(right[index])
            leftNorm += Double(left[index]) * Double(left[index])
            rightNorm += Double(right[index]) * Double(right[index])
        }
        let value = dot / max(leftNorm.squareRoot() * rightNorm.squareRoot(), 1e-12)
        return Float(min(max(value, 0), 1))
    }

    static func matchConfidence(_ candidate: [Float], enrollment: SoundEnrollment) -> Float? {
        let references = enrollment.prototypes.isEmpty ? [enrollment.prototype] : enrollment.prototypes
        let similarities = references.map { similarity(candidate, $0) }.sorted(by: >)
        guard let best = similarities.first, best >= enrollment.similarityThreshold else { return nil }
        if enrollment.matcherVersion >= 4 && similarities.count >= minPositiveSamples {
            let tolerance: Float = 0.04
            if similarities[1] < enrollment.similarityThreshold - tolerance ||
                similarity(candidate, enrollment.prototype) < enrollment.similarityThreshold - tolerance {
                return nil
            }
        }
        return best
    }

    static func enroll(
        name: String,
        description: String,
        priority: AlertPriority,
        positives: [CapturedFingerprint],
        background: CapturedFingerprint,
        nowMs: Int64 = nowEpochMs(),
        confusingSounds: [CapturedFingerprint] = []
    ) throws -> SoundDefinition {
        guard (minPositiveSamples...maxPositiveSamples).contains(positives.count) else {
            throw EnrollmentError(message: "Record between \(minPositiveSamples) and \(maxPositiveSamples) examples")
        }
        guard positives.allSatisfy({ $0.rmsDbfs >= -50 }) else {
            throw EnrollmentError(message: "One recording is too quiet; record it again")
        }
        let averaged = (0..<featureCount).map { index in
            positives.map { Double($0.features[index]) }.reduce(0, +) / Double(positives.count)
        }
        let norm = max(averaged.reduce(0.0) { $0 + $1 * $1 }.squareRoot(), 1e-12)
        let prototype = averaged.map { Float($0 / norm) }
        let consistent = positives.filter { similarity($0.features, prototype) >= minRepeatSimilarity }.count
        guard consistent >= minPositiveSamples else {
            throw EnrollmentError(message: "The examples are too different; teach the same sound at least three times")
        }
        let negatives = [background] + confusingSounds
        let backgroundSimilarity = negatives.map { negative in
            positives.map { similarity($0.features, negative.features) }.max() ?? 0
        }.max() ?? 0
        guard backgroundSimilarity < 0.90 else {
            throw EnrollmentError(message: "A background or confusing sound is too similar to an example; replace that recording")
        }
        let threshold = min(max(0.93, backgroundSimilarity + 0.08), 0.98)
        let pattern: HapticPattern
        switch priority {
        case .informational: pattern = .twoShort
        case .attention: pattern = .longPulse
        case .emergency: pattern = .urgentRepeat
        }
        let trimmedDescription = description.trimmingCharacters(in: .whitespacesAndNewlines)
        return SoundDefinition(
            id: "custom:\(UUID().uuidString.lowercased())",
            displayName: name.trimmingCharacters(in: .whitespacesAndNewlines),
            descriptionText: trimmedDescription.isEmpty ? "Sound enrolled with the phone microphone" : trimmedDescription,
            safetyCritical: priority == .emergency,
            defaultPriority: priority,
            defaultHapticPattern: pattern,
            defaultHapticStrength: priority == .emergency ? .strong : .standard,
            defaultRequiresAcknowledgement: priority == .emergency,
            enrollment: SoundEnrollment(
                prototype: prototype,
                prototypes: positives.map(\.features),
                sampleRmsDbfs: positives.map(\.rmsDbfs),
                similarityThreshold: threshold,
                positiveSampleCount: positives.count,
                backgroundSimilarity: backgroundSimilarity,
                createdAtEpochMs: nowMs,
                matcherVersion: 4
            )
        )
    }

    private static func goertzelAmplitude(_ samples: [Int16], frequency: Int) -> Double {
        let coefficient = 2.0 * cos(2.0 * Double.pi * Double(frequency) / Double(sampleRate))
        var previous = 0.0
        var previousPrevious = 0.0
        for sample in samples {
            let current = Double(sample) + coefficient * previous - previousPrevious
            previousPrevious = previous
            previous = current
        }
        let power = previousPrevious * previousPrevious + previous * previous - coefficient * previous * previousPrevious
        return 2.0 * max(0.0, power).squareRoot() / Double(samples.count)
    }
}
