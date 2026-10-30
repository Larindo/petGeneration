"""Launch a real desktop pet against isolated test data and verify startup."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    os.environ["DAHLIA_PET"] = "1"
    os.environ["APPDATA"] = str(args.data)
    from pet.config import Config
    from pet.character_studio.app import select_character
    from pet.character_studio.project import install_package
    config = Config()
    config.set("feature_activation", {"version": 1, "enabled": []})
    config.save()
    cid = json.loads((args.package / "manifest.json").read_text(encoding="utf-8"))["studio"]["project_id"]
    install_package(args.package, config.dir / "characters", cid)
    select_character(config.dir, cid)
    command = [str(args.exe), "--pet"] if args.exe else [sys.executable, "-m", "pet.character_studio", "--pet"]
    env = dict(os.environ, PYTHONUTF8="1")
    env.pop("QT_QPA_PLATFORM", None)
    with (config.dir / "smoke-stdout.log").open("wb") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log,
                                   creationflags=0x08000000 if os.name == "nt" else 0)
        deadline = time.monotonic() + 40
        text = ""
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError((config.dir / "smoke-stdout.log").read_text(encoding="utf-8", errors="replace"))
                logs = list(config.dir.glob("pet-*.log"))
                text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in logs)
                if "进入事件循环" in text and "motion" in text:
                    break
                time.sleep(.25)
            if "进入事件循环" not in text:
                raise RuntimeError("Runtime did not reach its event loop: " + text[-1500:])
            print(json.dumps({"pid": process.pid, "startup": True, "motion_logged": "motion" in text,
                              "log_dir": str(config.dir)}), flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
