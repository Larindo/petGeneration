"""Project storage, stable inbox detection and portable, asset-only packages."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid
import zipfile

from .prompts import ACTIONS, DEFAULT_APPEARANCE, VERSION, build_prompt

MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_PERSONALITY = "温柔、好奇、有一点俏皮；关心对方的感受，也有自己的想法。"
DEFAULT_COMMUNICATION_STYLE = "使用自然的中文，通常回复一到三句；称呼用户为朋友，偶尔使用语气词，不连续追问。"


def character_chat(project):
    personality = project.get("personality", "").strip()
    communication = project.get("communication_style", "").strip()
    prompt = f"你是桌宠{project['name']}。{project['appearance']}"
    if personality:
        prompt += f"\n\n【性格】\n{personality}"
    if communication:
        prompt += f"\n\n【沟通习惯】\n{communication}"
    return {"name": project["name"], "personality": personality,
            "communication_style": communication, "system_prompt": prompt}


def valid_id(value):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", str(value)):
        raise ValueError("角色ID必须以小写字母开头，只能包含字母、数字、下划线和短横线。")
    if str(value).lower() in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}:
        raise ValueError("角色ID不能使用系统保留名称。")
    return str(value)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_project(root, name, appearance=DEFAULT_APPEARANCE):
    if not str(name).strip():
        raise ValueError("请输入角色名称。")
    cid = "pet_" + uuid.uuid4().hex[:12]
    path = Path(root) / cid
    path.mkdir(parents=True)
    (path / "inbox").mkdir()
    save_project(path, {
        "id": cid, "name": name.strip(), "appearance": appearance,
        "personality": DEFAULT_PERSONALITY, "communication_style": DEFAULT_COMMUNICATION_STYLE,
        "phrases": ["你好呀~", "陪你一会儿~"],
        "actions": {a.id: {"description": a.example, "seconds": a.seconds,
                          "start": 0, "end": 0, "source_facing": "left"} for a in ACTIONS},
        "attempts": {},
    })
    return path


def load_project(path):
    doc = json.loads((Path(path) / "project.json").read_text(encoding="utf-8"))
    valid_id(doc["id"])
    if doc.get("version") != VERSION:
        raise ValueError("不支持的角色项目版本。")
    doc.setdefault("personality", "")
    doc.setdefault("communication_style", "")
    return doc


def save_project(path, data):
    actions = {}
    for a in ACTIONS:
        raw = data.get("actions", {}).get(a.id, {})
        seconds = float(raw.get("seconds", a.seconds))
        description = str(raw.get("description", a.example)).strip()
        build_prompt(data["appearance"], a.id, description, seconds)
        start, end = float(raw.get("start", 0)), float(raw.get("end", 0))
        if not (0 <= start <= 60 and 0 <= end <= 60) or (end and end <= start):
            raise ValueError("片段结束时间必须晚于开始时间；0表示视频末尾。")
        actions[a.id] = {"description": description, "seconds": seconds, "start": start,
                         "end": end, "source_facing": "right" if raw.get("source_facing") == "right" else "left"}
    name = str(data["name"]).strip()[:80]
    if not name:
        raise ValueError("请输入角色名称。")
    identity = {}
    for key, label in (("personality", "性格"), ("communication_style", "沟通习惯")):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > 3000:
            raise ValueError(f"{label}需为不超过3000字的文本。")
        identity[key] = value.strip()
    phrases = [str(p).strip()[:200] for p in data.get("phrases", []) if str(p).strip()][:50]
    doc = {"version": VERSION, "id": valid_id(data["id"]), "name": name,
           "appearance": str(data["appearance"]).strip(), "actions": actions,
           "phrases": phrases or ["你好呀~"], "attempts": data.get("attempts", {}), **identity}
    atomic_json(Path(path) / "project.json", doc)
    return doc


def input_fingerprint(path, settings=None):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(json.dumps(settings or {}, sort_keys=True).encode())
    return digest.hexdigest()


def pending_inputs(path, *, retry=False):
    path = Path(path)
    project = load_project(path)
    found = {}
    for source in sorted((path / "inbox").iterdir()):
        if not source.is_file() or source.suffix.lower() not in MEDIA:
            continue
        action = source.stem
        if action not in {"portrait", *(a.id for a in ACTIONS)}:
            continue
        if action == "portrait" and source.suffix.lower() not in IMAGE:
            raise ValueError("portrait必须是图片。")
        if action != "portrait" and source.suffix.lower() in IMAGE:
            raise ValueError(f"{action}需要视频；单张图片请命名为portrait。")
        if action in found:
            raise ValueError(f"{action}有多个同名素材，请只保留一个。")
        settings = project["actions"].get(action, {})
        fingerprint = input_fingerprint(source, settings)
        found[action] = {"action": action, "path": str(source), "fingerprint": fingerprint}
    priority = ["portrait", "idle", "wave", *(a.id for a in ACTIONS if a.id not in ("idle", "wave"))]
    return [item for key, item in sorted(found.items(), key=lambda pair: priority.index(pair[0]))
            if retry or project["attempts"].get(key, {}).get("fingerprint") != item["fingerprint"]]


def sync_identity(project_path, characters_root):
    """Apply edited identity to this project's own packages, without re-encoding."""
    path = Path(project_path)
    project = load_project(path)
    for package in (path / "package", Path(characters_root) / project["id"]):
        manifest_path = package / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("studio", {}).get("project_id") != project["id"]:
            raise ValueError("角色包与当前项目不匹配。")
        manifest["name"] = project["name"]
        manifest["studio"]["phrases"] = project["phrases"]
        manifest.setdefault("chat", {}).update(character_chat(project))
        atomic_json(manifest_path, manifest)


