"""Stable CLI for the same fixed pipeline used by the character workshop."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pet.character_studio.processing import main

if __name__ == "__main__":
    raise SystemExit(main())
