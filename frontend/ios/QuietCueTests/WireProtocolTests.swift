import XCTest
@testable import QuietCue

final class WireProtocolTests: XCTestCase {
    func testRoundTripWithPayload() throws {
        let payload = Data((0..<64).map { UInt8($0) })
        let message = WireMessage(kind: "audio_chunk", body: ["sequence": 7, "sample_rate": 16_000], payload: payload)
        let frame = try WireProtocol.encode(message)
        XCTAssertEqual(frame.prefix(4), Data("QC01".utf8))
        let decoded = try WireProtocol.decode(frame: frame)
        XCTAssertEqual(decoded.kind, "audio_chunk")
        XCTAssertEqual(decoded.body["sequence"] as? Int, 7)
        XCTAssertEqual(decoded.payload, payload)
    }

    func testFrameMatchesPythonReferenceEncoding() throws {
        // backend/communication/stream_protocol.py: struct.pack("!4sII") + sorted compact JSON.
        let frame = try WireProtocol.encode(WireMessage(kind: "heartbeat", body: ["seq": 1]))
        let json = Data(#"{"body":{"seq":1},"kind":"heartbeat"}"#.utf8)
        var expected = Data("QC01".utf8)
        expected.append(contentsOf: [0, 0, 0, UInt8(json.count), 0, 0, 0, 0])
        expected.append(json)
        XCTAssertEqual(frame, expected)
    }

    func testRejectsBadMagic() {
        var frame = Data("XX01".utf8)
        frame.append(contentsOf: [0, 0, 0, 2, 0, 0, 0, 0])
        frame.append(Data("{}".utf8))
        XCTAssertThrowsError(try WireProtocol.decode(frame: frame))
    }

    func testEdgeAnalyzerFlagsLoudTone() {
        let sampleRate = 16_000
        let samples: [Int16] = (0..<8_000).map { index in
            Int16(20_000 * sin(2 * Double.pi * 1_000 * Double(index) / Double(sampleRate)))
        }
        let analysis = EdgeAnalyzer(sampleRate: sampleRate).analyze(samples)
        XCTAssertGreaterThan(analysis.rmsDbfs, -10)
        XCTAssertEqual(analysis.dominantToneHz, 1_000)
        XCTAssertTrue(analysis.candidates.contains { $0.kind == "tonal_alarm_candidate" })
        XCTAssertFalse(analysis.voiceActivity)
    }
}
