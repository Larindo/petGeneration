"""Character workshop: editable creative fields, locked prompts, inbox and jobs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from .app import command
from .project import (
    create_project, export_package, import_package, load_project, pending_inputs,
    save_project, MEDIA,
    sync_identity, DEFAULT_PERSONALITY, DEFAULT_COMMUNICATION_STYLE,
)
from .prompts import ACTIONS, DEFAULT_APPEARANCE, action_by_id, build_prompt
from .theme import CharacterPreview, PixelTitle, WorkshopSelect
from pet.settings_widgets import BrowserDoubleSpinBox


class StudioDialog(QDialog):
    def __init__(self, parent=None, *, data_dir=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        if data_dir is None:
            from pet.config import Config
            data_dir = Config().dir
        self.data_dir = Path(data_dir)
        self.projects = self.data_dir / "studio" / "projects"
        self.characters = self.data_dir / "characters"
        self.projects.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("桌宠孵化基地")
        self.setObjectName("characterStudio")
        self.resize(1100, 780)
        self.setMinimumSize(720, 500)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        font.setPixelSize(13)
        self.setFont(font)
        self.apply_theme()
        self.project_path = None
        self.project = None
        self.action_id = "portrait"
        self.loading = False
        self.worker = None
        self.pet_process = None
        self.buffer = ""
        self.observed = None
        self.finished_signature = None
        self.event_path = None
        self.last_event = None
        self.rows = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        title = PixelTitle("桌宠孵化基地")
        title.setObjectName("studioTitle")
        toolbar.addWidget(title)
        self.project_select = WorkshopSelect()
        self.project_select.setMinimumWidth(180)
        self.project_select.setAccessibleName("角色项目")
        toolbar.addWidget(self.project_select, 1)
        toolbar.addWidget(self.button("新建角色", "add", self.new_project))
        toolbar.addWidget(self.button("导入角色包", "file", self.import_pack))
        layout.addLayout(toolbar)
        tabs = QTabWidget()
        self.tabs = tabs
        layout.addWidget(tabs, 1)
        self.build_prompt_tab(tabs)
        self.build_personality_tab(tabs)
        self.build_assets_tab(tabs)
        self.status = QLabel("新建角色或选择已有项目")
        self.status.setObjectName("studioStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.project_select.currentIndexChanged.connect(self.select_project)
        self.refresh_projects()
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.watch_inbox)
        self.timer.start()

    def button(self, text, icon, callback, *, primary=False):
        from pet.context_menus.icons import vector_widget_icon
        button = QPushButton(text, self)
        if primary:
            button.setProperty("settingsDark", False)
        button.setIcon(vector_widget_icon(button, icon))
        button.setToolTip(text)
        button.setProperty("studioPrimary", primary)
        button.clicked.connect(callback)
        return button

    def apply_theme(self, theme="dark"):
        from .theme import apply_workshop_theme
        apply_workshop_theme(self, dark=theme != "light")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "prompt_split"):
            # Stack the editors before either column becomes too narrow to read.
            orientation = Qt.Orientation.Vertical if self.width() < 960 else Qt.Orientation.Horizontal
            if self.prompt_split.orientation() != orientation:
                self.prompt_split.setOrientation(orientation)
                self.prompt_split.setSizes([440, 560])

    def paintEvent(self, event):
        super().paintEvent(event)
        from .theme import paint_workshop_background
        paint_workshop_background(self)

    def section_label(self, text):
        label = QLabel(text)
        label.setProperty("studioSection", True)
        return label

    def add_scroll_tab(self, tabs, page, title):
        page.setObjectName("studioPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        page.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        tabs.addTab(scroll, title)

    def build_prompt_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        self.prompt_split = QSplitter(Qt.Orientation.Horizontal)
        self.prompt_split.setChildrenCollapsible(False)
        self.prompt_split.setHandleWidth(18)
        editor = QWidget()
        edit_layout = QVBoxLayout(editor)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(10)
        edit_layout.addWidget(self.section_label("01  /  角色设定"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("例如：咕咕嘎嘎")
        self.appearance = QPlainTextEdit(DEFAULT_APPEARANCE)
        self.appearance.setMinimumHeight(150)
        self.appearance.setMaximumHeight(190)
        self.appearance.setAccessibleName("可自定义形象与风格")
        form = QFormLayout()
        form.addRow("角色名称", self.name)
        edit_layout.addLayout(form)
        edit_layout.addWidget(QLabel("形象与风格"))
        edit_layout.addWidget(self.appearance)
        edit_layout.addWidget(self.section_label("02  /  动作设定"))
        self.action_select = WorkshopSelect()
        self.action_select.addItem("角色母版 · 图片", "portrait")
        for action in ACTIONS:
            self.action_select.addItem(f"{action.label} · {action.id}", action.id)
        edit_layout.addWidget(self.action_select)
        self.description = QPlainTextEdit()
        self.description.setMinimumHeight(65)
        self.description.setMaximumHeight(100)
        self.description.setAccessibleName("可自定义动作描述")
        edit_layout.addWidget(self.description)
        row = QHBoxLayout()
        row.addWidget(QLabel("时长"))
        self.seconds = BrowserDoubleSpinBox()
        self.seconds.setFixedWidth(120)
        self.seconds.setRange(1, 12)
        self.seconds.setSingleStep(.5)
        self.seconds.setSuffix(" 秒")
        row.addWidget(self.seconds)
        row.addStretch(1)
        row.addWidget(self.button("恢复动作示例", "update", self.reset_action))
        edit_layout.addLayout(row)
        edit_layout.addStretch(1)
        output = QWidget()
        output_layout = QVBoxLayout(output)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(10)
        output_header = QHBoxLayout()
        output_header.addWidget(self.section_label("03  /  完整提示词"))
        output_header.addStretch(1)
        output_header.addWidget(self.button("复制完整提示词", "copy", self.copy_prompt, primary=True))
        output_layout.addLayout(output_header)
        self.animation_hint = QLabel("请将角色母版图片与下方完整提示词一起发送给生成视频的 AI。")
        self.animation_hint.setObjectName("animationHint")
        self.animation_hint.setWordWrap(True)
        self.animation_hint.setVisible(False)
        output_layout.addWidget(self.animation_hint)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName("promptOutput")
        self.prompt.setReadOnly(True)
        self.prompt.setAccessibleName("完整提示词（固定规范只读）")
        self.prompt.setMinimumHeight(300)
        output_layout.addWidget(self.prompt, 1)
        self.prompt_split.addWidget(editor)
        self.prompt_split.addWidget(output)
        self.prompt_split.setSizes([440, 560])
        layout.addWidget(self.prompt_split)
        self.add_scroll_tab(tabs, page, "形象与提示词")
        self.action_select.currentIndexChanged.connect(self.change_action)
        self.name.editingFinished.connect(self.persist)
        self.appearance.textChanged.connect(self.edit_changed)
        self.description.textChanged.connect(self.edit_changed)
        self.seconds.valueChanged.connect(self.edit_changed)

    def build_personality_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        self.personality = QPlainTextEdit(DEFAULT_PERSONALITY)
        self.communication_style = QPlainTextEdit(DEFAULT_COMMUNICATION_STYLE)
        for title, editor, example in (
            ("性格", self.personality, DEFAULT_PERSONALITY),
            ("沟通习惯", self.communication_style, DEFAULT_COMMUNICATION_STYLE),
        ):
            label = self.section_label(title)
            label.setBuddy(editor)
            editor.setAccessibleName(title)
            editor.setAccessibleDescription("最多3000字；留空表示不指定。")
            editor.setPlaceholderText("例如：" + example)
            editor.setMinimumHeight(100)
            layout.addWidget(label)
            layout.addWidget(editor, 1)
            editor.textChanged.connect(self.persist)
        self.phrases = QLineEdit("你好呀~ | 陪你一会儿~")
        form = QFormLayout()
        form.addRow("自动台词（用 | 分隔）", self.phrases)
        layout.addLayout(form)
        self.phrases.editingFinished.connect(self.persist)
        row = QHBoxLayout()
        row.addStretch(1)
        self.save_identity_button = self.button("保存角色设定", "save", self.save_identity, primary=True)
        row.addWidget(self.save_identity_button)
        layout.addLayout(row)
        self.add_scroll_tab(tabs, page, "性格与交流")

    def save_identity(self):
        if self.worker:
            self.status.setText("素材正在处理，请等待完成后保存角色设定")
            return
        if not self.persist():
            return
        try:
            sync_identity(self.project_path, self.characters)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        self.status.setText("角色设定已保存")

    def build_assets_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.section_label("素材目录"))
        self.inbox = QLineEdit()
        self.inbox.setReadOnly(True)
        self.inbox.setAccessibleName("素材投放目录")
        layout.addWidget(self.inbox)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.button("打开素材目录", "file", self.open_inbox))
        toolbar.addWidget(self.button("选择素材", "add", self.pick_media))
        self.auto = QCheckBox("自动处理新素材")
        toolbar.addWidget(self.auto)
        layout.addLayout(toolbar)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(16)
        self.assets = QListWidget()
        self.assets.setMinimumHeight(170)
        self.assets.setAccessibleName("动作素材与处理状态")
        split.addWidget(self.assets)
        self.preview = CharacterPreview("尚无角色预览")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumWidth(180)
        self.preview.setObjectName("petPreview")
        split.addWidget(self.preview)
        split.setSizes([420, 360])
        layout.addWidget(split, 1)
        options = QHBoxLayout()
        self.trim_start = BrowserDoubleSpinBox()
        self.trim_end = BrowserDoubleSpinBox()
        for widget in (self.trim_start, self.trim_end):
            widget.setFixedWidth(140)
            widget.setRange(0, 60)
            widget.setDecimals(2)
            widget.setSuffix(" 秒")
        self.trim_end.setSpecialValueText("视频末尾")
        self.facing = WorkshopSelect()
        self.facing.addItem("朝左", "left")
        self.facing.addItem("朝右（处理时翻转）", "right")
        for title, widget in (("截取起点", self.trim_start), ("截取终点", self.trim_end),
                              ("走路视频原始朝向", self.facing)):
            column = QVBoxLayout()
            label = QLabel(title)
            label.setBuddy(widget)
            column.addWidget(label)
            column.addWidget(widget)
            options.addLayout(column, 1)
        layout.addLayout(options)
        for widget in (self.trim_start, self.trim_end):
            widget.valueChanged.connect(self.asset_options_changed)
        self.facing.currentIndexChanged.connect(self.asset_options_changed)
        self.assets.currentRowChanged.connect(self.asset_selected)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setObjectName("processLog")
        self.log.setReadOnly(True)
        self.log.setFixedHeight(64)
        layout.addWidget(self.log)
        self.installed_select = WorkshopSelect()
        self.installed_select.setAccessibleName("已安装角色")
        layout.addWidget(self.installed_select)
        controls = QHBoxLayout()
        self.process_button = self.button("处理新素材", "play", self.start_processing)
        self.retry_button = self.button("重新处理失败项", "update", self.retry_failed)
        self.launch_button = self.button("使用此角色", "play", self.launch_pet, primary=True)
        self.export_button = self.button("导出角色包", "download", self.export_pack)
        for b in [self.process_button, self.retry_button, self.launch_button, self.export_button]:
            controls.addWidget(b)
        layout.addLayout(controls)
        self.add_scroll_tab(tabs, page, "素材与桌宠")

    def refresh_projects(self, selected=None):
        self.project_select.blockSignals(True)
        self.project_select.clear()
        for path in sorted(self.projects.iterdir()):
            if not (path / "project.json").is_file():
                continue
            try:
                project = load_project(path)
                self.project_select.addItem(project["name"], str(path))
            except (ValueError, KeyError, OSError):
                continue
        if selected:
            self.project_select.setCurrentIndex(self.project_select.findData(str(selected)))
        self.project_select.blockSignals(False)
        self.select_project()

    def new_project(self):
        if self.worker:
            return
        path = create_project(self.projects, self.name.text().strip() or "我的桌宠",
                              self.appearance.toPlainText().strip() or DEFAULT_APPEARANCE)
        self.refresh_projects(path)

    def select_project(self, *_):
        raw = self.project_select.currentData()
        self.project_path = Path(raw) if raw else None
        self.project = load_project(self.project_path) if raw else None
        self.loading = True
        if self.project:
            self.name.setText(self.project["name"])
            self.appearance.setPlainText(self.project["appearance"])
            self.phrases.setText(" | ".join(self.project["phrases"]))
            self.personality.setPlainText(self.project["personality"])
            self.communication_style.setPlainText(self.project["communication_style"])
            self.inbox.setText(str(self.project_path / "inbox"))
        self.save_identity_button.setEnabled(self.project is not None and self.worker is None)
        self.loading = False
        self.observed = self.finished_signature = None
        self.change_action()
        self.refresh_assets()

    def change_action(self, *_):
        self.action_id = self.action_select.currentData()
        action = action_by_id(self.action_id)
        self.animation_hint.setVisible(action is not None)
        self.loading = True
        self.description.setEnabled(action is not None)
        self.seconds.setEnabled(action is not None)
        raw = (self.project or {}).get("actions", {}).get(self.action_id, {})
        self.description.setPlainText(raw.get("description", action.example if action else "母版使用上方形象描述"))
        self.seconds.setValue(raw.get("seconds", action.seconds if action else 1))
        self.loading = False
        self.refresh_prompt()

    def edit_changed(self, *_):
        if not self.loading:
            self.persist()
            self.refresh_prompt()

    def persist(self):
        if self.loading or self.project is None:
            return False
        # Worker updates attempts independently; always merge latest disk state.
        try:
            project = load_project(self.project_path)
            project.update(name=self.name.text(), appearance=self.appearance.toPlainText(),
                           phrases=self.phrases.text().split("|"),
                           personality=self.personality.toPlainText(),
                           communication_style=self.communication_style.toPlainText())
            if self.action_id != "portrait":
                project["actions"][self.action_id].update(
                    description=self.description.toPlainText(), seconds=self.seconds.value())
            self.project = save_project(self.project_path, project)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return False
        return True

    def refresh_prompt(self):
        try:
            self.prompt.setPlainText(build_prompt(
                self.appearance.toPlainText(), self.action_id,
                self.description.toPlainText(), self.seconds.value()))
        except ValueError as exc:
            self.prompt.clear()
            self.status.setText(str(exc))

    def copy_prompt(self):
        text = self.prompt.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status.setText("完整提示词已复制")

    def reset_action(self):
        action = action_by_id(self.action_id)
        if action:
            self.loading = True
            self.description.setPlainText(action.example)
            self.seconds.setValue(action.seconds)
            self.loading = False
            self.edit_changed()

    def refresh_assets(self):
        old = max(0, self.assets.currentRow())
        self.assets.blockSignals(True)
        self.assets.clear()
        project = load_project(self.project_path) if self.project_path else {}
        for cid, label in [("portrait", "角色母版")] + [(a.id, a.label) for a in ACTIONS]:
            attempt = project.get("attempts", {}).get(cid, {})
            state = {"done": "已就绪", "error": "失败"}.get(attempt.get("status"), "待导入")
            self.assets.addItem(f"{label} · {cid}    {state}")
        self.assets.setCurrentRow(old)
        self.assets.blockSignals(False)
        self.asset_selected(old)
        portrait = self.project_path / "package" / "portrait.png" if self.project_path else None
        if portrait and portrait.exists():
            self.preview.setPixmap(QPixmap(str(portrait)))
        else:
            self.preview.setText("尚无角色预览")
        selected = self.installed_select.currentData()
        self.installed_select.clear()
        if self.characters.exists():
            for manifest_path in sorted(self.characters.glob("*/manifest.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    self.installed_select.addItem(manifest.get("name", manifest_path.parent.name), manifest_path.parent.name)
                except (OSError, ValueError):
                    continue
        wanted = self.project["id"] if self.project else selected
        index = self.installed_select.findData(wanted)
        if index >= 0:
            self.installed_select.setCurrentIndex(index)
        ready = self.installed_select.count() > 0
        self.launch_button.setEnabled(ready and self.worker is None)
        self.export_button.setEnabled(ready and self.worker is None)

    def selected_asset(self):
        row = self.assets.currentRow()
        return "portrait" if row <= 0 else ACTIONS[row - 1].id

    def asset_selected(self, *_):
        cid = self.selected_asset()
        data = load_project(self.project_path) if self.project_path else {}
        raw = data.get("actions", {}).get(cid, {})
        self.loading = True
        self.trim_start.setValue(raw.get("start", 0))
        self.trim_end.setValue(raw.get("end", 0))
        self.facing.setCurrentIndex(self.facing.findData(raw.get("source_facing", "left")))
        self.trim_start.setEnabled(cid != "portrait")
        self.trim_end.setEnabled(cid != "portrait")
        self.facing.setEnabled(cid == "walk")
        self.loading = False
        error = data.get("attempts", {}).get(cid, {}).get("error")
        if error:
            self.status.setText(error)

    def asset_options_changed(self, *_):
        cid = self.selected_asset()
        if self.loading or not self.project_path or cid == "portrait":
            return
        data = load_project(self.project_path)
        data["actions"][cid].update(start=self.trim_start.value(), end=self.trim_end.value(),
                                    source_facing=self.facing.currentData())
        try:
            save_project(self.project_path, data)
            self.finished_signature = None
        except ValueError as exc:
            self.status.setText(str(exc))

    def open_inbox(self):
        if self.project_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_path / "inbox")))

    def pick_media(self):
        if not self.project_path or self.worker:
            return
        cid = self.selected_asset()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择角色母版" if cid == "portrait" else "选择动作视频", "",
            "图片 (*.png *.jpg *.jpeg *.webp)" if cid == "portrait" else "视频 (*.mp4 *.webm *.mov)")
        if not path:
            return
        source = Path(path)
        inbox = self.project_path / "inbox"
        existing = [p for p in inbox.glob(cid + ".*") if p.suffix.lower() in MEDIA]
        if existing and QMessageBox.question(self, "替换素材", "替换这个动作已有的输入素材？") != QMessageBox.StandardButton.Yes:
            return
        # Archive originals inside this project; never delete a supplied file.
        import uuid
        for old in existing:
            if old.resolve() == source.resolve():
                self.start_processing()
                return
            archive = self.project_path / "originals" / uuid.uuid4().hex
            archive.mkdir(parents=True)
            shutil.move(str(old), str(archive / old.name))
        shutil.copy2(source, inbox / (cid + source.suffix.lower()))
        self.start_processing()

    def watch_inbox(self):
        if self.worker and self.event_path and self.event_path.exists():
            try:
                event = json.loads(self.event_path.read_text(encoding="utf-8"))
                if event != self.last_event:
                    self.last_event = event
                    self.status.setText(event.get("message", "")[-240:])
            except (OSError, ValueError):
                pass
        if not self.auto.isChecked() or not self.project_path or self.worker:
            return
        files = list((self.project_path / "inbox").iterdir())
        try:
            signature = tuple(sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                                     for p in files if p.is_file() and p.suffix.lower() in MEDIA))
        except OSError:
            return
        if signature == self.finished_signature:
            return
        if signature != self.observed:
            self.observed = signature
            return
        try:
            if pending_inputs(self.project_path):
                self.start_processing()
            self.finished_signature = signature
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            self.finished_signature = signature

    def retry_failed(self):
        if not self.project_path or self.worker:
            return
        from .project import atomic_json
        project = load_project(self.project_path)
        project["attempts"] = {k: v for k, v in project["attempts"].items() if v.get("status") != "error"}
        atomic_json(self.project_path / "project.json", project)
        self.start_processing()

    def start_processing(self, *_):
        if not self.project_path or self.worker:
            return
        if not self.persist():
            return
        self.worker = QProcess(self)
        self.worker.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.worker.setProcessEnvironment(env)
        self.event_path = self.project_path / "worker-event.json"
        self.event_path.unlink(missing_ok=True)
        self.last_event = None
        program, args = command("--studio-worker", "--project", str(self.project_path),
                                "--characters", str(self.characters), "--events", str(self.event_path))
        self.buffer = ""
        self.worker.readyReadStandardOutput.connect(self.read_worker)
        self.worker.finished.connect(self.worker_finished)
        self.worker.errorOccurred.connect(self.worker_error)
        self.progress.setRange(0, 0)
        for widget in (self.project_select, self.process_button, self.retry_button, self.launch_button,
                       self.export_button, self.save_identity_button):
            widget.setEnabled(False)
        self.status.setText("正在处理素材")
        self.worker.start(program, args)

    def read_worker(self):
        if not self.worker:
            return
        self.buffer += bytes(self.worker.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            try:
                event = json.loads(line)
                text = event["message"]
            except (ValueError, KeyError):
                text = line
            self.log.appendPlainText(text)
            self.status.setText(text[-240:])

    def worker_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText("无法启动处理程序，请检查安装是否完整。")
            self.worker_finished(1)

    def worker_finished(self, code, *_):
        if not self.worker:
            return
        self.read_worker()
        self.worker.deleteLater()
        self.worker = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if code == 0 else 0)
        for widget in (self.project_select, self.process_button, self.retry_button, self.save_identity_button):
            widget.setEnabled(True)
        self.refresh_assets()
        self.status.setText("处理完成，可以使用此角色" if code == 0 else "部分素材处理失败，选择对应动作查看原因")

    def export_pack(self):
        cid = self.installed_select.currentData()
        if not cid:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出角色包", cid + ".zip", "角色包 (*.zip)")
        if path:
            try:
                if self.project and self.project["id"] == cid:
                    if not self.persist():
                        return
                    sync_identity(self.project_path, self.characters)
                export_package(self.characters / cid, Path(path), cid)
                self.status.setText("角色包已导出")
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))

    def import_pack(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入角色包", "", "角色包 (*.zip)")
        if path:
            try:
                installed = import_package(Path(path), self.characters)
                self.refresh_assets()
                self.installed_select.setCurrentIndex(self.installed_select.findData(installed.name))
                self.activate(installed.name)
            except (OSError, ValueError) as exc:
                self.status.setText(str(exc))

    def launch_pet(self):
        cid = self.installed_select.currentData()
        if cid:
            self.activate(cid)

    def activate(self, cid):
        from .app import select_character
        from pet.config import Config
        # Create global settings before the slot profile on a clean installation.
        config = Config()
        if not config.path.exists():
            config.set("feature_activation", {"version": 1, "enabled": []})
            config.save()
        try:
            if self.project and self.project["id"] == cid:
                if not self.persist():
                    return
                sync_identity(self.project_path, self.characters)
            select_character(self.data_dir, cid)
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
            return
        if self.pet_process and self.pet_process.poll() is None:
            self.pet_process.terminate()
            try:
                self.pet_process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.pet_process.kill()
                self.pet_process.wait(timeout=2)
        program, args = command("--pet")
        with (self.data_dir / "studio-pet.log").open("ab") as log:
            self.pet_process = subprocess.Popen(
                [program, *args], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
        QTimer.singleShot(2500, self.check_pet_started)
        self.status.setText("已选择角色，正在启动桌宠")

    def check_pet_started(self):
        if self.pet_process and self.pet_process.poll() is not None:
            code = self.pet_process.returncode
            self.status.setText("桌宠已在运行；新素材需重启桌宠生效" if code == 0 else
                               f"桌宠启动失败（{code}），详情见 {self.data_dir / 'studio-pet.log'}")
        else:
            self.status.setText("桌宠进程已启动")

    def closeEvent(self, event):
        if self.worker:
            self.status.setText("素材正在处理，请等待完成后关闭")
            event.ignore()
            return
        super().closeEvent(event)


def open_studio(parent=None, data_dir=None):
    dialog = StudioDialog(parent, data_dir=data_dir)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
    return dialog
