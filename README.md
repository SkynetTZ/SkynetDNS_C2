# SkynetDNS_C2
Security research project exploring DNS-based command-and-control (C&amp;C) using DNS protocol.

<img width="1788" height="479" alt="Screenshot 2026-04-27 at 19 09 09" src="https://github.com/user-attachments/assets/1ee83a4b-c2dc-454f-9e1b-8a7c787e8d0c" />

<img width="1800" height="1169" alt="Screenshot 2026-04-27 at 18 39 00" src="https://github.com/user-attachments/assets/6330c325-8661-4090-945b-f58e0cca829a" />

<img width="1795" height="721" alt="Screenshot 2026-04-27 at 19 39 03" src="https://github.com/user-attachments/assets/11b0b20e-35a5-480c-b634-fae6713d93b2" />

<img width="1483" height="999" alt="Screenshot 2026-04-27 at 19 40 25" src="https://github.com/user-attachments/assets/17849bde-ec8c-4465-ad94-9ae4dae2e12f" />

# About
`SkyneDNS_C2` demonstrates how command/data exchange can be tunneled through DNS queries and responses.  
The codebase includes:

- a Windows C++ client implementation
- a Python server implementation for handling DNS traffic and session tracking
- a build script for compiling the Windows client

This project is useful for understanding how DNS can be abused as a covert transport channel and how defenders can identify those patterns. Instead of focusing on offensive deployment, treat it as a reference implementation for:

- protocol behavior analysis
- telemetry generation for blue-team pipelines
- testing detections around anomalous DNS record usage (especially TXT records)

The idea is to demonstrate how the DNS protocol can be leveraged to target Windows computers while evading monitoring tools. By using DNS TXT records, an attacker can establish a covert communication channel between the client and the attacker, allowing malicious traffic to pass unnoticed. This technique can also be used to trigger operating system commands on the client machine.

# Repository Structure
- `client.cp.cpp` - Windows client implementation (DNS polling, command/result transport)
- `server2.py` - Python DNS server/controller prototype with session management
- `build.py` - Python helper script to compile the client executable with `g++`

# How It Works (High Level)
At a high level, the system follows a request/response beacon model over DNS:

1. The client periodically sends DNS queries to a configured domain.
2. The server parses incoming DNS requests and maps them to a session.
3. The server returns tasking (or idle responses) via DNS response records.
4. The client executes received tasking and sends output back in DNS-safe chunks.
5. The server reassembles chunks, stores results, and updates session state.

# Component Details
### `client.cp.cpp` (Windows C++ client)

Main responsibilities:

- build and send DNS packets
- parse DNS responses (including TXT data)
- maintain periodic beaconing with jitter
- collect local identity context (for session identification)
- send command output in encoded chunks
- generate decoy queries to blend traffic patterns

Why this matters for detection:

- periodic jittered polling can still produce measurable beacon signatures
- TXT-heavy traffic and structured subdomains are often high-signal indicators
- chunked exfil patterns may stand out in DNS logs

### `server2.py` (Python controller/server)
Main responsibilities:

- listen for DNS requests and decode protocol fields
- create/track sessions and their metadata
- queue and deliver commands to clients
- receive chunked results and reassemble complete outputs
- expose an operator-style console interface for managing sessions/tasks

Operationally, this is where state lives (active sessions, pending commands, collected outputs), which makes it a good point for:

- protocol instrumentation
- additional logging hooks
- replay/testing of detection logic

### `build.py` (client builder)
Main responsibilities:

- validate compiler prerequisites
- clean old artifacts
- compile the client with Windows networking libraries
- optionally apply optimization flags

It also includes usability checks (missing compiler/source handling) that make local lab iteration easier.

# Requirements
### Server-side (Python)

- Python 3.9+
- `dnslib`
- `rich`

Install dependencies:

```bash
pip3 install dnslib rich
```

### Client build (Windows)

- MinGW-w64 `g++` in PATH
- Windows environment with Winsock libraries available

## Build
From the project root:

```bash
python3 build.py
```

Optional modes:

```bash
python3 build.py optimize
python3 build.py clean
```

Expected output is a Windows executable (default `1.exe`) in the repository root.
