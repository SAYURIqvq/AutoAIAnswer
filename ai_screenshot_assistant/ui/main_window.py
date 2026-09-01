from __future__ import annotations

import io
import threading
from typing import Any

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_screenshot_assistant.ai.client import FailoverVisionClient, ProviderConfig
from ai_screenshot_assistant.backend_api import BackendApi, BackendSession
from ai_screenshot_assistant.capture.screenshot import ScreenCapture
from ai_screenshot_assistant.config import settings
from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.input.mouse_listener import MouseRoiListener
from ai_screenshot_assistant.ui.streaming_overlay import StreamingOverlay
from ai_screenshot_assistant.websocket_client import DesktopWebSocketPublisher


class UiSignals(QObject):
    status = Signal(str)
    result = Signal(dict)
    error = Signal(str)
    provider_changed = Signal(str)
    stream_started = Signal()
    stream_delta = Signal(str)
    stream_completed = Signal(str)
    stream_error = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, backend_url: str | None = None) -> None:
        super().__init__()
        self.backend_url = backend_url or settings.backend_url
        self.setWindowTitle("AI 截图搜题助手")
        self.setMinimumSize(560, 620)
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
        self.signals.provider_changed.connect(self.set_provider)

        self.overlay = StreamingOverlay(self.app_settings)
        self.signals.stream_started.connect(self.overlay.start_stream)
        self.signals.stream_delta.connect(self.overlay.append_delta)
        self.signals.stream_completed.connect(self.overlay.complete_stream)
        self.signals.stream_error.connect(self.overlay.show_error)

        self.session: BackendSession | None = None
        self.publisher: DesktopWebSocketPublisher | None = None
        self.workflow: AssistantWorkflow | None = None
        self.mouse_listener: MouseRoiListener | None = None

        self.status_label = QLabel("状态：准备中")
        self.provider_label = QLabel("当前模型：DeepSeek / deepseek-v4-flash-vision-exp")
        self.deepseek_key_input = QLineEdit(self.deepseek_key)
        self.deepseek_key_input.setEchoMode(QLineEdit.Normal)
        self.openrouter_key_input = QLineEdit(self.openrouter_key)
        self.openrouter_key_input.setEchoMode(QLineEdit.Normal)
        self.openrouter_model_input = QLineEdit(self.openrouter_model)
        self.save_providers_button = QPushButton("保存模型配置")
        self.save_providers_button.clicked.connect(self.save_provider_settings)
        self.save_status = QLabel("")
        self.overlay_toggle = QCheckBox("显示桌面流式悬浮答案")
        self.overlay_toggle.setChecked(False)
        self.overlay_toggle.toggled.connect(self.set_overlay_visible)
        self.mobile_label = QLabel("手机端：正在创建配对链接")
        self.mobile_label.setWordWrap(True)
        self.qr_label = QLabel()
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)

        provider_form = QFormLayout()
        provider_form.addRow("DeepSeek Key（首选）", self.deepseek_key_input)
        provider_form.addRow("OpenRouter Key（402 备用）", self.openrouter_key_input)
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
        layout.addWidget(self.mobile_label)
        layout.addWidget(self.qr_label)
        layout.addWidget(QLabel("手势：起点左键长按 2 秒，终点普通左键单击；生成期间暂停监听"))
        layout.addWidget(self.logs, 1)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        self._setup_workflow()

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
        openrouter_model = self.openrouter_model_input.text().strip()
        if not deepseek_key or not openrouter_key or not openrouter_model:
            self.save_status.setText("两把 Key 和模型 ID 均不能为空")
            self.save_status.setStyleSheet("color: #d33;")
            return
        self.deepseek_key = deepseek_key
        self.openrouter_key = openrouter_key
        self.openrouter_model = openrouter_model
        self.app_settings.setValue("providers/deepseek_key", deepseek_key)
        self.app_settings.setValue("providers/openrouter_key", openrouter_key)
        self.app_settings.setValue("providers/openrouter_model", openrouter_model)
        self.app_settings.sync()
        if self.workflow is not None:
            self.workflow.ai_client = self._build_ai_client()
        self.set_provider("deepseek")
        self.save_status.setText("已保存；下一题从 DeepSeek 开始")
        self.save_status.setStyleSheet("color: #198754;")
        self._log("Provider settings updated")

    def set_provider(self, provider: str) -> None:
        if provider == "openrouter":
            self.provider_label.setText(f"当前模型：OpenRouter / {self.openrouter_model}")
            self._log("DeepSeek 额度不足，已切换 OpenRouter")
        else:
            self.provider_label.setText(f"当前模型：DeepSeek / {settings.deepseek_model}")

    def set_overlay_visible(self, visible: bool) -> None:
        if visible:
            self.overlay.show()
            self.overlay.raise_()
        else:
            self.overlay.hide()

    def _setup_workflow(self) -> None:
        try:
            self.session = BackendApi(self.backend_url).create_session()
            self.publisher = DesktopWebSocketPublisher(self.backend_url, self.session.session_id)
            self.mobile_label.setText(f"手机端：{self.session.pair_url}")
            self._set_qr(self.session.pair_url)
            self._log(f"Mobile URL: {self.session.pair_url}")
        except Exception as exc:
            self.session = None
            self.publisher = None
            self._log(f"Backend unavailable; mobile streaming disabled: {exc}")

        session_id = self.session.session_id if self.session else "local"
        self.workflow = AssistantWorkflow(
            session_id=session_id,
            capture=ScreenCapture(),
            ai_client=self._build_ai_client(),
            publisher=self.publisher,
        )
        self.workflow.on_status = self.signals.status.emit
        self.workflow.on_result = self.signals.result.emit
        self.workflow.on_error = self.signals.error.emit
        self.workflow.on_stream_started = self.signals.stream_started.emit
        self.workflow.on_stream_delta = self.signals.stream_delta.emit
        self.workflow.on_stream_completed = self.signals.stream_completed.emit
        self.workflow.on_stream_error = self.signals.stream_error.emit

        self.mouse_listener = MouseRoiListener(self._left_up, self._second_left_up)
        try:
            self.mouse_listener.start()
            self.workflow.start_capture()
        except Exception as exc:
            self._log(f"Input listener not active: {exc}")

    def _left_up(self, x: int, y: int) -> None:
        if self.workflow is not None:
            self.workflow.left_up(x, y)

    def _second_left_up(self, x: int, y: int) -> None:
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
        self.overlay.close()
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.publisher is not None:
            self.publisher.close()
        super().closeEvent(event)
