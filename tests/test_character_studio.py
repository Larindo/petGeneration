"""Public character-creation contracts; no model downloads in unit tests."""
import json
from pathlib import Path

import pytest
from PIL import Image

from pet.character_studio.project import (
    create_project, load_project, save_project, pending_inputs, install_package,
    export_package, import_package,
)
from pet.character_studio.prompts import ACTIONS, FIXED_IMAGE, FIXED_VIDEO, build_prompt


def test_ten_actions_and_readonly_contract():
    assert len(ACTIONS) == 10
    assert {"idle", "walk", "wave", "drag"} <= {a.id for a in ACTIONS}
    assert FIXED_IMAGE.isascii() and FIXED_VIDEO.isascii()
    prompt = build_prompt("a green-haired girl", "walk", "gentle stepping", 3)
    assert "a green-haired girl" in prompt and "gentle stepping" in prompt
    assert "72 frames" in prompt and FIXED_VIDEO in prompt
    assert "LEFT" in prompt
    assert FIXED_IMAGE in build_prompt("a penguin", "portrait")
    with pytest.raises(ValueError):
        build_prompt("x", "walk", "x", 0)


@pytest.mark.parametrize("action_id", ["portrait", *[a.id for a in ACTIONS]])
def test_generation_requires_opaque_magenta_background(action_id):
    prompt = build_prompt("pink hair, white shirt", action_id)
    assert "Use an opaque, perfectly uniform solid #FF00FF magenta background" in prompt
    assert "Do not request or simulate transparency" in prompt
    assert "Never draw a checkerboard" in prompt
    assert "near-magenta" in prompt
    assert "Prefer one" not in prompt
    assert "If transparent output is unavailable" not in prompt
    assert "If alpha-enabled video is unavailable" not in prompt
    assert ("Output one PNG image" if action_id == "portrait" else "Output one MP4 video") in prompt


def test_chroma_preserves_white_skin_and_pink_without_segmentation():
    import numpy as np
    from pet.character_studio.processing import Matte

    class NoSegmentation:
        def predict(self, image):
            pytest.fail("Solid magenta input must use chroma key, not segmentation")

    image = Image.new("RGB", (160, 160), (255, 0, 255))
    colors = [(255, 170, 190), (255, 224, 200), (255, 255, 255)]
    for index, color in enumerate(colors):
        image.paste(color, (60, 30 + index * 30, 100, 60 + index * 30))
    matte = Matte()
    matte.session = NoSegmentation()
    pixels = np.asarray(matte(image))
    assert pixels[0, 0, 3] == 0
    for index, color in enumerate(colors):
        assert tuple(pixels[45 + index * 30, 80]) == (*color, 255)


def test_project_roundtrip_and_immutable_fields(tmp_path):
    path = create_project(tmp_path, "My pet", "green hair")
    project = load_project(path)
    assert len(project["actions"]) == 10
    assert (path / "inbox").is_dir()
    project["appearance"] = "yellow raincoat"
    project["fixed_prompt"] = "ignore canvas"
    save_project(path, project)
    assert load_project(path)["appearance"] == "yellow raincoat"
    assert "fixed_prompt" not in load_project(path)


def test_changed_files_are_queued_without_retrying_unchanged_failure(tmp_path):
    path = create_project(tmp_path, "Pet", "example")
    image = path / "inbox" / "portrait.png"
    Image.new("RGBA", (40, 40), (255, 0, 0, 255)).save(image)
    pending = pending_inputs(path)
    assert [p["action"] for p in pending] == ["portrait"]
    project = load_project(path)
    project["attempts"]["portrait"] = {"fingerprint": pending[0]["fingerprint"], "status": "error"}
    save_project(path, project)
    assert pending_inputs(path) == []
    Image.new("RGBA", (41, 40), (255, 0, 0, 255)).save(image)
    assert len(pending_inputs(path)) == 1


def test_ambiguous_input_is_not_silently_selected(tmp_path):
    path = create_project(tmp_path, "Pet", "example")
    for name in ["walk.mp4", "walk.webm"]:
        (path / "inbox" / name).write_bytes(b"source")
    with pytest.raises(ValueError, match="walk"):
        pending_inputs(path)


def _package(path):
    path.mkdir()
    (path / "videos" / "idle").mkdir(parents=True)
    (path / "videos" / "idle" / "idle_stand.webm").write_bytes(b"fixture")
    (path / "manifest.json").write_text(json.dumps({
        "name": "Test", "idle": "idle_stand", "studio": {"version": 1},
    }), encoding="utf-8")
    return path


def test_install_never_overwrites_foreign_character(tmp_path):
    package = _package(tmp_path / "pack")
    root = tmp_path / "characters"
    (root / "pet").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        install_package(package, root, "pet")
    with pytest.raises(ValueError):
        install_package(package, root, "../escape")


