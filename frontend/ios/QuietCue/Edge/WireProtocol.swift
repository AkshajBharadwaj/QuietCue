import Foundation

/// One QuietCue transport message: a small JSON document plus an optional
/// binary payload (PCM audio). Mirrors `backend/communication/stream_protocol.py`.
struct WireMessage {
    var kind: String
    var body: [String: Any]
    var payload: Data = Data()
}

struct WireProtocolError: LocalizedError {
    var message: String
    var errorDescription: String? { message }
}

/// Frame layout: `QC01` magic, big-endian UInt32 JSON length, big-endian
/// UInt32 payload length, JSON document, payload bytes.
enum WireProtocol {
    static let magic = Data("QC01".utf8)
    static let prefixSize = 12
    static let maxJsonBytes = 64 * 1024
    static let maxPayloadBytes = 1024 * 1024

    static func encode(_ message: WireMessage) throws -> Data {
        guard !message.kind.isEmpty else { throw WireProtocolError(message: "Message kind cannot be empty") }
        let document: [String: Any] = ["kind": message.kind, "body": message.body]
        let json = try JSONSerialization.data(
            withJSONObject: document,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        guard json.count <= maxJsonBytes else { throw WireProtocolError(message: "Message JSON is too large") }
        guard message.payload.count <= maxPayloadBytes else { throw WireProtocolError(message: "Message payload is too large") }
        var frame = Data(capacity: prefixSize + json.count + message.payload.count)
        frame.append(magic)
        frame.append(bigEndian(UInt32(json.count)))
        frame.append(bigEndian(UInt32(message.payload.count)))
        frame.append(json)
        frame.append(message.payload)
        return frame
    }

    struct Prefix {
        var jsonLength: Int
        var payloadLength: Int
    }

    static func parsePrefix(_ data: Data) throws -> Prefix {
        guard data.count >= prefixSize else { throw WireProtocolError(message: "Message is shorter than its prefix") }
        let bytes = [UInt8](data.prefix(prefixSize))
        guard Data(bytes[0..<4]) == magic else { throw WireProtocolError(message: "Unrecognized QuietCue protocol magic") }
        let jsonLength = Int(readUInt32(bytes, at: 4))
        let payloadLength = Int(readUInt32(bytes, at: 8))
        guard jsonLength >= 2, jsonLength <= maxJsonBytes else {
            throw WireProtocolError(message: "Invalid JSON length: \(jsonLength)")
        }
        guard payloadLength <= maxPayloadBytes else {
            throw WireProtocolError(message: "Invalid payload length: \(payloadLength)")
        }
        return Prefix(jsonLength: jsonLength, payloadLength: payloadLength)
    }

    static func decodeParts(document: Data, payload: Data) throws -> WireMessage {
        guard let decoded = try? JSONSerialization.jsonObject(with: document) as? [String: Any] else {
            throw WireProtocolError(message: "Message JSON is invalid")
        }
        guard let kind = decoded["kind"] as? String, !kind.isEmpty else {
            throw WireProtocolError(message: "Message kind must be a non-empty string")
        }
        guard let body = decoded["body"] as? [String: Any] else {
            throw WireProtocolError(message: "Message body must be an object")
        }
        return WireMessage(kind: kind, body: body, payload: payload)
    }

    static func decode(frame: Data) throws -> WireMessage {
        let prefix = try parsePrefix(frame)
        let expected = prefixSize + prefix.jsonLength + prefix.payloadLength
        guard frame.count == expected else {
            throw WireProtocolError(message: "Expected \(expected) bytes, received \(frame.count)")
        }
        let documentStart = frame.startIndex + prefixSize
        let documentEnd = documentStart + prefix.jsonLength
        return try decodeParts(
            document: frame.subdata(in: documentStart..<documentEnd),
            payload: frame.subdata(in: documentEnd..<frame.endIndex)
        )
    }

    private static func bigEndian(_ value: UInt32) -> Data {
        var swapped = value.bigEndian
        return Data(bytes: &swapped, count: 4)
    }

    private static func readUInt32(_ bytes: [UInt8], at offset: Int) -> UInt32 {
        (UInt32(bytes[offset]) << 24) | (UInt32(bytes[offset + 1]) << 16) |
            (UInt32(bytes[offset + 2]) << 8) | UInt32(bytes[offset + 3])
    }
}
