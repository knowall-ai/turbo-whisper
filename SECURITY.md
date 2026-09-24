# Security Policy

Turbo Whisper records microphone audio, sends it to a Whisper API endpoint you configure, and simulates keyboard input to type the result. That makes three things security-relevant: the audio and transcripts, the API key in your config, and the global hotkey / input-device access the app needs. We take reports in any of these areas seriously.

## Supported versions

Only the most recent tagged release (the newest `vX.Y.Z` tag on GitHub, which the AUR and PPA packages track) receives security fixes. Older releases are not patched; upgrade to the latest release. The unreleased `main` branch is not a supported version, although fixes land there first.

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

- The app talks to whichever API endpoint is configured, sending your audio and (if set) the API key as a Bearer token. Plain `http://` URLs give no transport confidentiality, so use them only for trusted local or self-hosted servers and never with a real cloud API key; use `https://` for anything that leaves your machine or LAN. Weaknesses in third-party or self-hosted Whisper servers are out of scope, but please tell us if the client handles their responses unsafely.
- The config file stores the API key in plain text. It lives at `$XDG_CONFIG_HOME/turbo-whisper/config.json` on Linux and macOS (`~/.config/turbo-whisper/config.json` when that variable is unset) and `%APPDATA%\turbo-whisper\config.json` on Windows. The app does not set permissions, so on Linux/macOS they follow your umask (commonly `0644`); run `chmod 600` on the file if other users share the machine. On Windows the file inherits your profile's ACL, which already excludes other standard users. This is a known trade-off rather than a vulnerability on its own, though a report proposing a safer default is welcome.
- Auto-typing on Linux uses a virtual keyboard via `/dev/uinput` (see `docs/SOLUTION_DESIGN.adoc`), which is why the app asks for `input` group membership. Please report anything that lets the app inject input beyond what the documentation describes.

Thank you for helping keep Turbo Whisper users safe.
