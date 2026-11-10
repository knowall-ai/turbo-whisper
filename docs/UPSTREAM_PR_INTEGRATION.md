# Upstream PR integration — 2026-10-29

Scope: all nine open PRs (including the draft) targeting `knowall-ai/turbo-whisper`
when this integration started. Original authorship is retained in the cherry-picked
commits. This integration does not close, approve, or merge the original PRs.

| Upstream PR | Reviewed head | Integration and improvements |
| --- | --- | --- |
| [#39](https://github.com/knowall-ai/turbo-whisper/pull/39) | `e4995b1` | Both packaging commits retained: `qt6-svg` dependency and removal of the unused optional dependency. No AUR upload performed. |
| [#28](https://github.com/knowall-ai/turbo-whisper/pull/28) | `b15e216` | Both timeout commits retained. Added a UI control, finite positive-value validation, sync/async parity, multipart request tests and handled malformed responses. |
| [#34](https://github.com/knowall-ai/turbo-whisper/pull/34) | `9365950` | Letter-key matching retained and extended to release events, Ctrl-character normalization, right-hand modifiers and modifier overlap. |
| [#36](https://github.com/knowall-ai/turbo-whisper/pull/36) | `4b28b67` | X11 fallback retained with configured delay, argument termination and a bounded process timeout. Never present XWayland typing as insertion into native Wayland apps. |
| [#26](https://github.com/knowall-ai/turbo-whisper/pull/26) | `e3095a0` | Hold-to-talk retained. Added native backend release callbacks and portal Deactivated support. Queue start/stop states on the Qt thread so short taps cannot miss the release. |
| [#27](https://github.com/knowall-ai/turbo-whisper/pull/27) | `d86db25` | Non-exclusive evdev backend retained, with letter keys, both modifier sides, multiple-device state and synchronous availability probing. Prefer the desktop portal on Wayland; `TURBO_WHISPER_USE_EVDEV=1` prefers evdev when device access already exists. No group/udev changes are made by the app. |
| [#35](https://github.com/knowall-ai/turbo-whisper/pull/35) | `7ac46f8` | Server-side X11 grabs retained. Probe asynchronous X errors before choosing the backend; support function keys, all eight lock variants, release callbacks, auto-repeat handling and clean shutdown. Real Xvfb tests check consumption, release, ungrabbing and conflict detection. |
| [#10 (draft)](https://github.com/knowall-ai/turbo-whisper/pull/10) | `a1eec08` | Reviewed alongside #40. Its focused-app display, background lookup, stale-result token and pointer-sized Windows handles are covered by the newer implementation in #40. Not layered twice. Its Wayland drag fix is retained in the application. The new app icon replaces its orb styling. |
| [#40](https://github.com/knowall-ai/turbo-whisper/pull/40) | `4503d82` | Implementation and seven focused-window tests retained, including KDE/kdotool support, timeout-bounded calls, stale-result protection and 64-bit Windows handles. GNOME Wayland correctly omits unavailable focused-window information. |

## Desktop changes

- Compact, sound-responsive recording HUD; a separate resizable settings window.
- Dictation, Connection, Audio and History sections with real controls and keyboard focus.
- Microphone selection is passed to Pulse/PipeWire on Linux; PyAudio remains the
  Windows/macOS fallback. No microphone is opened until recording starts.
- Hidden API keys stay editable. Settings writes are atomic and private; unknown
  existing config fields survive a load/save cycle.
- New installs default to the official OpenAI endpoint rather than an unrelated
  third-party server. Existing endpoint choices are preserved. Claude integration
  is opt-in for new installations.
- Launching the app opens settings; relaunching activates the existing window.
  `--background` retains tray-only startup when explicitly wanted.
- Clipboard fallback is reported as clipboard fallback. Without input permissions,
  native Wayland insertion is not claimed; use Ctrl+V. Non-ASCII characters are
  never silently dropped by the ASCII evdev mapping.

## Verification boundaries

CI uses a read-only GitHub token and SHA-pinned actions. It gates lint, formatting,
locked dependencies, source/wheel packaging, regression tests and Qt interactions
on Linux/macOS/Windows with Python 3.10 and 3.12. Linux also runs real keyboard-grab
regressions under isolated Xvfb and renders synthetic UI screenshots. `ci-ok` fails
if any required job fails or is cancelled. No secrets, real microphone capture,
paid transcription API or host keyboard injection are needed for tests.

Automated mocks and Xvfb establish the tested behavior, not end-to-end physical
hotkey/microphone behavior on every desktop. Portal permission dialogs, actual
Windows/macOS audio/input permissions, AUR/DEB publishing and paid cloud API calls
are separate from CI. The later local-inference additions provide optional faster-whisper and whisper.cpp
runtimes, including live local phrases. See `LOCAL_LATENCY.adoc` for measured
responsiveness and `SESSION_LIFECYCLE.adoc` for rapid-toggle and finalization limits.
Model weights and optional inference runtimes are not bundled. Superwhisper is a
separate application with its own offline models.
