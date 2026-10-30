"""Build an independent Windows portable product without personal assets."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, help="Optional local u2net.onnx for offline creation")
    parser.add_argument("--skip-zip", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "DahliaPet", "--distpath", "dist-dahlia", "--workpath", "build/dahlia",
        "--specpath", "build", "--paths", str(root),
        "--collect-submodules", "pet", "--collect-all", "rembg",
        "--recursive-copy-metadata", "rembg",
        "--collect-all", "imageio_ffmpeg", "--collect-all", "onnxruntime",
        "--collect-all", "keyring", "--collect-all", "win32ctypes",
        "--collect-all", "edge_tts", "--collect-all", "tzdata",
        "--collect-all", "PySide6.QtMultimedia",
        "--collect-data", "rapidocr",
        "--add-data", "pet/persona_presets;pet/persona_presets",
        "--add-data", "pet/menu_templates;pet/menu_templates",
        "--add-data", "pet/chat/legacy_styles.qss;pet/chat",
        "--add-data", "pet/chat/modern_styles.qss;pet/chat",
        "--add-data", "LICENSE;.", "--add-data", "THIRD_PARTY_NOTICES.md;.",
        "--add-data", "docs/DAHLIA-PET.md;.",
    ]
    # Optional heavyweight ML backends are not part of the local CPU pipeline.
    for module in ["torch", "tensorflow", "transformers", "pytest", "IPython", "matplotlib"]:
        command += ["--exclude-module", module]
    if args.model:
        if not args.model.is_file():
            raise FileNotFoundError(args.model)
        command += ["--add-data", f"{args.model.resolve()};studio_models/models/u2net"]
    for i, value in enumerate(command):
        if i > 0 and command[i - 1] == "--add-data":
            source, destination = value.split(";", 1)
            command[i] = f"{Path(source).resolve()};{destination}"
    command += [str(root / "packaging/dahlia_entry.py")]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if os.name == "nt":
        # Qt uses Windows' unversioned ICU API. Foreign Poppler/Conda ICU DLLs
        # found via PATH export different symbols and make QtCore fail to load.
        windows = Path(os.environ["SystemRoot"])
        env["PATH"] = os.pathsep.join(map(str, [
            Path(sys.executable).parent, Path(sys.base_prefix),
            windows / "System32", windows,
        ]))
    subprocess.run(command, check=True, env=env)
    bundle = root / "dist-dahlia" / "DahliaPet"
    for name in ("DAHLIA-PET.md", "DAHLIA-PET-VALIDATION.md", "ASSET-PIPELINE.md"):
        shutil.copy2(root / "docs" / name, bundle / name)
    if os.name == "nt":
        import pefile
        qtcore = bundle / "_internal" / "PySide6" / "Qt6Core.dll"
        pe = pefile.PE(str(qtcore))
        for dep in pe.DIRECTORY_ENTRY_IMPORT:
            if dep.dll.lower() != b"icuuc.dll":
                continue
            bundled = bundle / "_internal" / "icuuc.dll"
            candidate = bundled if bundled.exists() else windows / "System32" / "icuuc.dll"
            symbols = {s.name for s in pefile.PE(str(candidate)).DIRECTORY_ENTRY_EXPORT.symbols}
            if any(imp.name and imp.name not in symbols for imp in dep.imports):
                raise RuntimeError("Incompatible ICU runtime; refusing to distribute this build")
    forbidden = ["config.json", "config-slot-0.json", "project.json"]
    if any(path.name in forbidden for path in bundle.rglob("*")):
        raise RuntimeError("Personal configuration unexpectedly included in bundle")
    if not args.skip_zip:
        shutil.make_archive(str(root / "dist-dahlia" / "DahliaPet-Windows"), "zip", bundle.parent, bundle.name)
    print(bundle / "DahliaPet.exe")


if __name__ == "__main__":
    main()
