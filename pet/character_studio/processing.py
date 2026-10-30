"""Fixed local image/video pipeline. Invoked by CLI or isolated GUI worker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("OMP_NUM_THREADS", "4")

import numpy as np
from PIL import Image, ImageOps

from .project import atomic_json, load_project, pending_inputs, install_package, character_chat
from .prompts import action_by_id

CANVAS = (640, 360)
FPS = 24
EVENT_PATH = None


def emit(message, **extra):
    event = {"message": message, **extra}
    if EVENT_PATH:
        atomic_json(EVENT_PATH, event)
    if sys.stdout is not None:
        print(json.dumps(event, ensure_ascii=False), flush=True)


def foreground_box(image):
    ys, xs = np.where(np.asarray(image)[:, :, 3] >= 128)
    if len(xs) < 100:
        raise ValueError("没有检测到完整角色，请检查输入素材。")
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def normalize_frame(image, scale, offset, mirror=False):
    from scipy.ndimage import distance_transform_edt
    canvas = Image.new("RGBA", CANVAS)
    size = tuple(max(1, round(v * scale)) for v in image.size)
    canvas.alpha_composite(image.resize(size, Image.Resampling.LANCZOS), offset)
    if mirror:
        canvas = ImageOps.mirror(canvas)
    pixels = np.array(canvas)
    solid = pixels[:, :, 3] >= 250
    if not solid.any():
        raise ValueError("抠图后角色没有实心区域，请换一份清晰素材。")
    indices = distance_transform_edt(~solid, return_distances=False, return_indices=True)
    pixels[~solid, :3] = pixels[indices[0], indices[1], :3][~solid]
    box = foreground_box(Image.fromarray(pixels))
    if box[0] <= 3 or box[1] <= 3 or box[2] >= 637 or box[3] >= 357:
        raise ValueError("动作超出安全画布，请缩小动作幅度后重新生成。")
    return Image.fromarray(pixels)


class Matte:
    def __init__(self):
        self.session = None

    def __call__(self, image):
        import cv2
        pixels = np.asarray(image.convert("RGBA"))
        if pixels[:, :, 3].min() < 250:
            return image.convert("RGBA")
        rgb = pixels[:, :, :3]
        # Use chroma-key only when all four corners are close to pure magenta.
        corners = rgb[[0, 0, -1, -1], [0, -1, 0, -1]].astype(float)
        if np.max(np.linalg.norm(corners - [255, 0, 255], axis=1)) < 65:
            distance = np.linalg.norm(rgb.astype(float) - [255, 0, 255], axis=2)
            alpha = np.clip((distance - 28) / 52, 0, 1) * 255
        else:
            if self.session is None:
                emit("正在加载本地抠图模型；首次使用可能需要下载模型")
                from rembg import new_session
                self.session = new_session("u2net", providers=["CPUExecutionProvider"])
            alpha = np.asarray(self.session.predict(Image.fromarray(rgb))[0]).astype(float)
            alpha = np.clip((alpha - 12) / 231, 0, 1) * 255
        count, labels, stats, _ = cv2.connectedComponentsWithStats((alpha >= 110).astype("uint8"), 8)
        if count < 2:
            raise ValueError("未识别到角色。")
        main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        support = cv2.dilate((labels == main).astype("uint8"), np.ones((7, 7), "uint8"))
        return Image.fromarray(np.dstack([rgb, (alpha * support).astype("uint8")]))


def video_frames(path, start=0, end=0):
    import imageio_ffmpeg
    params = ["-ss", str(start)] if start else []
    if Path(path).suffix.lower() == ".webm":
        params = ["-c:v", "libvpx-vp9"] + params
    output = ["-vf", "fps=24", "-t", str(end - start if end else 12.1)]
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgba", bpp=4,
                                       input_params=params, output_params=output)
    try:
        meta = next(reader)
        width, height = meta["size"]
        if width * height > 4096 * 2160:
            raise ValueError("输入视频过大，请导出为1080p或更小。")
        if not end and meta.get("duration", 0) - start > 12.1:
            raise ValueError("视频超过12秒，请填写片段起止时间。")
        for i, raw in enumerate(reader):
            if i >= 288:
                break
            yield Image.frombytes("RGBA", (width, height), raw)
    finally:
        reader.close()


def encode(frames, target):
    import imageio_ffmpeg
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "640x360", "-r", "24", "-i", "pipe:0",
        "-an", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-lossless", "1",
        "-auto-alt-ref", "0", "-threads", "4", str(target),
    ]
    with tempfile.TemporaryFile() as error:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=error,
                                creationflags=0x08000000 if os.name == "nt" else 0)
        try:
            for frame in frames:
                proc.stdin.write(frame.tobytes())
            proc.stdin.close()
            if proc.wait(timeout=180):
                error.seek(0)
                raise RuntimeError(error.read().decode(errors="replace")[-1000:])
        except BaseException:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            raise


def verify_video(path, expected):
    boxes = []
    for frame in video_frames(path):
        alpha = np.asarray(frame)[:, :, 3]
        if alpha.min() != 0 or alpha.max() < 250 or np.any(alpha[:3]) or np.any(alpha[-3:]):
            raise ValueError("透明通道校验失败。")
        boxes.append(foreground_box(frame))
    if len(boxes) != expected:
        raise ValueError(f"帧数不一致：预期{expected}，实际{len(boxes)}。")
    return boxes


def _walk_loop(paths):
    if len(paths) < 20:
        return 0, len(paths), None
    # Search repeated gait phases in the latter portion, avoiding generated turn-ins.
    features = []
    for path in paths:
        p = np.asarray(Image.open(path).resize((128, 72))).astype(float) / 255
        features.append(np.dstack([p[:, :, :3] * p[:, :, 3:], p[:, :, 3:]]))
    best = None
    lower = max(0, len(paths) // 4)
    for start in range(lower, len(paths) - 16):
        for end in range(start + 16, min(start + 73, len(paths) - 1)):
            score = float(np.mean((features[start] - features[end]) ** 2))
            motion = float(np.mean((features[start + 1] - features[start] -
                                    features[end + 1] + features[end]) ** 2))
            candidate = (score + motion * .5, start, end)
            if best is None or candidate < best:
                best = candidate
    return (best[1], best[2], best[0]) if best else (0, len(paths), None)


def process_one(project_path, item):
    project_path = Path(project_path)
    project = load_project(project_path)
    action_id = item["action"]
    settings = project["actions"].get(action_id, {})
    source = Path(item["path"])
    output = project_path / "package"
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=".processing-", dir=project_path) as temporary:
        scratch = Path(temporary)
        matte = Matte()
        images = ([Image.open(source).convert("RGBA")] if action_id == "portrait" else
                  video_frames(source, settings.get("start", 0), settings.get("end", 0)))
        paths, boxes = [], []
        for index, frame in enumerate(images):
            result = matte(frame)
            box = foreground_box(result)
            if box[0] < 2 or box[1] < 2 or box[2] >= result.width - 1 or box[3] >= result.height - 1:
                raise ValueError("输入角色贴边或背景未去除，请使用完整全身素材。")
            path = scratch / f"raw-{index:04}.png"
            result.save(path)
            paths.append(path)
            boxes.append(box)
            if index % 12 == 0:
                emit(f"{action_id}：已抠图 {index + 1} 帧", action=action_id, frames=index + 1)
        if not paths:
            raise ValueError("没有可用帧，请检查片段时间。")
        first, last, score = _walk_loop(paths) if action_id == "walk" else (0, len(paths), None)
        selected = np.asarray(boxes[first:last])
        reference_height = (float(np.median(selected[:, 3] - selected[:, 1]))
                            if action_id in ("walk", "drag") else boxes[0][3] - boxes[0][1])
        scale = 238 / reference_height
        # Scale is constant over the action, not per frame (prevents size jitter).
        scale = min(scale, 420 / float(max(selected[:, 2]) - min(selected[:, 0])),
                    312 / float(max(selected[:, 3]) - min(selected[:, 1])))
        center = float(np.median((selected[:, 0] + selected[:, 2]) / 2))
        ground = float(max(selected[:, 3]))
        offset = (round(320 - center * scale), round(330 - ground * scale))
        normalized = []
        for index, path in enumerate(paths[first:last]):
            image = normalize_frame(Image.open(path).convert("RGBA"), scale, offset,
                                    action_id == "walk" and settings.get("source_facing") == "right")
            p = scratch / f"frame-{index:04}.png"
            image.save(p)
            normalized.append(p)
        # New outputs are completely validated before replacing playable files.
        name = "idle_stand" if action_id == "portrait" else f"{action_by_id(action_id).category}_{action_id}"
        category = "idle" if action_id == "portrait" else action_by_id(action_id).category
        count = 48 if action_id == "portrait" else len(normalized)
        encoded = scratch / f"{name}.webm"
        sequence = ([Image.open(normalized[0]).convert("RGBA")] * 48 if action_id == "portrait" else
                    (Image.open(p).convert("RGBA") for p in normalized))
        encode(sequence, encoded)
        checked = verify_video(encoded, count)
        destination = output / "videos" / category / encoded.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(encoded, destination)
        portrait = Image.open(normalized[0]).convert("RGBA")
        if action_id == "portrait" or not (output / "portrait.png").exists():
            portrait.save(output / "portrait.png")
        if not list((output / "videos" / "idle").glob("*.webm")):
            encode([portrait] * 48, output / "videos" / "idle" / "idle_stand.webm")
        if action_id == "walk":
            # Conservative estimate from foot travel relative to body.
            stride = max(30, min(120, round((count / 24) * 65)))
            atomic_json(output / "videos" / "move_strides.json", {name: {"stride": stride}})
        report = {"source_name": source.name, "frames": count, "size": [640, 360],
                  "fps": 24, "loop_source_range": [first, last], "loop_score": score,
                  "elapsed_seconds": round(time.monotonic() - started, 3), "alpha_checked": True,
                  "bounds": [min(b[0] for b in checked), min(b[1] for b in checked),
                             max(b[2] for b in checked), max(b[3] for b in checked)]}
        atomic_json(project_path / "reports" / f"{action_id}.json", report)
        write_manifest(project_path)
        emit("素材处理完成", action=action_id, report=report)
        return report


def write_manifest(path):
    path = Path(path)
    project = load_project(path)
    output = path / "package"
    videos = output / "videos"
    idle = "idle_idle" if (videos / "idle" / "idle_idle.webm").exists() else "idle_stand"
    portrait = Image.open(output / "portrait.png").convert("RGBA")
    box = foreground_box(portrait)
    half = max(320 - box[0], box[2] - 320)
    manifest = {
        "name": project["name"], "body_box": [320 - half, box[1], 320 + half, box[3]],
        "idle": idle, "idles": [idle],
        "moves": [p.stem for p in (videos / "move").glob("*.webm")],
        "clicks": [p.stem for p in (videos / "click").glob("*.webm")],
        "acts": [p.stem for p in (videos / "random").glob("*.webm")],
        "studio": {"version": 1, "project_id": project["id"], "phrases": project["phrases"]},
        "chat": character_chat(project),
    }
    if (videos / "drag" / "drag_drag.webm").exists():
        manifest["drag"] = "drag_drag"
    atomic_json(output / "manifest.json", manifest)
    (output / "SOURCE.txt").write_text(
        "User-supplied character artwork. Processed locally with Dahlia Pet Studio.\n"
        "640x360, 24fps, VP9 alpha. Original media remains in the private project inbox.\n",
        encoding="utf-8",
    )


def process_pending(path, characters_root, retry=False):
    path = Path(path)
    # A crashed process cannot leave a permanent lock: QLockFile records PID.
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(path / ".processing.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise RuntimeError("这个角色正在另一个窗口中处理。")
    errors = []
    try:
        for item in pending_inputs(path, retry=retry):
            try:
                report = process_one(path, item)
                status = {"fingerprint": item["fingerprint"], "status": "done", "report": report}
            except Exception as exc:
                status = {"fingerprint": item["fingerprint"], "status": "error", "error": str(exc)}
                errors.append(f"{item['action']}: {exc}")
                emit(str(exc), action=item["action"], error=True)
            # Re-read before merging; prompt edits made in the UI are not discarded.
            current = load_project(path)
            current["attempts"][item["action"]] = status
            atomic_json(path / "project.json", current)
        if (path / "package" / "manifest.json").exists():
            write_manifest(path)
            installed = install_package(path / "package", characters_root, load_project(path)["id"])
            emit("角色包已安装", installed=str(installed))
        if errors:
            raise RuntimeError("；".join(errors))
    finally:
        lock.unlock()


def main(argv=None):
    global EVENT_PATH
    parser = argparse.ArgumentParser(description="Dahlia Pet fixed local material pipeline")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--characters", required=True, type=Path)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--events", type=Path)
    args = parser.parse_args(argv)
    EVENT_PATH = args.events
    try:
        process_pending(args.project, args.characters, args.retry)
    except Exception as exc:
        emit(str(exc), error=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