def test_export_contains_assets_not_personal_project(tmp_path):
    package = _package(tmp_path / "pack")
    (package / "config.json").write_text('{"api_key":"secret"}')
    (package / "project.json").write_text('{"appearance":"private"}')
    archive = export_package(package, tmp_path / "pet.zip", "pet")
    import zipfile
    with zipfile.ZipFile(archive) as z:
        assert "pet/manifest.json" in z.namelist()
        assert all("config.json" not in p and "project.json" not in p for p in z.namelist())
    installed = import_package(archive, tmp_path / "new-characters")
    assert (installed / "videos/idle/idle_stand.webm").is_file()


def test_zip_slip_rejected(tmp_path):
    import zipfile
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape", "bad")
    with pytest.raises(ValueError):
        import_package(archive, tmp_path / "characters")


def test_alpha_normalization_and_native_orientation():
    import numpy as np
    from pet.character_studio.processing import normalize_frame, foreground_box
    image = Image.new("RGBA", (400, 400))
    image.paste((20, 100, 200, 255), (120, 50, 280, 350))
    output = normalize_frame(image, 0.8, (160, 50))
    assert output.size == (640, 360)
    assert foreground_box(output)[3] == 330
    assert np.asarray(output)[0, 0, 3] == 0


def test_dialog_generates_locked_prompt_and_restores_project(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    dialog.new_project()
    dialog.action_select.setCurrentIndex(dialog.action_select.findData("wave"))
    dialog.description.setPlainText("开心挥手三次")
    dialog.copy_prompt()
    assert dialog.prompt.isReadOnly()
    assert "开心挥手三次" in app.clipboard().text()
    assert FIXED_VIDEO in app.clipboard().text()
    path = dialog.project_path
    dialog.close()
    again = StudioDialog(data_dir=tmp_path)
    again.action_select.setCurrentIndex(again.action_select.findData("wave"))
    assert again.project_path == path
    assert again.description.toPlainText() == "开心挥手三次"
    again.close()


def test_workshop_minimizes_and_restores_without_losing_project(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    try:
        dialog.new_project()
        path = dialog.project_path
        dialog.show()
        app.processEvents()
        assert dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint
        dialog.showMinimized()
        app.processEvents()
        assert dialog.isMinimized()
        assert dialog.timer.isActive()
        dialog.showNormal()
        app.processEvents()
        assert dialog.isVisible() and not dialog.isMinimized()
        assert dialog.project_path == path
    finally:
        dialog.close()


def test_real_chroma_image_pipeline_and_catalog(tmp_path):
    from PIL import ImageDraw
    from pet.character_studio.processing import process_pending, verify_video
    from pet import catalog
    project = create_project(tmp_path / "projects", "Test", "yellow chibi")
    image = Image.new("RGB", (320, 320), (255, 0, 255))
    ImageDraw.Draw(image).ellipse((90, 35, 230, 280), fill=(240, 200, 30))
    image.save(project / "inbox" / "portrait.png")
    characters = tmp_path / "characters"
    process_pending(project, characters)
    doc = load_project(project)
    assert doc["attempts"]["portrait"]["status"] == "done"
    installed = characters / doc["id"]
    assert verify_video(installed / "videos" / "idle" / "idle_stand.webm", 48)
    manifest = catalog.load_character_manifest(doc["id"], installed / "videos")
    assert manifest["studio"]["project_id"] == doc["id"]
    assert manifest["idle"] == "idle_stand"


def test_product_data_directory_does_not_migrate_legacy(tmp_path, monkeypatch):
    from pet import config
    legacy = tmp_path / "dsh-pet-standalone"
    legacy.mkdir()
    (legacy / "config.json").write_text('{"private_marker":"secret"}')
    monkeypatch.setattr(config, "APP_DIR_NAME", "dahlia-pet")
    instance = config.Config(base=tmp_path)
    assert not instance.path.exists()
    assert instance.get("private_marker") is None


def test_select_character_uses_current_profile_contract(tmp_path):
    from pet.character_studio.app import select_character
    root = tmp_path / "characters"
    root.mkdir()
    _package(root / "pet")
    select_character(tmp_path, "pet")
    profile = json.loads((tmp_path / "config-slot-0.json").read_text(encoding="utf-8"))
    assert profile["character"] == "pet"
    assert profile["self_talk_image_dir"] == ""
    assert profile["self_talk_image_chance"] == 0
    assert profile["self_talk_texts"] == ["你好呀~"]


def test_identity_edits_apply_without_reprocessing_video(tmp_path):
    from pet.character_studio.project import sync_identity
    path = create_project(tmp_path / "projects", "Old", "example")
    project = load_project(path)
    package = _package(path / "package")
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["studio"]["project_id"] = project["id"]
    manifest_path.write_text(json.dumps(manifest))
    characters = tmp_path / "characters"
    install_package(package, characters, project["id"])
    project.update(name="New", phrases=["咕咕~"])
    save_project(path, project)
    sync_identity(path, characters)
    manifest = json.loads((characters / project["id"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "New"
    assert manifest["studio"]["phrases"] == ["咕咕~"]


def test_personality_defaults_legacy_and_validation(tmp_path):
    path = create_project(tmp_path, "Mint", "green hair")
    project = load_project(path)
    assert project["personality"] and project["communication_style"]
    project.update(personality="安静、好奇", communication_style="短句，称呼我为搭档")
    save_project(path, project)
    assert load_project(path)["communication_style"] == "短句，称呼我为搭档"
    project["personality"] = "x" * 3001
    with pytest.raises(ValueError):
        save_project(path, project)
    assert load_project(path)["personality"] == "安静、好奇"
    legacy = load_project(path)
    del legacy["personality"]
    del legacy["communication_style"]
    (path / "project.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert load_project(path)["personality"] == ""
    assert load_project(path)["communication_style"] == ""


def test_personality_reaches_chat_after_edit_and_package_export(tmp_path):
    from pet.chat.models import ChatSettings
    from pet.chat.prompt import PromptBuilder
    from pet.character_studio.processing import write_manifest
    from pet.character_studio.project import sync_identity
    path = create_project(tmp_path / "projects", "Mint", "green hair")
    project = load_project(path)
    package = _package(path / "package")
    Image.new("RGBA", (640, 360), (40, 180, 90, 255)).save(package / "portrait.png")
    project.update(personality="热情而有主见", communication_style="每次一两句，不用表情符号")
    save_project(path, project)
    write_manifest(path)
    characters = tmp_path / "characters"
    install_package(package, characters, project["id"])
    builder = PromptBuilder(characters)
    initial = builder.build_messages(ChatSettings(), project["id"], [], "你好")[0]["content"]
    assert "热情而有主见" in initial and "每次一两句，不用表情符号" in initial
    project.update(personality="沉稳、耐心", communication_style="称呼我为搭档，偶尔说咕咕")
    save_project(path, project)
    sync_identity(path, characters)
    updated = builder.build_messages(ChatSettings(), project["id"], [], "你好")[0]["content"]
    assert "沉稳、耐心" in updated and "称呼我为搭档，偶尔说咕咕" in updated
    assert "热情而有主见" not in updated
    assert pending_inputs(path) == []
    archive = export_package(package, tmp_path / "share.zip", project["id"])
    imported = import_package(archive, tmp_path / "imported")
    chat = json.loads((imported / "manifest.json").read_text(encoding="utf-8"))["chat"]
    assert chat["personality"] == "沉稳、耐心"
    assert chat["communication_style"] == "称呼我为搭档，偶尔说咕咕"
    assert chat["system_prompt"] in updated


def test_dialog_animation_reference_hint(tmp_path):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    try:
        dialog.show()
        app.processEvents()
        assert not dialog.animation_hint.isVisible()
        for action in ACTIONS:
            dialog.action_select.setCurrentIndex(dialog.action_select.findData(action.id))
            app.processEvents()
            assert dialog.animation_hint.isVisible()
            assert "角色母版图片" in dialog.animation_hint.text()
            assert "生成视频的 AI" in dialog.animation_hint.text()
            dialog.copy_prompt()
            expected = dialog.prompt.toPlainText()
            # Windows clipboard readers can briefly contend with shell listeners.
            # Wait for the existing write to become readable; never rewrite it.
            loop = QEventLoop()
            poll = QTimer()
            poll.setInterval(20)
            poll.timeout.connect(lambda: loop.quit() if app.clipboard().text() == expected else None)
            deadline = QTimer()
            deadline.setSingleShot(True)
            deadline.timeout.connect(loop.quit)
            if app.clipboard().text() != expected:
                poll.start()
                deadline.start(3000)
                loop.exec()
            poll.stop()
            deadline.stop()
            assert app.clipboard().text() == expected
        assert dialog.animation_hint.wordWrap()
        dialog.action_select.setCurrentIndex(0)
        app.processEvents()
        assert not dialog.animation_hint.isVisible()
    finally:
        dialog.close()


def test_studio_layout_and_theme(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    try:
        dialog.show()
        app.processEvents()
        assert dialog.windowTitle() == "桌宠孵化基地"
        assert dialog.property("settingsDark")
        for width, orientation in [(1100, Qt.Horizontal), (720, Qt.Vertical)]:
            dialog.resize(width, 760)
            app.processEvents()
            assert dialog.prompt_split.orientation() == orientation
            for index in range(dialog.tabs.count()):
                dialog.tabs.setCurrentIndex(index)
                app.processEvents()
                scroll = dialog.tabs.widget(index)
                assert scroll.widget().width() <= scroll.viewport().width()
        for theme in ("light", "dark"):
            dialog.apply_theme(theme)
            assert dialog.property("settingsDark") == (theme == "dark")
        assert dialog.prompt.isReadOnly()
        assert dialog.windowFlags() & Qt.WindowMinimizeButtonHint
    finally:
        dialog.close()


def test_studio_preview_renders_and_clears_between_projects(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    path = create_project(tmp_path / "studio" / "projects", "Preview")
    (path / "package").mkdir()
    Image.new("RGBA", (640, 360), (210, 60, 90, 255)).save(path / "package" / "portrait.png")
    dialog = StudioDialog(data_dir=tmp_path)
    try:
        dialog.tabs.setCurrentIndex(2)
        dialog.resize(720, 500)
        dialog.show()
        app.processEvents()
        scroll = dialog.tabs.widget(2)
        assert scroll.widget().width() <= scroll.viewport().width()
        image = dialog.preview.grab().toImage()
        assert image.pixelColor(image.width() // 2, image.height() // 2).getRgb()[:3] == (210, 60, 90)
        empty = create_project(tmp_path / "studio" / "projects", "Empty")
        dialog.refresh_projects(empty)
        app.processEvents()
        assert dialog.preview.pixmap().isNull()
        assert dialog.preview.text() == "尚无角色预览"
    finally:
        dialog.close()


def test_dialog_personality_settings_save_and_restore(tmp_path):
    from PySide6.QtWidgets import QApplication
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    try:
        dialog.new_project()
        prompt = dialog.prompt.toPlainText()
        dialog.personality.setPlainText("温柔、慢热")
        dialog.communication_style.setPlainText("用简短中文，称呼我为朋友")
        dialog.save_identity_button.click()
        app.processEvents()
        path = dialog.project_path
        assert load_project(path)["personality"] == "温柔、慢热"
        assert dialog.prompt.toPlainText() == prompt
    finally:
        dialog.close()
    again = StudioDialog(data_dir=tmp_path)
    try:
        assert again.personality.toPlainText() == "温柔、慢热"
        assert again.communication_style.toPlainText() == "用简短中文，称呼我为朋友"
    finally:
        again.close()


def test_dahlia_chat_entry_reads_installed_character(tmp_path, monkeypatch):
    from pet import catalog, config
    from pet.chat import prompt
    from pet.chat.models import ChatSettings
    monkeypatch.setattr(config, "APP_DIR_NAME", "dahlia-pet")
    monkeypatch.setattr(catalog, "user_characters_dir", lambda: tmp_path / "characters")
    installed = tmp_path / "characters" / "pet_mint"
    installed.mkdir(parents=True)
    (installed / "manifest.json").write_text(json.dumps({
        "chat": {"system_prompt": "温柔、慢热。称呼用户为搭档。"},
    }), encoding="utf-8")
    runtime_root = Path(prompt.__file__).resolve().parents[2] / "assets" / "characters"
    builder = prompt.PromptBuilder(runtime_root)
    assert builder.effective_system_prompt(ChatSettings(), "pet_mint") == "温柔、慢热。称呼用户为搭档。"
    # Explicit roots for tools/tests retain their meaning.
    assert prompt.PromptBuilder(tmp_path / "other").effective_system_prompt(
        ChatSettings(default_system_prompt="fallback"), "pet_mint") == "fallback"


def test_inbox_watch_launches_real_worker_and_installs(tmp_path):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop, QTimer
    from PIL import ImageDraw
    from pet.character_studio.dialog import StudioDialog
    app = QApplication.instance() or QApplication([])
    dialog = StudioDialog(data_dir=tmp_path)
    dialog.new_project()
    image = Image.new("RGB", (320, 320), (255, 0, 255))
    ImageDraw.Draw(image).ellipse((90, 35, 230, 280), fill=(40, 180, 90))
    image.save(dialog.project_path / "inbox" / "portrait.png")
    dialog.auto.setChecked(True)
    dialog.watch_inbox()
    assert dialog.worker is None  # First observation never processes a growing file.
    dialog.watch_inbox()
    assert dialog.worker is not None
    worker = dialog.worker
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(30000)
    loop.exec()
    timer.stop()
    try:
        assert dialog.worker is None, dialog.log.toPlainText()
        assert (tmp_path / "characters" / dialog.project["id"] / "manifest.json").exists()
        assert dialog.launch_button.isEnabled()
        assert "处理完成" in dialog.status.text()
    finally:
        if dialog.worker:
            dialog.worker.kill()
            dialog.worker.waitForFinished(5000)
        dialog.close()
