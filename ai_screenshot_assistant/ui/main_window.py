from __future__ import annotations

import base64
import gc
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig
from ai_screenshot_assistant.ai.models import DEFAULT_MODEL_TIER, TIER_LABELS, normalize_model_tier, tier_options
from ai_screenshot_assistant.backend_api import BackendApi, BackendSession
from ai_screenshot_assistant.capture.screenshot import ScreenCapture
from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.core.messages import Event
from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.desktop_command_client import DesktopCommandClient
from ai_screenshot_assistant.input.mouse_listener import MouseRoiListener
from ai_screenshot_assistant.resources import app_icon_path
from ai_screenshot_assistant.ui.streaming_overlay import StreamingOverlay
from ai_screenshot_assistant.utils.qrcode_image import QR_DISPLAY_PX, pair_qr_png_bytes
from ai_screenshot_assistant.websocket_client import DesktopWebSocketPublisher

gAppName = str("QQMusic")

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
    clear_conversation_requested = Signal()
    model_tier_requested = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, backend_url: str | None = None) -> None:
        super().__init__()
        self.backend_url = backend_url or settings.backend_url
        self.setWindowTitle(gAppName)
        icon = self._app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.setMinimumSize(560, 640)
        self.app_settings = QSettings("AI Screenshot Assistant", "Desktop")

        legacy_key = str(self.app_settings.value("api/key", "") or "")
        self.deepseek_key = str(
            self.app_settings.value("providers/deepseek_key", legacy_key or settings.deepseek_api_key) or ""
        )
        self.openrouter_key = str(
            self.app_settings.value("providers/openrouter_key", settings.openrouter_api_key) or ""
        )
        self.model_tier = normalize_model_tier(
            str(self.app_settings.value("providers/model_tier", settings.model_tier) or DEFAULT_MODEL_TIER)
        )

        self.signals = UiSignals()
        self.signals.status.connect(self.set_status)
        self.signals.result.connect(self.show_result)
        self.signals.error.connect(self.show_error)
        self.signals.provider_changed.connect(self._on_provider_failover)
        self.signals.clear_conversation_requested.connect(self._clear_conversation)
        self.signals.model_tier_requested.connect(self._on_model_tier_requested)

        self.overlay = StreamingOverlay(self.app_settings)
        self.signals.stream_started.connect(self._on_stream_started)
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
        self.provider_label = QLabel("当前模型：未配置")
        self.deepseek_key_input = QLineEdit(self.deepseek_key)
        self.deepseek_key_input.setEchoMode(QLineEdit.Normal)
        self.deepseek_key_input.setPlaceholderText("可选，简单档优先使用")
        self.openrouter_key_input = QLineEdit(self.openrouter_key)
        self.openrouter_key_input.setEchoMode(QLineEdit.Normal)
        self.openrouter_key_input.setPlaceholderText("可选，好/中等档使用通义千问 VL")
        self.model_tier_combo = QComboBox()
        for tier, label, hint in tier_options():
            self.model_tier_combo.addItem(f"{label} · {hint}", tier)
        index = self.model_tier_combo.findData(self.model_tier)
        self.model_tier_combo.setCurrentIndex(index if index >= 0 else 0)
        self.model_tier_combo.currentIndexChanged.connect(self._on_desktop_model_tier)
        self.save_providers_button = QPushButton("保存模型配置")
        self.save_providers_button.clicked.connect(self.save_provider_settings)
        self.save_status = QLabel("")
        self.overlay_toggle = QCheckBox("显示桌面流式悬浮答案")
        self.overlay_toggle.toggled.connect(self.set_overlay_visible)
        overlay_visible = self._settings_bool("overlay/visible", True)
        opacity_percent = int(self.app_settings.value("overlay/opacity_percent", 50) or 50)
        opacity_percent = max(15, min(100, opacity_percent))
        self.opacity_label = QLabel(f"字幕透明度：{opacity_percent}%")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(15, 100)
        self.opacity_slider.setValue(opacity_percent)
        self.opacity_slider.valueChanged.connect(self._on_overlay_opacity)
        self.overlay.set_opacity_percent(opacity_percent)
        font_px = int(self.app_settings.value("overlay/font_px", 18) or 18)
        font_px = max(8, min(22, font_px))
        self.font_label = QLabel(f"字幕字号：{font_px}px")
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 22)
        self.font_slider.setValue(font_px)
        self.font_slider.valueChanged.connect(self._on_overlay_font)
        self.overlay.set_font_px(font_px)
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
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setScaledContents(False)
        self.qr_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.qr_label.setContentsMargins(12, 12, 12, 12)
        self.qr_label.setFixedSize(QR_DISPLAY_PX + 24, QR_DISPLAY_PX + 24)
        self.qr_label.setStyleSheet("QLabel { background: #ffffff; border-radius: 8px; }")
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(72)
        self.logs.setMaximumHeight(140)
        self.logs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.logs.document().setMaximumBlockCount(80)
        self.clear_chat_button = QPushButton("清空对话记录")
        self.clear_chat_button.clicked.connect(self._clear_conversation)

        provider_form = QFormLayout()
        provider_form.addRow("DeepSeek Key（可选）", self.deepseek_key_input)
        provider_form.addRow("OpenRouter Key（可选）", self.openrouter_key_input)
        provider_form.addRow("模型档位", self.model_tier_combo)

        save_row = QHBoxLayout()
        save_row.addWidget(self.save_providers_button)
        save_row.addWidget(self.save_status, 1)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.provider_label)
        layout.addLayout(provider_form)
        layout.addLayout(save_row)
        layout.addWidget(self.overlay_toggle)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_label)
        opacity_row.addWidget(self.opacity_slider, 1)
        layout.addLayout(opacity_row)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_label)
        font_row.addWidget(self.font_slider, 1)
        layout.addLayout(font_row)
        layout.addWidget(self.region_gesture_toggle)
        layout.addWidget(self.fullscreen_gesture_toggle)
        layout.addWidget(self.fullscreen_button)
        layout.addWidget(self.mobile_label)
        qr_wrap = QWidget()
        qr_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        qr_layout = QVBoxLayout(qr_wrap)
        qr_layout.setContentsMargins(0, 8, 0, 8)
        qr_layout.addWidget(self.qr_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(qr_wrap, 0, Qt.AlignmentFlag.AlignHCenter)
        gesture_hint = QLabel(self._gesture_hint_text())
        gesture_hint.setWordWrap(True)
        layout.addWidget(gesture_hint)
        layout.addWidget(self.clear_chat_button)
        layout.addWidget(self.logs)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        content = QWidget()
        content.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        self.signals.mobile_fullscreen_requested.connect(self._capture_current_screen_from_mobile)
        self._setup_tray_icon()
        self._setup_workflow()
        self.overlay_toggle.setChecked(overlay_visible)
        QTimer.singleShot(600, self._maybe_prompt_macos_permissions)

    def _setup_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._log("System tray unavailable; close will exit directly")
            return
        icon = self._app_icon()
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
        self.tray_icon.setIcon(icon)
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

    def _app_icon(self) -> QIcon:
        icon_path = app_icon_path()
        if icon_path is not None:
            icon = QIcon(str(icon_path))
            if not icon.isNull():
                return icon
        icon = QApplication.windowIcon()
        if not icon.isNull():
            return icon
        return QIcon()

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
            model=settings.openrouter_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
        return FailoverVisionClient(
            deepseek,
            openrouter,
            on_provider_changed=lambda name: self.signals.provider_changed.emit(name),
            model_tier=self.model_tier,
        )

    def save_provider_settings(self) -> None:
        deepseek_key = self.deepseek_key_input.text().strip()
        openrouter_key = self.openrouter_key_input.text().strip()
        if not deepseek_key and not openrouter_key:
            self.save_status.setText("请至少填写 DeepSeek 或 OpenRouter 其中一把 Key")
            self.save_status.setStyleSheet("color: #d33;")
            return
        self.deepseek_key = deepseek_key
        self.openrouter_key = openrouter_key
        self.model_tier = normalize_model_tier(self.model_tier_combo.currentData())
        self.app_settings.setValue("providers/deepseek_key", deepseek_key)
        self.app_settings.setValue("providers/openrouter_key", openrouter_key)
        self.app_settings.setValue("providers/model_tier", self.model_tier)
        self.app_settings.sync()
        client = self._build_ai_client()
        if self.workflow is not None:
            self.workflow.ai_client = client
        self._refresh_provider_label()
        self._publish_model_changed()
        if self.model_tier in {"good", "medium"} and openrouter_key:
            self.save_status.setText("已保存；好/中等档使用通义千问 VL")
        elif deepseek_key:
            self.save_status.setText("已保存；简单档优先 DeepSeek Flash")
        else:
            self.save_status.setText("已保存；将使用通义千问 VL")
        self.save_status.setStyleSheet("color: #198754;")
        self._log("Provider settings updated")

    def set_provider(self, provider: str) -> None:
        self._refresh_provider_label(provider)

    def _refresh_provider_label(self, provider: str | None = None) -> None:
        client = self.workflow.ai_client if self.workflow is not None else None
        current = provider or getattr(client, "current_provider", "none")
        model = ""
        if client is not None and hasattr(client, "current_model_id"):
            model = client.current_model_id()
        tier_label = TIER_LABELS.get(self.model_tier, "好")
        if current == "openrouter" and model:
            self.provider_label.setText(f"当前模型：{tier_label} / OpenRouter / {model}")
        elif current == "deepseek" and model:
            self.provider_label.setText(f"当前模型：{tier_label} / DeepSeek / {model}")
        elif current in {"openrouter", "deepseek"}:
            self.provider_label.setText(f"当前模型：{tier_label} / {current}")
        else:
            self.provider_label.setText("当前模型：未配置 Key")

    def _on_provider_failover(self, provider: str) -> None:
        self.set_provider(provider)
        if provider == "openrouter":
            self._log("DeepSeek 额度不足，已切换 OpenRouter")

    def set_overlay_visible(self, visible: bool) -> None:
        self.app_settings.setValue("overlay/visible", visible)
        if visible:
            self.overlay.show()
        else:
            self.overlay.hide()

    def _on_overlay_opacity(self, percent: int) -> None:
        self.opacity_label.setText(f"字幕透明度：{percent}%")
        self.app_settings.setValue("overlay/opacity_percent", percent)
        self.overlay.set_opacity_percent(percent)

    def _on_overlay_font(self, size: int) -> None:
        self.font_label.setText(f"字幕字号：{size}px")
        self.app_settings.setValue("overlay/font_px", max(8, min(22, size)))
        self.overlay.set_font_px(size)

    def _on_stream_started(self) -> None:
        # Overlay visibility is owned only by 「显示桌面流式悬浮答案」.
        # Streaming must not show/raise it, or the main console comes forward too.
        self.overlay.start_stream()

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
        self._refresh_provider_label(ai_client.current_provider)
        self._publish_model_changed()
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
        request_id: str | None = None,
    ) -> None:
        if self.workflow is None or self.mouse_listener is None:
            return
        self.mouse_listener.set_enabled(False)
        threading.Thread(
            target=self._run_fullscreen,
            args=(x, y, user_text, use_conversation, is_chat, request_id),
            daemon=True,
        ).start()

    def _capture_current_screen(self) -> None:
        center = self.frameGeometry().center()
        self._capture_fullscreen_at(center.x(), center.y())

    def _capture_current_screen_from_mobile(self, payload: dict[str, Any]) -> None:
        user_text = str(payload.get("text") or "").strip()
        use_conversation = bool(payload.get("conversation"))
        is_chat = bool(payload.get("chat"))
        request_id = str(payload.get("client_request_id") or "").strip() or None
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
            request_id=request_id,
        )

    def _capture_current_screen_preview_for_mobile(self) -> None:
        if self.workflow is None or self.mouse_listener is None:
            return
        center = self.frameGeometry().center()
        self.mouse_listener.set_enabled(False)
        threading.Thread(
            target=self._run_fullscreen_preview,
            args=(center.x(), center.y()),
            daemon=True,
        ).start()

    def _submit_mobile_screenshots(self, payload: dict[str, Any]) -> None:
        if self.workflow is None or self.mouse_listener is None:
            return
        raw_images = payload.get("images")
        if not isinstance(raw_images, list):
            raw_images = []
        png_images: list[bytes] = []
        for raw_image in raw_images[:5]:
            if not isinstance(raw_image, str):
                continue
            image_data = raw_image.split(",", 1)[1] if "," in raw_image else raw_image
            try:
                png_images.append(base64.b64decode(image_data, validate=True))
            except Exception:
                self._log("手机端提交的截图解码失败，已跳过")
        user_text = str(payload.get("text") or "").strip()
        use_conversation = bool(payload.get("conversation"))
        is_chat = bool(payload.get("chat"))
        request_id = str(payload.get("client_request_id") or "").strip() or None
        self._log(f"手机端提交 {len(png_images)} 张截图" + ("并追问" if user_text else ""))
        self.mouse_listener.set_enabled(False)
        threading.Thread(
            target=self._run_mobile_screenshots,
            args=(png_images, user_text or None, use_conversation, is_chat, request_id),
            daemon=True,
        ).start()

    def _handle_desktop_command(self, command: dict[str, Any]) -> None:
        if command.get("type") == "command.fullscreen":
            payload = command.get("payload")
            self.signals.mobile_fullscreen_requested.emit(payload if isinstance(payload, dict) else {})
        elif command.get("type") == "command.capture_fullscreen":
            self._capture_current_screen_preview_for_mobile()
        elif command.get("type") == "command.submit_screenshots":
            payload = command.get("payload")
            self._submit_mobile_screenshots(payload if isinstance(payload, dict) else {})
        elif command.get("type") == "command.clear_conversation":
            self.signals.clear_conversation_requested.emit()
        elif command.get("type") == "command.set_model_tier":
            payload = command.get("payload")
            tier = ""
            if isinstance(payload, dict):
                tier = str(payload.get("tier") or "")
            self.signals.model_tier_requested.emit(tier)

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
        request_id: str | None = None,
    ) -> None:
        try:
            if self.workflow is not None:
                self.workflow.process_fullscreen(
                    x,
                    y,
                    user_text=user_text,
                    use_conversation=use_conversation,
                    is_chat=is_chat,
                    request_id=request_id,
                )
        finally:
            if self.mouse_listener is not None:
                self.mouse_listener.set_enabled(True)

    def _run_fullscreen_preview(self, x: int, y: int) -> None:
        try:
            if self.workflow is not None:
                self.workflow.capture_fullscreen_for_mobile(x, y)
        finally:
            if self.mouse_listener is not None:
                self.mouse_listener.set_enabled(True)

    def _run_mobile_screenshots(
        self,
        png_images: list[bytes],
        user_text: str | None = None,
        use_conversation: bool = False,
        is_chat: bool = False,
        request_id: str | None = None,
    ) -> None:
        try:
            if self.workflow is not None:
                self.workflow.process_mobile_images(
                    png_images,
                    user_text=user_text,
                    use_conversation=use_conversation,
                    is_chat=is_chat,
                    request_id=request_id,
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
        pixmap = QPixmap()
        pixmap.loadFromData(pair_qr_png_bytes(url), "PNG")
        scaled = pixmap.scaled(
            QR_DISPLAY_PX,
            QR_DISPLAY_PX,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.qr_label.setPixmap(scaled)
        self.qr_label.setFixedSize(scaled.width() + 24, scaled.height() + 24)

    def _on_desktop_model_tier(self, _index: int) -> None:
        self._apply_model_tier(str(self.model_tier_combo.currentData() or DEFAULT_MODEL_TIER))

    def _on_model_tier_requested(self, tier: str) -> None:
        self._apply_model_tier(tier, sync_combo=True)

    def _apply_model_tier(self, tier: str, *, sync_combo: bool = False) -> None:
        if self.workflow is None:
            self.model_tier = normalize_model_tier(tier)
            return
        payload = self.workflow.set_model_tier(tier)
        self.model_tier = normalize_model_tier(str(payload.get("tier") or tier))
        self.app_settings.setValue("providers/model_tier", self.model_tier)
        self.app_settings.sync()
        if sync_combo:
            self.model_tier_combo.blockSignals(True)
            index = self.model_tier_combo.findData(self.model_tier)
            if index >= 0:
                self.model_tier_combo.setCurrentIndex(index)
            self.model_tier_combo.blockSignals(False)
        self._refresh_provider_label()

    def _publish_model_changed(self) -> None:
        if self.workflow is None:
            return
        client = self.workflow.ai_client
        apply_tier = getattr(client, "apply_model_tier", None)
        if callable(apply_tier):
            payload = apply_tier(self.model_tier, notify=False).to_payload()
        else:
            payload = {"tier": self.model_tier}
        if self.publisher is not None:
            event = Event(
                type="model.changed",
                session_id=self.workflow.session_id,
                payload=payload,
            )
            try:
                self.publisher.send_sync(event.to_dict())
            except Exception as exc:
                self._log(f"Mobile update failed: {exc}")
        self._refresh_provider_label()

    def _clear_conversation(self) -> None:
        if self.workflow is not None:
            self.workflow.clear_conversation()
        self.overlay.clear()
        self.logs.clear()
        gc.collect()
        self._log("已清空对话记录并释放内存")

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
                event.accept()
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
        if self._force_quit:
            QApplication.quit()
