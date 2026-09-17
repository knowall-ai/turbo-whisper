# Security Policy

Turbo Whisper records microphone audio, sends it to a Whisper API endpoint you configure, and simulates keyboard input to type the result. That makes three things security-relevant: the audio and transcripts, the API key in your config, and the global hotkey / input-device access the app needs. We take reports in any of these areas seriously.

## Supported versions

Only the latest release on the `main` branch (and the matching AUR / PPA packages) receives security fixes.

## Reporting a vulnerability

Please **do not** report security vulnerabilities through public GitHub issues, discussions or pull requests.

1. Use GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**, or go directly to <https://github.com/knowall-ai/turbo-whisper/security/advisories/new>.
2. Include what you found, how to reproduce it, the version or commit you tested, your OS and display session (X11/Wayland), and the impact you believe it has.
3. If you have a suggested fix, a private patch or a draft PR link is welcome, but not required.

## What to expect

- We aim to acknowledge reports within 5 working days.
- We will keep you updated as we investigate, and agree a disclosure timeline with you. Our default is to publish a fix and advisory within 90 days of the report, sooner for anything actively exploitable.
- With your permission we will credit you in the advisory and release notes.

## Scope notes

- The app talks to whichever API endpoint is configured. Weaknesses in third-party or self-hosted Whisper servers are out of scope, but please tell us if the client handles their responses unsafely.
- Your config file (`~/.config/turbo-whisper/config.json`) stores the API key in plain text with user-only permissions; a report about that design is welcome, but it is a known trade-off rather than a vulnerability on its own.
- Features that need `/dev/uinput` or `/dev/input` access (typing, Wayland hotkeys) are documented in `docs/SOLUTION_DESIGN.adoc`. Please report anything that lets the app read or inject input beyond what the documentation describes.

Thank you for helping keep Turbo Whisper users safe.
