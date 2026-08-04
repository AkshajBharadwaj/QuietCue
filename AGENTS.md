# QuietCue AGENTS.md

## Project Overview

QuietCue is a wearable AI-assisted accessibility system designed to help deaf and hard-of-hearing users perceive important environmental events through intelligent audio understanding and haptic feedback.

The system uses a multi-device architecture:

* **Snapdragon X Elite PC**: AI inference, reasoning, backend services, and orchestration
* **Arduino Uno Q**: wearable edge device for sensing, communication, and haptic feedback
* **Optional phone companion**: configuration, notifications, and user interaction

The goal is to build a reliable, low-latency pipeline:

```
Environment
     |
     ↓
Audio Capture
     |
     ↓
AI Understanding
     |
     ↓
Event Decision
     |
     ↓
Haptic Feedback
     |
     ↓
User Awareness
```

---

# Architecture

## High-Level System

```
                 GitHub Repository
                        |
        --------------------------------
        |                              |
 Developer Machines            Snapdragon X Elite PC
                                      |
                              QuietCue Backend
                                      |
                         ------------------------
                         |                      |
                    AI Inference          Device Communication
                         |                      |
                         ↓                      ↓
                  Event Understanding       Arduino Uno Q
                                                |
                                                ↓
                                         Haptic Feedback
```

---

# Device Responsibilities

## Snapdragon X Elite PC

The Snapdragon PC is the primary intelligence layer.

Responsibilities:

* Run AI models
* Process audio
* Perform sound event detection
* Run speech recognition when needed
* Perform context reasoning
* Manage alert prioritization
* Communicate with the Uno Q
* Host development services

Examples:

* Doorbell detection
* Fire alarm detection
* Car horn detection
* Name-call detection
* Conversation understanding

The Snapdragon PC should handle heavy computation.

Do NOT move large models onto the Uno Q unless specifically optimized for edge inference.

---

## Arduino Uno Q

The Uno Q is the wearable edge device.

Responsibilities:

* Capture sensor data
* Communicate with backend
* Control vibration motors
* Handle user input
* Provide reliable real-time feedback

The Uno Q should NOT:

* Run large language models
* Run large speech-to-text models
* Replace the Snapdragon inference system

Possible local inference:

* Lightweight sound classifiers
* Wake-word detection
* Simple event detection

---

# Communication Architecture

## Development Communication

Used for debugging and deployment:

```
Developer Laptop
        |
        | Tailscale + SSH
        ↓
Snapdragon PC / Uno Q
```

Tailscale provides secure remote access.

SSH is for:

* debugging
* deployment
* checking logs
* restarting services

SSH should not be used as the primary runtime communication method.

---

## Runtime Communication

Runtime communication should use:

* Bluetooth Low Energy
* WiFi
* WebSockets
* MQTT
* Serial (during development)

Example:

```
AI Backend
    |
    | "DOORBELL"
    ↓
Uno Q
    |
    ↓
Vibration Pattern
```

Messages should be small event payloads.

Example:

```json
{
  "event": "fire_alarm",
  "confidence": 0.94,
  "timestamp": "2026-08-03T14:00:00"
}
```

---

# Repository Structure

```
QuietCue/

├── backend/
│   ├── app/
│   ├── inference/
│   ├── audio/
│   ├── communication/
│   └── requirements.txt
│
├── arduino/
│   ├── firmware/
│   ├── haptics/
│   └── communication/
│
├── frontend/
│
├── docs/
│
└── README.md
```

---

# Development Workflow

## Code Ownership

GitHub is the source of truth.

Developers should:

1. Clone the repository
2. Create a branch
3. Make changes locally
4. Commit changes
5. Push changes
6. Merge through GitHub

Example:

```bash
git checkout -b feature-name

git add .

git commit -m "Describe change"

git push origin feature-name
```

---

# Deployment Workflow

## Snapdragon PC

Pull latest changes:

```bash
git pull
```

Run backend:

```bash
python backend/app/server.py
```

---

## Uno Q

The Uno Q maintains a deployed copy.

Update:

```bash
git pull
```

Run hardware services:

```bash
python arduino/firmware/controller.py
```

---

# Hardware Development

## Initial Prototype

Start with:

```
Snapdragon PC
       |
       | event message
       ↓
Uno Q
       |
       ↓
Vibration Motor
```

Example:

Input:

```
DOORBELL
```

Output:

```
Two short vibrations
```

---

# Haptic Design Principles

Avoid requiring users to memorize many patterns.

Recommended categories:

## Informational

Example:

* Doorbell
* Message
* Conversation

Pattern:

* short pulses

---

## Attention

Example:

* Name called
* Important notification

Pattern:

* longer vibration

---

## Emergency

Example:

* Fire alarm
* Vehicle warning

Pattern:

* repeated urgent pulses

---

# Engineering Principles

## Prefer simplicity

Do not add hardware unless it improves the user experience.

Every component should have a clear purpose.

---

## Separate intelligence from feedback

AI reasoning belongs on powerful compute.

The wearable should provide:

* reliable sensing
* reliable communication
* reliable feedback

---

## Build incrementally

Recommended milestones:

### Milestone 1

Communication test:

```
Python → Uno Q → vibration
```

### Milestone 2

Basic event detection:

```
Audio → classifier → vibration
```

### Milestone 3

Context-aware AI:

```
Audio + context → intelligent alert
```

### Milestone 4

Wearable refinement:

* battery
* enclosure
* latency optimization
* user testing

---

# Security

Never commit:

* API keys
* passwords
* WiFi credentials
* Tailscale auth keys
* tokens

Use:

* environment variables
* local configuration files
* secret managers

---

# Current Technical Direction

The preferred architecture is:

```
Wearable Environment
        |
        ↓
Uno Q + Microphone
        |
        ↓
Snapdragon X Elite AI Engine
        |
        ↓
Decision Agent
        |
        ↓
Uno Q Haptic Feedback
```

The system should eventually become an intelligent agent that understands context, prioritizes events, and adapts alerts to the user's needs.
