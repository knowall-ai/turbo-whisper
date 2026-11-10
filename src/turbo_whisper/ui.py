"""Qt views for a quiet recording HUD and a separate, accessible settings window."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .icons import get_close_icon, get_eye_icon
from .waveform import WaveformWidget

THEME = """
QWidget { background: #1c1c1f;
    color: #ededf0;
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
    }
QFrame#Sidebar { background: #171719;
    border-right: 1px solid #303034;
    }
QFrame#Card { background: #252528;
    border: 1px solid #36363b;
    border-radius: 12px;
    }
QLabel { background: transparent;
    }
QLabel#Title { font-size: 26px;
    font-weight: 600;
    letter-spacing: -0.5px;
    }
QLabel#Subtitle, QLabel#Muted { color: #a7a7b0;
    }
QLabel#Section { font-size: 15px;
    font-weight: 600;
    }
QLabel#Brand { font-size: 17px;
    font-weight: 600;
    }
QLabel#Badge { background: #34303f;
    color: #d5c9ff;
    border-radius: 7px;
    padding: 5px 9px;
    font-size: 11px;
    }
QListWidget#Navigation { background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
    }
QListWidget#Navigation::item { padding: 11px 14px;
    margin: 3px 0;
    border-radius: 8px;
    }
QListWidget#Navigation::item:selected { background: #333039;
    color: #e5dfff;
    }
QListWidget#Navigation::item:hover { background: #29292e;
    }
QPushButton { background: #303034;
    border: 1px solid #45454c;
    border-radius: 7px;
    padding: 8px 13px;
    font-weight: 500;
    }
QPushButton:hover { background: #3b3b42;
    border-color: #66616f;
    }
QPushButton:pressed { background: #45414e;
    }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
QSpinBox:focus, QPlainTextEdit:focus {
    border: 1px solid #c4afff;
    }
QPushButton#Primary { background: #d1c0fa;
    color: #252032;
    border: 1px solid #d1c0fa;
    font-weight: 600;
    }
QPushButton#Primary:hover { background: #e0d3ff;
    }
QPushButton#Quiet { background: transparent;
    border: 1px solid transparent;
    color: #bbb9c3;
    }
QPushButton#Quiet:hover { background: #34343a;
    }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: #1e1e22;
    color: #efedf4;
    border: 1px solid #45454d;
    border-radius: 7px;
    padding: 9px 11px;
    min-height: 18px;
    selection-background-color: #675481;
    }
QPlainTextEdit { background: #1e1e22;
    color: #efedf4;
    border: 1px solid #45454d;
    border-radius: 7px;
    padding: 10px;
    selection-background-color: #675481;
    }
QComboBox::drop-down { border: none;
    width: 25px;
    }
QComboBox QAbstractItemView { background: #29292e;
    selection-background-color: #454050;
    }
QCheckBox { spacing: 10px;
    background: transparent;
    padding: 6px 0;
    }
QCheckBox::indicator { width: 18px;
    height: 18px;
    border: 1px solid #77727f;
    border-radius: 5px;
    background: #242429;
    }
QCheckBox::indicator:checked { background: #b9a0ed;
    border-color: #d1c0fa;
    image: url("__CHECK_ICON__");
    }
QSlider::groove:horizontal { height: 4px;
    background: #424249;
    border-radius: 2px;
    }
QSlider::sub-page:horizontal { background: #b9a0ed;
    border-radius: 2px;
    }
QSlider::handle:horizontal { background: #eee7ff;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
    }
QListWidget#History { border: none;
    background: transparent;
    outline: none;
    }
QListWidget#History::item { background: #252528;
    border: 1px solid #36363b;
    border-radius: 10px;
    margin: 0 0 9px 0;
    padding: 8px;
    }
QScrollArea { background: transparent;
    border: none;
    }
QScrollBar:vertical { background: transparent;
    width: 7px;
    margin: 3px;
    }
