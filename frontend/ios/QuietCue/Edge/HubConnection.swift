import Foundation
import Network

/// Length-prefixed TCP session with the inference hub (port 8765 by default).
/// Equivalent to the asyncio reader/writer pair in `uno_q/linux/transport/hub_client.py`.
final class HubConnection {
    private let connection: NWConnection
    private let queue = DispatchQueue(label: "com.quietcue.hub-connection")

    init(host: String, port: UInt16) {
        let endpoint = NWEndpoint.hostPort(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!)
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        tcp.connectionTimeout = 5
        let parameters = NWParameters(tls: nil, tcp: tcp)
        parameters.serviceClass = .responsiveData
        connection = NWConnection(to: endpoint, using: parameters)
    }

    func connect(timeout: TimeInterval = 5) async throws {
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask { try await self.waitUntilReady() }
            group.addTask {
                try await Task.sleep(for: .seconds(timeout))
                throw WireProtocolError(message: "Timed out connecting to the hub")
            }
            try await group.next()
            group.cancelAll()
        }
    }

    private func waitUntilReady() async throws {
        let gate = ResumeGate()
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connection.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    if gate.claim() { continuation.resume() }
                case .failed(let error):
                    if gate.claim() { continuation.resume(throwing: error) }
                case .cancelled:
                    if gate.claim() { continuation.resume(throwing: WireProtocolError(message: "Connection cancelled")) }
                case .waiting(let error):
                    // Network.framework keeps retrying while waiting; surface the
                    // reason so the reconnect loop can back off instead.
                    if gate.claim() { continuation.resume(throwing: error) }
                default:
                    break
                }
            }
            connection.start(queue: queue)
        }
    }

    func send(_ message: WireMessage) async throws {
        let frame = try WireProtocol.encode(message)
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            connection.send(content: frame, completion: .contentProcessed { error in
                if let error { continuation.resume(throwing: error) } else { continuation.resume() }
            })
        }
    }

    func receive() async throws -> WireMessage {
        let prefix = try WireProtocol.parsePrefix(try await receiveExactly(WireProtocol.prefixSize))
        let document = try await receiveExactly(prefix.jsonLength)
        let payload = prefix.payloadLength > 0 ? try await receiveExactly(prefix.payloadLength) : Data()
        return try WireProtocol.decodeParts(document: document, payload: payload)
    }

    func receive(timeout: TimeInterval) async throws -> WireMessage {
        try await withThrowingTaskGroup(of: WireMessage.self) { group in
            group.addTask { try await self.receive() }
            group.addTask {
                try await Task.sleep(for: .seconds(timeout))
                throw WireProtocolError(message: "Timed out waiting for the hub")
            }
            let result = try await group.next()!
            group.cancelAll()
            return result
        }
    }

    private func receiveExactly(_ length: Int) async throws -> Data {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            connection.receive(minimumIncompleteLength: length, maximumLength: length) { content, _, isComplete, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let content, content.count == length {
                    continuation.resume(returning: content)
                } else if isComplete {
                    continuation.resume(throwing: WireProtocolError(message: "Hub closed the connection"))
                } else {
                    continuation.resume(throwing: WireProtocolError(message: "Short read from the hub"))
                }
            }
        }
    }

    func close() {
        connection.stateUpdateHandler = nil
        connection.cancel()
    }
}

/// Ensures a continuation is resumed exactly once across state callbacks.
private final class ResumeGate: @unchecked Sendable {
    private let lock = NSLock()
    private var resumed = false

    func claim() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if resumed { return false }
        resumed = true
        return true
    }
}
