"""Local Qt layout evidence and an optional real-media processing smoke test."""
import argparse
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wave", type=Path)
    parser.add_argument("--walk", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    from pet.character_studio.project import create_project, load_project, save_project
    from pet.character_studio.dialog import StudioDialog
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    data = args.output / "data"
    projects = data / "studio" / "projects"
    path = create_project(projects, "咕咕嘎嘎", "两头身少女，企鹅连体服，深灰帽兜、浅色肚皮、黄色脚掌。")
    project = load_project(path)
    project["phrases"] = ["咕咕嘎嘎~", "咕咕~"]
    project["actions"]["walk"]["source_facing"] = "right"
    save_project(path, project)
    for source, name in [(args.wave, "wave.mp4"), (args.walk, "walk.mp4")]:
        if source:
            shutil.copy2(source, path / "inbox" / name)
    dialog = StudioDialog(data_dir=data)
    for theme in ["light", "dark"]:
        dialog.apply_theme(theme)
        for width in [720, 1100]:
            dialog.resize(width, 760)
            for tab in range(dialog.tabs.count()):
                dialog.tabs.setCurrentIndex(tab)
                dialog.show()
                app.processEvents()
                dialog.grab().save(str(args.output / f"studio-{theme}-{width}-{tab}.png"))
    dialog.close()
    if args.wave or args.walk:
        from pet.character_studio.processing import process_pending
        process_pending(path, data / "characters")
    print(path)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    main()
