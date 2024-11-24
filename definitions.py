import os

# Define the root directory of the project
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define specific directories
LOGS_DIR = os.path.join(ROOT_DIR, "logs")
CORE_DIR = os.path.join(ROOT_DIR, "core")
UTILS_DIR = os.path.join(ROOT_DIR, "utils")

# Ensure necessary directories exist
os.makedirs(LOGS_DIR, exist_ok=True)
