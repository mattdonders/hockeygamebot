from pathlib import Path

# Define the root directory of the project
ROOT_DIR = Path(__file__).resolve().parent

# Define specific directories
LOGS_DIR = ROOT_DIR / "logs"
CORE_DIR = ROOT_DIR / "core"
UTILS_DIR = ROOT_DIR / "utils"
IMAGES_DIR = ROOT_DIR / "images"
RESOURCES_DIR = ROOT_DIR / "resources"
ROSTERS_DIR = RESOURCES_DIR / "rosters"
LOGOS_DIR = RESOURCES_DIR / "logos"

# Ensure necessary directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
ROSTERS_DIR.mkdir(parents=True, exist_ok=True)
LOGOS_DIR.mkdir(parents=True, exist_ok=True)
