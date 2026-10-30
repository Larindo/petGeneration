"""Exercise the frozen worker, including neural matting, using a local frame."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import cv2
    from pet.character_studio.project import create_project, load_project
    path = create_project(args.output / "projects", "Frozen smoke", "A chibi character")
    cap = cv2.VideoCapture(str(args.video))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError("Cannot read source")
    cv2.imwrite(str(path / "inbox" / "portrait.png"), frame)
    events = path / "events.json"
    result = subprocess.run([
        str(args.exe), "--studio-worker", "--project", str(path),
        "--characters", str(args.output / "characters"), "--events", str(events),
    ], timeout=120)
    if result.returncode:
        raise RuntimeError(events.read_text(encoding="utf-8") if events.exists() else f"Worker exit {result.returncode}")
    state = load_project(path)
    assert state["attempts"]["portrait"]["status"] == "done", state["attempts"]
    print(json.dumps(state["attempts"]["portrait"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
