import Foundation

/// Cheap first-pass analysis attached to every chunk. Port of
/// `uno_q/linux/audio_capture/edge_analyzer.py`; emits candidates only, never
/// safety decisions.
struct EdgeAnalysis {
    var rmsDbfs: Float
    var peakDbfs: Float
    var voiceActivity: Bool
    var voiceProbability: Float
    var dominantToneHz: Int?
    var toneMarginDb: Float?
    var candidates: [(kind: String, confidence: Float)]

    func toWire() -> [String: Any] {
        [
            "rms_dbfs": rmsDbfs,
            "peak_dbfs": peakDbfs,
            "voice_activity": voiceActivity,
            "voice_probability": voiceProbability,
            "dominant_tone_hz": dominantToneHz as Any? ?? NSNull(),
            "tone_margin_db": toneMarginDb as Any? ?? NSNull(),
            "candidates": candidates.map { ["kind": $0.kind, "confidence": $0.confidence] },
        ]
    }
}

struct EdgeAnalyzer {
    private static let toneFrequencies = [600, 800, 1000, 1250, 1600, 2000, 2500, 3150]
    let sampleRate: Int

    init(sampleRate: Int = 16_000) {
        self.sampleRate = sampleRate
    }

    func analyze(_ samples: [Int16]) -> EdgeAnalysis {
        precondition(!samples.isEmpty)
        var sumSquares = 0.0
        var peakValue = 0
        for sample in samples {
            sumSquares += Double(sample) * Double(sample)
            peakValue = max(peakValue, abs(Int(sample)))
        }
        let rms = (sumSquares / Double(samples.count)).squareRoot() / 32768.0
        let peak = Double(peakValue) / 32768.0
        let rmsDbfs = toDbfs(rms)
        let peakDbfs = toDbfs(peak)

        let (dominant, toneDbfs) = dominantTone(samples)
        let toneMargin: Double? = dominant != nil ? toneDbfs - rmsDbfs : nil
        let voiceProbability = self.voiceProbability(samples, overallDbfs: rmsDbfs)
        let voiceActivity = voiceProbability >= 0.30 && rmsDbfs >= -42.0 && (toneMargin ?? -1) < 0.5

        var candidates: [(kind: String, confidence: Float)] = []
        if voiceActivity {
            candidates.append(("speech_candidate", clamp(0.45 + voiceProbability * 0.45)))
        }
        if let margin = toneMargin, dominant != nil, margin >= -1.0 {
            candidates.append(("tonal_alarm_candidate", clamp(0.50 + (margin + 1.0) / 8.0)))
        }
        if rmsDbfs >= -25.0 || peakDbfs >= -10.0 {
            let loudness = max((rmsDbfs + 35.0) / 25.0, (peakDbfs + 20.0) / 20.0)
            candidates.append(("loud_sound_candidate", clamp(loudness)))
        }
        return EdgeAnalysis(
            rmsDbfs: Float((rmsDbfs * 100).rounded() / 100),
            peakDbfs: Float((peakDbfs * 100).rounded() / 100),
            voiceActivity: voiceActivity,
            voiceProbability: Float((voiceProbability * 1000).rounded() / 1000),
            dominantToneHz: dominant,
            toneMarginDb: toneMargin.map { Float(($0 * 100).rounded() / 100) },
            candidates: candidates
        )
    }

    private func voiceProbability(_ samples: [Int16], overallDbfs: Double) -> Double {
        let frameSize = max(1, sampleRate / 50)
        var frameCount = 0
        var speechLike = 0
        let minimumFrameDbfs = max(-45.0, overallDbfs - 15.0)
        var start = 0
        while start + frameSize <= samples.count {
            let frame = samples[start..<(start + frameSize)]
            frameCount += 1
            var sumSquares = 0.0
            var crossings = 0
            var previous: Int16? = nil
            for sample in frame {
                sumSquares += Double(sample) * Double(sample)
                if let left = previous, (left < 0 && sample >= 0) || (left >= 0 && sample < 0) {
                    crossings += 1
                }
                previous = sample
            }
            let frameDbfs = toDbfs((sumSquares / Double(frame.count)).squareRoot() / 32768.0)
            let crossingRate = Double(crossings) / Double(max(1, frame.count - 1))
            if frameDbfs >= minimumFrameDbfs && crossingRate >= 0.015 && crossingRate <= 0.35 {
                speechLike += 1
            }
            start += frameSize
        }
        return frameCount > 0 ? Double(speechLike) / Double(frameCount) : 0
    }

    private func dominantTone(_ samples: [Int16]) -> (Int?, Double) {
        var bestFrequency: Int? = nil
        var bestAmplitude = 0.0
        for frequency in Self.toneFrequencies {
            let amplitude = goertzelAmplitude(samples, frequency: frequency)
            if amplitude > bestAmplitude {
                bestFrequency = frequency
                bestAmplitude = amplitude
            }
        }
        let toneDbfs = toDbfs(bestAmplitude / 32768.0)
        return toneDbfs < -50.0 ? (nil, toneDbfs) : (bestFrequency, toneDbfs)
    }

    private func goertzelAmplitude(_ samples: [Int16], frequency: Int) -> Double {
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

    private func toDbfs(_ amplitude: Double) -> Double { 20.0 * log10(max(amplitude, 1e-9)) }

    private func clamp(_ value: Double) -> Float { Float((max(0.0, min(0.99, value)) * 1000).rounded() / 1000) }
}
