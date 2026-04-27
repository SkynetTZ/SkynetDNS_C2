# SkynetDNS_C2
Security research project exploring DNS-based command-and-control (C&amp;C) using DNS protocol.

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