def _validate_package(package):
    package = Path(package)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    idle = manifest.get("idle")
    if not isinstance(idle, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", idle):
        raise ValueError("角色包缺少合法待机动画。")
    if not (package / "videos" / "idle" / f"{idle}.webm").is_file():
        raise ValueError("角色包缺少待机文件。")
    return manifest


def asset_files(package):
    package = Path(package)
    for p in package.rglob("*"):
        if p.is_symlink():
            raise ValueError("角色包不接受符号链接。")
        if not p.is_file():
            continue
        rel = p.relative_to(package)
        if str(rel).replace("\\", "/") in {"manifest.json", "portrait.png", "SOURCE.txt"} or (
            rel.parts[0] == "videos" and (p.suffix == ".webm" or p.name == "move_strides.json")
        ):
            yield p, rel


def install_package(package, root, cid):
    cid = valid_id(cid)
    package, root = Path(package), Path(root)
    manifest = _validate_package(package)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / cid
    if destination.exists():
        try:
            old = _validate_package(destination)
        except (OSError, ValueError):
            raise FileExistsError("目标角色已存在且不属于这个工坊项目。") from None
        if not manifest.get("studio", {}).get("project_id") or old.get("studio", {}).get("project_id") != manifest["studio"]["project_id"]:
            raise FileExistsError("同名角色已存在，不覆盖其他项目。")
    staging = Path(tempfile.mkdtemp(prefix=".studio-", dir=root))
    backup = root / f".previous-{cid}-{uuid.uuid4().hex}"
    try:
        for source, rel in asset_files(package):
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup.exists():
                backup.rename(destination)
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    # Only our exact generated backup is removed after successful replacement.
    if backup.exists() and backup.parent.resolve() == root.resolve():
        shutil.rmtree(backup)
    return destination


def export_package(package, target, cid):
    _validate_package(package)
    cid = valid_id(cid)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, rel in asset_files(package):
                archive.write(source, f"{cid}/{rel.as_posix()}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def import_package(archive, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=root) as scratch:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > 3000 or sum(e.file_size for e in entries) > 1024**3:
                raise ValueError("角色包超过大小或文件数限制。")
            ids = set()
            for entry in entries:
                p = PurePosixPath(entry.filename)
                if p.is_absolute() or ".." in p.parts or "\\" in entry.filename or ":" in entry.filename or len(p.parts) < 2:
                    raise ValueError("角色包路径不安全。")
                ids.add(valid_id(p.parts[0]))
            if len(ids) != 1:
                raise ValueError("每个包必须只包含一个角色。")
            cid = ids.pop()
            for entry in entries:
                if entry.is_dir():
                    continue
                output = Path(scratch).joinpath(*PurePosixPath(entry.filename).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                with z.open(entry) as src, output.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        return install_package(Path(scratch) / cid, root, cid)
