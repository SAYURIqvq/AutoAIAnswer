from __future__ import annotations

import io
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig
from ai_screenshot_assistant.backend_api import BackendApi, BackendSession
from ai_screenshot_assistant.capture.screenshot import ScreenCapture
from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.desktop_command_client import DesktopCommandClient
from ai_screenshot_assistant.input.mouse_listener import MouseRoiListener
from ai_screenshot_assistant.ui.streaming_overlay import StreamingOverlay
from ai_screenshot_assistant.websocket_client import DesktopWebSocketPublisher

gAppName = str("QQ音乐")

class UiSignals(QObject):
    status = Signal(str)
    result = Signal(dict)
    error = Signal(str)
    provider_changed = Signal(str)
    stream_started = Signal()
    stream_delta = Signal(str)
    stream_completed = Signal(str)
    stream_error = Signal(str)
    mobile_fullscreen_requested = Signal(dict)


class MainWindow(QMainWindow):
    def __init__(self, backend_url: str | None = None) -> None:
        super().__init__()
        self.backend_url = backend_url or settings.backend_url
        self.setWindowTitle(gAppName)
        self.setMinimumSize(560, 660)
        self.app_settings = QSettings("AI Screenshot Assistant", "Desktop")

        legacy_key = str(self.app_settings.value("api/key", "") or "")
        self.deepseek_key = str(
            self.app_settings.value("providers/deepseek_key", legacy_key or settings.deepseek_api_key) or ""
        )
        self.openrouter_key = str(
            self.app_settings.value("providers/openrouter_key", settings.openrouter_api_key) or ""
        )
        self.openrouter_model = str(
            self.app_settings.value("providers/openrouter_model", settings.openrouter_model) or settings.openrouter_model
        )

        self.signals = UiSignals()
        self.signals.status.connect(self.set_status)
        self.signals.result.connect(self.show_result)
        self.signals.error.connect(self.show_error)
        self.signals.provider_changed.connect(self._on_provider_failover)

        self.overlay = StreamingOverlay(self.app_settings)
        self.signals.stream_started.connect(self.overlay.start_stream)
        self.signals.stream_delta.connect(self.overlay.append_delta)
        self.signals.stream_completed.connect(self.overlay.complete_stream)
        self.signals.stream_error.connect(self.overlay.show_error)

        self.session: BackendSession | None = None
        self.publisher: DesktopWebSocketPublisher | None = None
        self.command_client: DesktopCommandClient | None = None
        self.workflow: AssistantWorkflow | None = None
        self.mouse_listener: MouseRoiListener | None = None
        self._force_quit = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.region_gesture_enabled = self._settings_bool("gestures/region_enabled", True)
        self.fullscreen_gesture_enabled = self._settings_bool("gestures/fullscreen_enabled", True)

        self.status_label = QLabel("状态：准备中")
        self.provider_label = QLabel("当前模型：DeepSeek / deepseek-v4-flash-vision-exp")
        self.deepseek_key_input = QLineEdit(self.deepseek_key)
        self.deepseek_key_input.setEchoMode(QLineEdit.Normal)
        self.deepseek_key_input.setPlaceholderText("可选，填写后优先使用")
        self.openrouter_key_input = QLineEdit(self.openrouter_key)
        self.openrouter_key_input.setEchoMode(QLineEdit.Normal)
        self.openrouter_key_input.setPlaceholderText("可选，仅填这一把也可以用")
        self.openrouter_model_input = QLineEdit(self.openrouter_model)
        self.openrouter_model_input.setPlaceholderText("使用 OpenRouter 时生效")
        self.save_providers_button = QPushButton("保存模型配置")
        self.save_providers_button.clicked.connect(self.save_provider_settings)
        self.save_status = QLabel("")
        self.overlay_toggle = QCheckBox("显示桌面流式悬浮答案")
        self.overlay_toggle.setChecked(False)
        self.overlay_toggle.toggled.connect(self.set_overlay_visible)
        self.region_gesture_toggle = QCheckBox("开启左键长按 2 秒框选手势")
        self.region_gesture_toggle.setChecked(self.region_gesture_enabled)
        self.region_gesture_toggle.toggled.connect(self.set_region_gesture_enabled)
        self.fullscreen_gesture_toggle = QCheckBox("开启右键长按 2 秒全屏截图手势")
        self.fullscreen_gesture_toggle.setChecked(self.fullscreen_gesture_enabled)
        self.fullscreen_gesture_toggle.toggled.connect(self.set_fullscreen_gesture_enabled)
        self.fullscreen_button = QPushButton("截取当前屏幕")
        self.fullscreen_button.clicked.connect(self._capture_current_screen)
        self.mobile_label = QLabel("手机端：正在创建配对链接")
        self.mobile_label.setWordWrap(True)
        self.qr_label = QLabel()
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)

        provider_form = QFormLayout()
        provider_form.addRow("DeepSeek Key（可选）", self.deepseek_key_input)
        provider_form.addRow("OpenRouter Key（可选）", self.openrouter_key_input)
        provider_form.addRow("OpenRouter 模型", self.openrouter_model_input)

        save_row = QHBoxLayout()
        save_row.addWidget(self.save_providers_button)
        save_row.addWidget(self.save_status, 1)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.provider_label)
        layout.addLayout(provider_form)
        layout.addLayout(save_row)
        layout.addWidget(self.overlay_toggle)
        layout.addWidget(self.region_gesture_toggle)
        layout.addWidget(self.fullscreen_gesture_toggle)
        layout.addWidget(self.fullscreen_button)
        layout.addWidget(self.mobile_label)
        layout.addWidget(self.qr_label)
        gesture_hint = QLabel(self._gesture_hint_text())
        gesture_hint.setWordWrap(True)
        layout.addWidget(gesture_hint)
        layout.addWidget(self.logs, 1)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        self.signals.mobile_fullscreen_requested.connect(self._capture_current_screen_from_mobile)
        self._setup_tray_icon()
        self._setup_workflow()
        QTimer.singleShot(600, self._maybe_prompt_macos_permissions)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._log("System tray unavailable; close will exit directly")
            return
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        capture_action = QAction("截取当前屏幕", self)
        capture_action.triggered.connect(self._capture_current_screen)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_from_tray)
        menu = QMenu(self)
        menu.addAction(show_action)
        menu.addAction(capture_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(gAppName)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_main_window()

    def show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_from_tray(self) -> None:
        self._force_quit = True
        self.close()
        QApplication.quit()

    def _settings_bool(self, key: str, default: bool) -> bool:
        value = self.app_settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _build_ai_client(self) -> FailoverVisionClient:
        deepseek = ProviderConfig(
            name="DeepSeek",
            api_key=self.deepseek_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
        openrouter = ProviderConfig(
            name="OpenRouter",
            api_key=self.openrouter_key,
            base_url=settings.openrouter_base_url,
            model=self.openrouter_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
        return FailoverVisionClient(
            deepseek,
            openrouter,
            on_provider_changed=lambda name: self.signals.provider_changed.emit(name),
        )

    def save_provider_settings(self) -> None:
        deepseek_key = self.deepseek_key_input.text().strip()
        openrouter_key = self.openrouter_key_input.text().strip()
        openrouter_model = self.openrouter_model_input.text().strip() or settings.openrouter_model
        if not deepseek_key and not openrouter_key:
            self.save_status.setText("请至少填写 DeepSeek 或 OpenRouter 其中一把 Key")
            self.save_status.setStyleSheet("color: #d33;")
            return
        if openrouter_key:
            self.openrouter_model_input.setText(openrouter_model)
        self.deepseek_key = deepseek_key
        self.openrouter_key = openrouter_key
        self.openrouter_model = openrouter_model
        self.app_settings.setValue("providers/deepseek_key", deepseek_key)
        self.app_settings.setValue("providers/openrouter_key", openrouter_key)
        self.app_settings.setValue("providers/openrouter_model", openrouter_model)
        self.app_settings.sync()
        client = self._build_ai_client()
        if self.workflow is not None:
            self.workflow.ai_client = client
        self.set_provider(client.current_provider)
        if deepseek_key:
            self.save_status.setText("已保存；有 DeepSeek Key 时下一题从 DeepSeek 开始")
        else:
            self.save_status.setText("已保存；将使用 OpenRouter")
        self.save_status.setStyleSheet("color: #198754;")
        self._log("Provider settings updated")

    def set_provider(self, provider: str) -> None:
        if provider == "openrouter":
            self.provider_label.setText(f"当前模型：OpenRouter / {self.openrouter_model}")
        elif provider == "deepseek":
            self.provider_label.setText(f"当前模型：DeepSeek / {settings.deepseek_model}")
        else:
            self.provider_label.setText("当前模型：未配置 Key")

    def _on_provider_failover(self, provider: str) -> None:
        self.set_provider(provider)
        if provider == "openrouter":
            self._log("DeepSeek 额度不足，已切换 OpenRouter")

    def set_overlay_visible(self, visible: bool) -> None:
        if visible:
            self.overlay.show()
            self.overlay.raise_()
        else:
            self.overlay.hide()

    def set_region_gesture_enabled(self, enabled: bool) -> None:
        self.region_gesture_enabled = enabled
        self.app_settings.setValue("gestures/region_enabled", enabled)
        self.app_settings.sync()
        self._log(f"左键框选手势：{'开启' if enabled else '关闭'}")

    def set_fullscreen_gesture_enabled(self, enabled: bool) -> None:
        self.fullscreen_gesture_enabled = enabled
        self.app_settings.setValue("gestures/fullscreen_enabled", enabled)
        self.app_settings.sync()
        self._log(f"右键全屏手势：{'开启' if enabled else '关闭'}")

    def _setup_workflow(self) -> None:
        try:
            self.session = BackendApi(self.backend_url).create_session()
            self.publisher = DesktopWebSocketPublisher(self.backend_url, self.session.session_id)
            self.command_client = DesktopCommandClient(
                self.backend_url,
                self.session.session_id,
                self._handle_desktop_command,
            )
            self.mobile_label.setText(f"手机端：{self.session.pair_url}")
            self._set_qr(self.session.pair_url)
            self._log(f"Mobile URL: {self.session.pair_url}")
        except Exception as exc:
            self.session = None
            self.publisher = None
            self._log(f"Backend unavailable; mobile streaming disabled: {exc}")

        session_id = self.session.session_id if self.session else "local"
        ai_client = self._build_ai_client()
        self.workflow = AssistantWorkflow(
            session_id=session_id,
            capture=ScreenCapture(),
            ai_client=ai_client,
            publisher=self.publisher,
        )
        self.workflow.on_status = self.signals.status.emit
        self.workflow.on_result = self.signals.result.emit
        self.workflow.on_error = self.signals.error.emit
        self.workflow.on_stream_started = self.signals.stream_started.emit
        self.workflow.on_stream_delta = self.signals.stream_delta.emit
        self.workflow.on_stream_completed = self.signals.stream_completed.emit
        self.workflow.on_stream_error = self.signals.stream_error.emit
        self.set_provider(ai_client.current_provider)
        if ai_client.current_provider == "none":
            self.save_status.setText("请至少填写一把 API Key 后保存")
            self.save_status.setStyleSheet("color: #d33;")
        self.mouse_listener = MouseRoiListener(self._left_up, self._second_left_up, self._right_long)
        try:
            self.mouse_listener.start()
            self.workflow.start_capture()
        except Exception as exc:
            self._log(f"Input listener not active: {exc}")

    def _left_up(self, x: int, y: int) -> None:
        if not self.region_gesture_enabled:
            self._log("左键框选手势已关闭")
            return
        if self.workflow is not None:
            self.workflow.left_up(x, y)

    def _second_left_up(self, x: int, y: int) -> None:
        if not self.region_gesture_enabled:
            self._log("左键框选手势已关闭")
            return
        if self.workflow is None or self.mouse_listener is None:
            return
        self.mouse_listener.set_enabled(False)
        threading.Thread(target=self._run_selection, args=(x, y), daemon=True).start()

    def _run_selection(self, x: int, y: int) -> None:
        try:
            if self.workflow is not None:
                self.workflow.second_left_up(x, y)
        finally:
            if self.mouse_listener is not None:
                self.mouse_listener.set_enabled(True)

    def _right_long(self, x: int, y: int) -> None:
        if not self.fullscreen_gesture_enabled:
            self._log("右键全屏手势已关闭")
            return
        self._capture_fullscreen_at(x, y)

    def _capture_fullscreen_at(
        self,
        x: int,
        y: int,
        user_text: str | None = None,
        use_conversation: bool = False,
        is_chat: bool = False,
    ) -> None:
        if self.workflow is None or self.mouse_listener is None:
            return
        self.mouse_listener.set_enabled(False)
        threading.Thread(
            target=self._run_fullscreen,
            args=(x, y, user_text, use_conversation, is_chat),
            daemon=True,
        ).start()

    def _capture_current_screen(self) -> None:
        center = self.frameGeometry().center()
        self._capture_fullscreen_at(center.x(), center.y())

    def _capture_current_screen_from_mobile(self, payload: dict[str, Any]) -> None:
        user_text = str(payload.get("text") or "").strip()
        use_conversation = bool(payload.get("conversation"))
        is_chat = bool(payload.get("chat"))
        if user_text:
            self._log("手机端请求截取当前屏幕并追问")
        else:
            self._log("手机端请求截取当前屏幕")
        center = self.frameGeometry().center()
        self._capture_fullscreen_at(
            center.x(),
            center.y(),
            user_text=user_text or None,
            use_conversation=use_conversation,
            is_chat=is_chat,
        )

    def _handle_desktop_command(self, command: dict[str, Any]) -> None:
        if command.get("type") == "command.fullscreen":
            payload = command.get("payload")
            self.signals.mobile_fullscreen_requested.emit(payload if isinstance(payload, dict) else {})

    def _gesture_hint_text(self) -> str:
        if sys.platform == "darwin":
            return (
                "手势：左键长按 2 秒框选起点，再左键单击终点；"
                "右键或 Control+左键长按 2 秒截取当前屏幕。也可用「截取当前屏幕」按钮。"
                "一图多题会按题号对应作答；生成期间暂停监听"
            )
        return (
            "手势：左键长按 2 秒框选起点，再左键单击终点；"
            "右键长按 2 秒截取当前屏幕全屏。一图多题会按题号对应作答；生成期间暂停监听"
        )

    def _maybe_prompt_macos_permissions(self) -> None:
        from ai_screenshot_assistant.utils.macos_permissions import (
            accessibility_trusted,
            is_macos,
            open_privacy_pane,
            request_screen_recording,
            screen_recording_allowed,
        )

        if not is_macos():
            return
        request_screen_recording()
        missing: list[str] = []
        if not accessibility_trusted():
            missing.append("辅助功能（监听框选和右键手势）")
        if not screen_recording_allowed():
            missing.append("屏幕录制（截取题目）")
        if not missing:
            return
        self._log("macOS 需要授权：" + "、".join(missing))
        QMessageBox.information(
            self,
            "需要 macOS 权限",
            "请在「系统设置 → 隐私与安全性」中允许本应用：\n\n- "
            + "\n- ".join(missing)
            + "\n\n授权后请完全退出应用再重新打开。",
        )
        if not accessibility_trusted():
            open_privacy_pane("Privacy_Accessibility")
        elif not screen_recording_allowed():
            open_privacy_pane("Privacy_ScreenCapture")

    def _run_fullscreen(
        self,
        x: int,
        y: int,
        user_text: str | None = None,
        use_conversation: bool = False,
        is_chat: bool = False,
    ) -> None:
        try:
            if self.workflow is not None:
                self.workflow.process_fullscreen(
                    x,
                    y,
                    user_text=user_text,
                    use_conversation=use_conversation,
                    is_chat=is_chat,
                )
        finally:
            if self.mouse_listener is not None:
                self.mouse_listener.set_enabled(True)

    def set_status(self, message: str) -> None:
        self.status_label.setText(f"状态：{message}")
        self._log(message)

    def show_result(self, result: dict[str, Any]) -> None:
        self._log("AI result completed")

    def show_error(self, message: str) -> None:
        self._log(f"Error: {message}")
        self.status_label.setText("状态：错误")

    def _log(self, message: str) -> None:
        self.logs.append(message)

    def _set_qr(self, url: str) -> None:
        import qrcode
        image = qrcode.make(url)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        self.qr_label.setPixmap(pixmap.scaledToWidth(160))

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._force_quit and self.tray_icon is not None and self.tray_icon.isVisible():
            message = QMessageBox(self)
            message.setWindowTitle("关闭 AI 截图搜题助手")
            message.setText("要最小化到右下角托盘继续运行，还是直接退出？")
            to_tray = message.addButton("最小化到托盘", QMessageBox.ButtonRole.AcceptRole)
            exit_app = message.addButton("直接退出", QMessageBox.ButtonRole.DestructiveRole)
            cancel = message.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            message.setDefaultButton(to_tray)
            message.exec()
            clicked = message.clickedButton()
            if clicked is cancel:
                event.ignore()
                return
            if clicked is to_tray:
                event.ignore()
                self.hide()
                self.tray_icon.showMessage(
                    "AI 截图搜题助手仍在运行",
                    "可从右下角托盘图标恢复窗口或退出。",
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
                return
            if clicked is exit_app:
                self._force_quit = True
        self.overlay.close()
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.publisher is not None:
            self.publisher.close()
        if self.command_client is not None:
            self.command_client.close()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        super().closeEvent(event)
