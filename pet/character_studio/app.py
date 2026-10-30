"""Dahlia Pet product entry and process commands."""
import os
import json
from pathlib import Path
import sys


def command(*args):
    if not args:
        args = ("--character-studio",)
    if getattr(sys, "frozen", False):
        return sys.executable, list(args)
    return sys.executable, ["-m", "pet.character_studio", *args]


def configure_product():
    os.environ["DAHLIA_PET"] = "1"
    os.environ.setdefault("PYTHONUTF8", "1")
    # Bundles can carry the model for fully offline creation; otherwise rembg
    # downloads its checksum-verified model on first use into its user cache.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    if (base / "studio_models").is_dir():
        os.environ.setdefault("U2NET_HOME", str(base / "studio_models"))


def select_character(data_dir, cid):
    from pet import pet_profiles
    from .project import valid_id
    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "characters" / valid_id(cid) / "manifest.json").read_text(encoding="utf-8"))
    result = pet_profiles.write_profile_settings(data_dir, 0, {
        "character": cid, "self_talk_texts": manifest.get("studio", {}).get("phrases", ["你好呀~"]),
        "self_talk_image_dir": "", "self_talk_image_chance": 0, "self_talk_enabled": True,
    }, user_customized=True)
    if not result.ok:
        raise ValueError("角色选择失败：" + str(result))


def main():
    configure_product()
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    args = sys.argv[1:]
    if "--studio-worker" in args:
        from .processing import main as worker_main
        return worker_main(args[args.index("--studio-worker") + 1:])
    if "--ocr-worker" in args or "--settings" in args or "--uninstall-cleanup" in args:
        from pet.__main__ import _main
        return _main()
    if "--pet" in args:
        from pet.app import main as pet_main
        return pet_main()
    from PySide6.QtWidgets import QApplication
    from pet.config import Config
    from .dialog import StudioDialog
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Dahlia Pet")
    config = Config()
    config.dir.mkdir(parents=True, exist_ok=True)
    if not config.path.exists():
        config.set("feature_activation", {"version": 1, "enabled": []})
        config.save()
    dialog = StudioDialog(data_dir=config.dir)
    dialog.show()
    return app.exec()
