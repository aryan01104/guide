"""Centralised settings loader (reads .env once)."""
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MODEL      = os.getenv("MODEL", "gpt-4o-mini")