QScrollBar::handle:vertical { background: #52515a;
    border-radius: 3px;
    min-height: 28px;
    }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0;
    }
QToolTip { background: #38343f;
    color: #f4efff;
    border: 1px solid #60566e;
    padding: 6px;
    }
"""


def label(text, name=None):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    item.setWordWrap(True)
    item.setTextFormat(Qt.TextFormat.PlainText)
    return item


def card(layout, title, detail=None):
    frame = QFrame()
    frame.setObjectName("Card")
    body = QVBoxLayout(frame)
    body.setContentsMargins(22, 19, 22, 20)
    body.setSpacing(13)
    body.addWidget(label(title, "Section"))
    if detail:
        body.addWidget(label(detail, "Muted"))
    layout.addWidget(frame)
    return body


def field(layout, title, widget, help_text=None):
    layout.addWidget(label(title))
    layout.addWidget(widget)
    widget.setAccessibleName(title)
    if help_text:
        layout.addWidget(label(help_text, "Muted"))


def page(title, subtitle):
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(30, 26, 30, 24)
    layout.setSpacing(18)
    layout.addWidget(label(title, "Title"))
    layout.addWidget(label(subtitle, "Subtitle"))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    return scroll, layout


def icon_button(icon, name):
    button = QPushButton()
    button.setObjectName("Quiet")
    button.setIcon(icon)
    button.setFixedSize(36, 36)
    button.setToolTip(name)
    button.setAccessibleName(name)
    return button


def build_windows(view):
    """Build controls while keeping state and I/O in RecordingWindow/TurboWhisper."""
    view.setWindowTitle("Turbo Whisper — Recording")
    from .icons import get_tray_icon

    view.setWindowIcon(get_tray_icon(64))
    view._base_window_flags = (
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
    )
    view.setWindowFlags(view._base_window_flags | Qt.WindowType.WindowDoesNotAcceptFocus)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    from pathlib import Path

    theme = THEME.replace("__CHECK_ICON__", Path(__file__).with_name("check.svg").as_posix())
    view.setStyleSheet(theme)
    hud = QFrame()
    hud.setObjectName("Card")
    root = QVBoxLayout(view)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(hud)
    row = QHBoxLayout(hud)
    row.setContentsMargins(16, 10, 10, 10)
    view.waveform = WaveformWidget(color="#c7aff5")
    view.waveform.setFixedSize(74, 38)
    row.addWidget(view.waveform)
    status = QVBoxLayout()
    view.status_label = label("Ready", "Section")
    view.hints_label = label("", "Muted")
    view._hotkey_str = "+".join(k.title() for k in view.config.hotkey)
    view.set_recording_hint(False)
    status.addWidget(view.status_label)
    status.addWidget(view.hints_label)
    row.addLayout(status, 1)
    view.settings_btn = QPushButton("···")
    view.settings_btn.setObjectName("Quiet")
    view.settings_btn.setAccessibleName("Open settings")
    view.settings_btn.setToolTip("Open settings")
    view.settings_btn.setFixedSize(32, 36)
    view.settings_btn.clicked.connect(view._toggle_settings)
    row.addWidget(view.settings_btn)
    view.close_btn = icon_button(get_close_icon(15, "#aaa6b2"), "Cancel recording")
    view.close_btn.clicked.connect(view._close_window)
    row.addWidget(view.close_btn)
    view.resize(400, 78)
    from PyQt6.QtCore import QTimer

    view._status_dots = 0
    view._status_timer = QTimer(view)
    view._status_timer.timeout.connect(view._animate_status)
    view._status_timer.setInterval(400)

    # Normal, resizable window: familiar desktop controls, no sprawling recording overlay.
    view.settings_panel = QWidget()
    window = view.settings_panel
    window.setWindowTitle("Turbo Whisper")
    window.setWindowIcon(view.windowIcon())
    window.setStyleSheet(theme)
    window.setMinimumSize(740, 560)
    window.resize(940, 720)
    shell = QHBoxLayout(window)
    shell.setContentsMargins(0, 0, 0, 0)
    shell.setSpacing(0)
    sidebar = QFrame()
    sidebar.setObjectName("Sidebar")
    sidebar.setFixedWidth(190)
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(17, 25, 17, 20)
    side.setSpacing(20)
    side.addWidget(label("∿  turbo whisper", "Brand"))
    view.navigation = QListWidget()
    view.navigation.setObjectName("Navigation")
    view.navigation.setAccessibleName("Settings sections")
    view.navigation.addItems(["Dictation", "Connection", "Audio", "History", "Review"])
    side.addWidget(view.navigation, 1)
    side.addWidget(label(f"Open source · {__version__}", "Muted"))
    shell.addWidget(sidebar)
    main = QVBoxLayout()
    main.setSpacing(0)
    view.pages = QStackedWidget()
    main.addWidget(view.pages, 1)
    shell.addLayout(main, 1)

    general, body = page("Dictation", "A little less typing. A little more flow.")
    view.pages.addWidget(general)
    hero = card(
        body, "Your voice, anywhere.", "Speak naturally, then return to what you were doing."
    )
    badge = label("VOICE TO TEXT", "Badge")
    hero.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
    actions = QHBoxLayout()
    view.record_btn = QPushButton("Start dictation")
    view.record_btn.setObjectName("Primary")
    view.record_btn.clicked.connect(view.record_requested.emit)
    actions.addWidget(view.record_btn)
    actions.addStretch()
    actions.addWidget(label(view._hotkey_str, "Muted"))
    hero.addLayout(actions)
    interaction = card(body, "Recording", "Choose a shortcut that feels natural on your desktop.")
    view.hotkey_input = QLineEdit("+".join(view.config.hotkey))
    field(
        interaction,
        "Keyboard shortcut",
        view.hotkey_input,
        "Separate keys with +, for example ctrl+alt+w.",
    )
    view.hold_checkbox = QCheckBox("Hold to talk — release the shortcut to transcribe")
    view.hold_checkbox.setChecked(view.config.push_to_talk)
    interaction.addWidget(view.hold_checkbox)
    view.paste_checkbox = QCheckBox("Insert transcribed text into the focused app")
    view.paste_checkbox.setChecked(view.config.auto_paste)
    interaction.addWidget(view.paste_checkbox)
    view.live_checkbox = QCheckBox("Insert local phrases as you speak (pause between phrases)")
    view.live_checkbox.setChecked(view.config.live_transcription)
    interaction.addWidget(view.live_checkbox)
    interaction.addWidget(
        label(
            "Live phrases use your local model. Pausing sends a phrase; stopping sends the rest. "
            "Text already inserted remains if you cancel.",
            "Muted",
        )
    )
    view.clipboard_checkbox = QCheckBox("Copy transcriptions to the clipboard")
    view.clipboard_checkbox.setChecked(view.config.copy_to_clipboard)
    interaction.addWidget(view.clipboard_checkbox)
    writer = card(
        body,
        "LibreOffice Writer",
        "Send live phrases directly to the active Writer document. "
        "After stopping, polish only this dictation. Unfinished words stay visible as "
        "provisional text with a Writer comment and an editable Review entry. "
        "While enabled, Writer's active document is the destination, "
        "even if another app has focus.",
    )
    view.writer_checkbox = QCheckBox("Dictate into Writer and polish after stopping")
    view.writer_checkbox.setChecked(view.config.writer_polish)
    view.paste_checkbox.setEnabled(not view.config.writer_polish)
    view.writer_checkbox.toggled.connect(
        lambda enabled: view.paste_checkbox.setEnabled(not enabled)
    )
    writer.addWidget(view.writer_checkbox)
    view.polish_url_input = QLineEdit(view.config.polish_url)
    field(
        writer,
        "Local correction endpoint",
        view.polish_url_input,
        "A local OpenAI-compatible text model is required. Only loopback HTTP is accepted; "
        "there is no remote correction fallback.",
    )
    view.polish_model_input = QLineEdit(view.config.polish_model)
    field(writer, "Local correction model", view.polish_model_input)
    view.open_writer_btn = QPushButton("Open a new Writer document")
    view.open_writer_btn.clicked.connect(view.open_writer_requested.emit)
    writer.addWidget(view.open_writer_btn)
    view.hotkey_status = label("Global shortcuts follow your desktop's permissions.", "Muted")
    body.addWidget(view.hotkey_status)
    body.addStretch()

    connection, body = page("Connection", "Transcribe on this computer or use an API service.")
    view.pages.addWidget(connection)
    selection = card(body, "Transcription")
    view.backend_combo = QComboBox()
    view.backend_combo.addItem("API service", "api")
    view.backend_combo.addItem("Local model", "local")
    view.backend_combo.addItem("whisper.cpp (local CPU / GPU)", "whisper_cpp")
    view.backend_combo.setCurrentIndex(
        max(0, view.backend_combo.findData(view.config.transcription_backend))
    )
    field(selection, "Run transcription with", view.backend_combo)
    view.api_settings = QWidget()
    body.addWidget(view.api_settings)
    backend = card(
        QVBoxLayout(view.api_settings),
        "API service",
        "Audio is sent to the endpoint below when you dictate with the API service selected.",
    )
    view.api_url_input = QLineEdit(view.config.api_url)
    field(backend, "API endpoint", view.api_url_input)
    keyrow = QHBoxLayout()
    view._actual_api_key = view.config.api_key
    view._key_visible = False
    view.api_key_input = QLineEdit(view.config.api_key)
    view.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    view.api_key_input.setPlaceholderText("Optional for a local server")
    view.api_key_input.setAccessibleName("API key")
    view.api_key_input.textChanged.connect(view._on_api_key_changed)
    keyrow.addWidget(view.api_key_input)
    view.key_visible_btn = icon_button(get_eye_icon(16, "#bcb7c7"), "Show or hide API key")
    view.key_visible_btn.clicked.connect(view._toggle_key_visibility)
    keyrow.addWidget(view.key_visible_btn)
    backend.addWidget(label("API key"))
    backend.addLayout(keyrow)
    view.model_input = QLineEdit(view.config.api_model)
    field(backend, "Model", view.model_input)
    view.timeout_input = QDoubleSpinBox()
    view.timeout_input.setRange(1, 3600)
    view.timeout_input.setSuffix(" seconds")
    view.timeout_input.setValue(view.config.transcription_timeout)
    field(
        backend,
        "Transcription timeout",
        view.timeout_input,
        "Increase this for long recordings on a local server.",
    )
    view.local_settings = QWidget()
    body.addWidget(view.local_settings)
    local = card(
        QVBoxLayout(view.local_settings),
        "Local model",
        "Audio stays on this computer. An optional local runtime is required; "
        "see the README for installation. "
        "The first dictation downloads the model; later runs use the cached copy.",
    )
    view.local_model_input = QLineEdit(view.config.local_model)
    field(
        local,
        "Local model name or folder",
        view.local_model_input,
        "Start with base or small. A folder must contain a converted faster-whisper model.",
    )
    view.local_device_combo = QComboBox()
    for title, value in [("CPU", "cpu"), ("NVIDIA GPU (CUDA)", "cuda"), ("Automatic", "auto")]:
        view.local_device_combo.addItem(title, value)
    view.local_device_combo.setCurrentIndex(
        max(0, view.local_device_combo.findData(view.config.local_device))
    )
    field(local, "Processing device", view.local_device_combo, "CPU works without GPU drivers.")
    view.local_compute_combo = QComboBox()
    for value in ["int8", "float32", "float16", "int8_float16", "default"]:
        view.local_compute_combo.addItem(value, value)
    view.local_compute_combo.setCurrentIndex(
        max(0, view.local_compute_combo.findData(view.config.local_compute_type))
    )
    field(local, "Precision", view.local_compute_combo, "Use int8 on CPU; float16 on NVIDIA GPU.")
    view.local_files_checkbox = QCheckBox("Use downloaded models only (no network access)")
    view.local_files_checkbox.setChecked(view.config.local_files_only)
    local.addWidget(view.local_files_checkbox)

    view.cpp_settings = QWidget()
    body.addWidget(view.cpp_settings)
    cpp = card(
        QVBoxLayout(view.cpp_settings),
        "whisper.cpp",
        "Audio stays on this computer. CPU inference works without a dedicated GPU. "
        "Choose a downloaded ggml model; base or small fits a CPU-oriented setup. "
        "Batch dictation reloads the model. Live phrases keep it ready between recordings.",
    )
    view.cpp_binary_input = QLineEdit(view.config.whisper_cpp_binary)
    field(cpp, "whisper-cli executable", view.cpp_binary_input)
    view.cpp_model_input = QLineEdit(view.config.whisper_cpp_model)
    field(cpp, "Model file (.bin)", view.cpp_model_input)
    view.cpp_device_input = QSpinBox()
    view.cpp_device_input.setRange(0, 64)
    view.cpp_device_input.setValue(view.config.whisper_cpp_device)
    field(cpp, "GPU device index", view.cpp_device_input)
    view.cpp_timeout_input = QDoubleSpinBox()
    view.cpp_timeout_input.setRange(1, 3600)
    view.cpp_timeout_input.setSuffix(" seconds")
    view.cpp_timeout_input.setValue(view.config.whisper_cpp_timeout)
    field(cpp, "Local processing timeout", view.cpp_timeout_input)
    view.cpp_use_gpu_checkbox = QCheckBox("Use GPU acceleration when available")
    view.cpp_use_gpu_checkbox.setChecked(view.config.whisper_cpp_use_gpu)
    cpp.addWidget(view.cpp_use_gpu_checkbox)
    view.cpp_require_gpu_checkbox = QCheckBox("Require GPU acceleration (reject CPU fallback)")
    view.cpp_require_gpu_checkbox.setChecked(view.config.whisper_cpp_require_gpu)
    cpp.addWidget(view.cpp_require_gpu_checkbox)

    def update_acceleration():
        enabled = view.cpp_use_gpu_checkbox.isChecked()
        view.cpp_device_input.setEnabled(enabled)
        view.cpp_require_gpu_checkbox.setEnabled(enabled)
        if not enabled:
            view.cpp_require_gpu_checkbox.setChecked(False)

    view.cpp_use_gpu_checkbox.toggled.connect(update_acceleration)
    update_acceleration()

    def update_backend():
        selected = view.backend_combo.currentData()
        view.api_settings.setVisible(selected == "api")
        view.local_settings.setVisible(selected == "local")
        view.cpp_settings.setVisible(selected == "whisper_cpp")

    view.backend_combo.currentIndexChanged.connect(update_backend)
    update_backend()
    language = card(body, "Language")
    view.language_input = QLineEdit(view.config.language)
    field(
        language,
        "Language code",
        view.language_input,
        "For example en, es, or fr. Leave blank for automatic detection with a local model.",
    )
    body.addStretch()

    audio, body = page("Audio", "Find your microphone. Make yourself heard.")
    view.pages.addWidget(audio)
    mic = card(
        body,
        "Input device",
        "Your system default follows the microphone selected in desktop settings.",
    )
    view.mic_combo = QComboBox()
    view._populate_mic_dropdown()
    field(mic, "Microphone", view.mic_combo)
    gain = QHBoxLayout()
    view.gain_label = label("Visual gain")
    view.gain_value_label = label("100%", "Muted")
    gain.addWidget(view.gain_label)
    gain.addStretch()
    gain.addWidget(view.gain_value_label)
    mic.addLayout(gain)
    view.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
    view.sensitivity_slider.setAccessibleName("Waveform visual gain")
    view.sensitivity_slider.setRange(0, 200)
    view.sensitivity_slider.setValue(100)
    view.sensitivity_slider.valueChanged.connect(view._on_sensitivity_changed)
    view._current_mic_level = 0
    mic.addWidget(view.sensitivity_slider)
    mic.addWidget(
        label("Adjusts the waveform preview; it does not change recording volume.", "Muted")
    )
    view.recordings_checkbox = QCheckBox("Keep audio with recent transcriptions")
    view.recordings_checkbox.setChecked(view.config.store_recordings)
    mic.addWidget(view.recordings_checkbox)
    body.addStretch()

    history, body = page("History", "A second chance for your last good thought.")
    view.pages.addWidget(history)
    view.history_empty = label(
        "Nothing here yet. Your recent transcriptions will appear after your first dictation.",
        "Muted",
    )
    body.addWidget(view.history_empty)
    view.history_list = QListWidget()
    view.history_list.setObjectName("History")
    view.history_list.setAccessibleName("Recent transcriptions")
    view.history_list.setMinimumHeight(300)
    view.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view._refresh_history()
    body.addWidget(view.history_list, 1)

    review, body = page("Review", "Complete provisional sentences and review local corrections.")
    body.setSpacing(10)
    view.pages.addWidget(review)
    view.review_list = QListWidget()
    view.review_list.setAccessibleName("Dictation results for review")
    view.review_list.setMaximumHeight(70)
    body.addWidget(view.review_list)
    view.review_feedback = label("Writer dictations will appear here after stopping.", "Muted")
    body.addWidget(view.review_feedback)
    view.review_original = QPlainTextEdit()
    view.review_original.setReadOnly(True)
    view.review_original.setMaximumHeight(75)
    field(body, "Original recognized words", view.review_original)
    view.review_text = QPlainTextEdit()
    view.review_text.setMinimumHeight(110)
    view.review_text.setMaximumHeight(170)
    field(body, "Reviewed text — finish an unfinished sentence here", view.review_text)
    buttons = QHBoxLayout()
    view.review_apply_btn = QPushButton("Apply reviewed text to Writer")
    view.review_apply_btn.setObjectName("Primary")
    view.review_apply_btn.clicked.connect(view._request_review_apply)
    buttons.addWidget(view.review_apply_btn)
    copy_review = QPushButton("Copy reviewed text")
    copy_review.clicked.connect(lambda: view._copy_to_clipboard(view.review_text.toPlainText()))
    buttons.addWidget(copy_review)
    body.addLayout(buttons)
    body.addWidget(
        label(
            "Apply replaces only this dictation's unchanged Writer range. "
            "It never completes your thought for you. After restarting the app, "
            "use Copy for older entries; old documents are not retargeted.",
            "Muted",
        )
    )
    view.review_list.currentRowChanged.connect(view._select_review)
    view._refresh_reviews()

    footer = QHBoxLayout()
    footer.setContentsMargins(30, 15, 30, 18)
    view.claude_status = label("", "Muted")
    view._update_claude_status()
    footer.addWidget(view.claude_status, 1)
    view.save_feedback = label("", "Muted")
    footer.addWidget(view.save_feedback)
    view.save_btn = QPushButton("Save changes")
    view.save_btn.setObjectName("Primary")
    view.save_btn.clicked.connect(view._save_settings)
    footer.addWidget(view.save_btn)
    main.addLayout(footer)

    def select_page(index):
        view.pages.setCurrentIndex(index)
        current = view.pages.currentWidget()
        # A contextless singleShot can outlive a closed page and abort PyQt
        # when its callback touches the deleted QScrollArea.
        reset = QTimer(current)
        reset.setSingleShot(True)
        reset.timeout.connect(lambda: current.verticalScrollBar().setValue(0))
        reset.timeout.connect(reset.deleteLater)
        reset.start(0)

    view.navigation.currentRowChanged.connect(select_page)
    view.navigation.setCurrentRow(0)
    view.navigation.setFocus()
