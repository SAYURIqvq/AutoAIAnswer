from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox

from ai_screenshot_assistant.core.workflow import AssistantWorkflow
from ai_screenshot_assistant.ui.main_window import MainWindow


class Speech:
    def __init__(self):
        self.stops = 0
        self.spoken = []

    def stop(self):
        self.stops += 1

    def say(self, text):
        self.spoken.append(text)


@pytest.mark.parametrize('chat', [False, True])
def test_every_answer_lane_stops_previous_speech_and_reads_result(chat):
    class AI:
        def analyze_images_stream(self, *args, **kwargs):
            yield '答案：A'

    workflow = AssistantWorkflow('test', None, AI())
    speech = Speech()
    workflow.on_answer_started = speech.stop
    workflow.on_answer_completed = speech.say
    workflow.process_mobile_images([b'png'], is_chat=chat, use_conversation=chat)
    assert speech.stops == 1
    assert len(speech.spoken) == 1
    assert 'A' in speech.spoken[0]


def test_cancelled_queued_answer_cannot_speak():
    workflow = AssistantWorkflow('test', None, None)
    queued, spoken = [], []
    workflow.dispatch_local = queued.append
    old, _ = workflow._begin_analysis('chat')
    workflow._run_if_active(old, lambda: spoken.append('old'), include_chat=True)
    workflow._begin_analysis('chat')
    for callback in queued:
        callback()
    assert spoken == []


def test_desktop_checkbox_is_independent_of_mobile_checkbox(qapp, tmp_path):
    target = SimpleNamespace(
        app_settings=QSettings(str(tmp_path / 'voice.ini'), QSettings.IniFormat),
        desktop_speech=Speech(), desktop_read_toggle=QCheckBox(),
        auto_read_toggle=QCheckBox(),
    )
    published = []
    target._publish_auto_read_mode = lambda: published.append(target.auto_read_toggle.isChecked())
    target.auto_read_toggle.setChecked(True)
    MainWindow._set_auto_read(target, True)
    MainWindow._read_desktop_answer(target, 'silent')
    assert target.desktop_speech.spoken == []
    target.desktop_read_toggle.setChecked(True)
    MainWindow._set_desktop_read(target, True)
    MainWindow._read_desktop_answer(target, 'answer')
    assert target.desktop_speech.spoken == ['answer']
    MainWindow._set_desktop_read(target, False)
    assert target.auto_read_toggle.isChecked()
    assert published == [True]
    assert target.app_settings.value('voice/auto_read', type=bool)
    assert not target.app_settings.value('voice/desktop_read', type=bool)


def test_synchronous_ui_dispatch_does_not_deadlock():
    workflow = AssistantWorkflow('test', None, None)
    started = []
    workflow.dispatch_local = lambda callback: callback()
    workflow.on_answer_started = lambda: started.append(True)
    workflow._begin_analysis()
    assert started == [True]
