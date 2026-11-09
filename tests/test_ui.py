from unittest.mock import Mock

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from turbo_whisper.config import Config
from turbo_whisper.main import SignalBridge, TurboWhisper


def test_navigation_is_separate_from_compact_recording_view(window, qapp):
    window._toggle_settings()
    qapp.processEvents()
    assert window.settings_panel.isVisible()
    assert not window.isVisible()
    assert window.width() <= 420
    for index in range(4):
        window.navigation.setCurrentRow(index)
        qapp.processEvents()
        assert window.pages.currentIndex() == index
        assert window.pages.currentWidget().verticalScrollBar().value() == 0
    window.settings_panel.resize(740, 560)
    qapp.processEvents()
    assert window.save_btn.isVisible()
    assert window.save_btn.geometry().right() <= window.settings_panel.width()


def test_hidden_api_key_is_editable_and_saved(window, qapp):
    window.api_key_input.setText("synthetic-secret")
    assert not window.api_key_input.isReadOnly()
    assert window.api_key_input.echoMode() == QLineEdit.EchoMode.Password
    window._save_settings()
    assert Config.load().api_key == "synthetic-secret"
    window._toggle_key_visibility()
    assert window.api_key_input.text() == "synthetic-secret"
    assert window.api_key_input.echoMode() == QLineEdit.EchoMode.Normal


def test_saving_interaction_options_reloads_shortcut_once(window):
    reloads = Mock()
    window.settings_saved.connect(reloads)
    window.hotkey_input.setText("ctrl+alt+w")
    window.hold_checkbox.setChecked(True)
    window.timeout_input.setValue(600)
    window._save_settings()
    assert Config.load().hotkey == ["ctrl", "alt", "w"]
    assert Config.load().push_to_talk
    assert Config.load().transcription_timeout == 600
    reloads.assert_called_once_with()


def test_invalid_settings_do_not_destroy_saved_config(window):
    window.config.save()
    before = Config.get_config_path().read_bytes()
    window.api_url_input.setText("not an endpoint")
    window._save_settings()
    assert Config.get_config_path().read_bytes() == before
    assert "valid HTTP" in window.save_feedback.text()
    window.api_url_input.setText("http://localhost:8000/transcribe")
    window.hotkey_input.setText("ctrl+unsupported-key")
    window._save_settings()
    assert Config.get_config_path().read_bytes() == before


def test_local_settings_save_without_api_credentials(window, qapp):
    window.navigation.setCurrentRow(1)
    window._toggle_settings()
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("local"))
    qapp.processEvents()
    assert window.local_settings.isVisible()
    assert not window.api_settings.isVisible()
    window.api_url_input.setText("")
    window.model_input.setText("")
    window.local_model_input.setText("small")
    window.local_files_checkbox.setChecked(True)
    window.live_checkbox.setChecked(True)
    window._save_settings()
    config = Config.load()
    assert config.transcription_backend == "local"
    assert config.local_model == "small"
    assert config.local_files_only
    assert config.live_transcription


def test_invalid_local_settings_leave_config_untouched(window):
    window.config.save()
    before = Config.get_config_path().read_bytes()
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("local"))
    window.local_model_input.clear()
    window._save_settings()
    assert "local model" in window.save_feedback.text()
    assert Config.get_config_path().read_bytes() == before
    window.local_model_input.setText("base")
    window.local_compute_combo.setCurrentIndex(window.local_compute_combo.findData("float16"))
    window._save_settings()
    assert "precision on CPU" in window.save_feedback.text()
    assert Config.get_config_path().read_bytes() == before


def test_start_button_and_escape_are_real_actions(window, qapp):
    record, cancel = Mock(), Mock()
    window.record_requested.connect(record)
    window.cancel_requested.connect(cancel)
    QTest.mouseClick(window.record_btn, Qt.MouseButton.LeftButton)
    record.assert_called_once_with()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    cancel.assert_called_once_with()


def test_cpp_settings_save_and_hide_other_backends(window, qapp, tmp_path):
    model = tmp_path / "ggml-large-v3.bin"
    model.write_bytes(b"synthetic model")
    window.navigation.setCurrentRow(1)
    window._toggle_settings()
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("whisper_cpp"))
    window.cpp_model_input.setText(str(model))
    qapp.processEvents()
    assert window.cpp_settings.isVisible()
    assert not window.local_settings.isVisible()
    assert not window.api_settings.isVisible()
    window._save_settings()
    loaded = Config.load()
    assert loaded.transcription_backend == "whisper_cpp"
    assert loaded.whisper_cpp_model == str(model)
    assert not loaded.whisper_cpp_require_gpu
    assert not loaded.whisper_cpp_use_gpu


def test_cpu_and_optional_acceleration_controls_are_consistent(window):
    assert not window.cpp_use_gpu_checkbox.isChecked()
    assert not window.cpp_require_gpu_checkbox.isEnabled()
    window.cpp_use_gpu_checkbox.setChecked(True)
    window.cpp_require_gpu_checkbox.setChecked(True)
    assert window.cpp_require_gpu_checkbox.isEnabled()
    window.cpp_use_gpu_checkbox.setChecked(False)
    assert not window.cpp_require_gpu_checkbox.isChecked()


def test_cpp_missing_model_does_not_overwrite_settings(window):
    window.config.save()
    before = Config.get_config_path().read_bytes()
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("whisper_cpp"))
    window.cpp_model_input.setText("/missing-model.bin")
    window._save_settings()
    assert "existing whisper.cpp model" in window.save_feedback.text()
    assert Config.get_config_path().read_bytes() == before


def test_history_copy_preserves_full_plain_text(window, qapp):
    text = "<b>This is plain text, with a complete sentence longer than forty characters.</b>"
    window.config.history = [{"text": text, "timestamp": "2026-10-29T12:00:00"}]
    window._refresh_history()
    item = window.history_list.itemWidget(window.history_list.item(0))
    assert item.findChild(QLabel).textFormat() == Qt.TextFormat.PlainText
    QTest.mouseClick(item.findChild(QPushButton), Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == text


def test_hold_events_are_ordered_on_qt_thread_even_for_a_short_tap(qapp):
    controller = object.__new__(TurboWhisper)
    controller.config = Config(push_to_talk=True)
    controller.signals = SignalBridge()
    transitions = []
    controller.signals.recording_requested.connect(
        transitions.append, Qt.ConnectionType.QueuedConnection
    )
    controller._on_hotkey_activate()
    controller._on_hotkey_deactivate()
    qapp.processEvents()
    assert transitions == [True, False]


def test_old_focused_window_result_cannot_overwrite_a_new_recording():
    controller = object.__new__(TurboWhisper)
    controller.window = Mock()
    controller.is_recording = True
    controller._recording_token = 2
    controller._on_focused_window_detected("Old editor", 1)
    controller.window.set_status.assert_not_called()
    controller._on_focused_window_detected("Current editor", 2)
    controller.window.hints_label.setToolTip.assert_called_once_with(
        "Dictating into Current editor"
    )
    controller.window.set_status.assert_not_called()  # Focus detection is not capture readiness.


def test_waveform_stops_its_timer_when_hidden(window, qapp):
    window.show()
    window.waveform.set_recording(True)
    qapp.processEvents()
    assert window.waveform.animation_timer.isActive()
    window.hide()
    qapp.processEvents()
    assert not window.waveform.animation_timer.isActive()


def test_pending_scroll_reset_cannot_access_a_destroyed_page(window, qapp, monkeypatch):
    import sys

    from PyQt6.QtCore import QCoreApplication, QEvent

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    window.navigation.setCurrentRow(1)
    page = window.pages.currentWidget()
    window.pages.removeWidget(page)
    page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert not errors


def test_launcher_reopens_the_existing_settings_window(qapp, monkeypatch):
    import uuid

    from PyQt6.QtNetwork import QLocalSocket
    from PyQt6.QtTest import QSignalSpy

    from turbo_whisper import main

    name = "turbo-whisper-test-" + uuid.uuid4().hex
    monkeypatch.setattr(main, "_activation_name", lambda: name)
    controller = object.__new__(TurboWhisper)
    controller.app = qapp
    controller._show_settings = Mock()
    controller._setup_activation_server()
    activated = QSignalSpy(controller._activation_server.newConnection)
    socket = QLocalSocket()
    try:
        socket.connectToServer(name)
        assert socket.waitForConnected(500)
        # Windows may finish the named-pipe connection before Qt dispatches its signal.
        if not activated:
            assert activated.wait(1500)
        controller._show_settings.assert_called_once()
    finally:
        socket.close()
        controller._activation_server.close()
