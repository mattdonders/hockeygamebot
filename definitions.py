import os

# Define the root directory of the project
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Define specific directories
LOGS_DIR = os.path.join(ROOT_DIR, "logs")
CORE_DIR = os.path.join(ROOT_DIR, "core")
UTILS_DIR = os.path.join(ROOT_DIR, "utils")
IMAGES_DIR = os.path.join(ROOT_DIR, "images")
RESOURCES_DIR = os.path.join(ROOT_DIR, "resources")

# Ensure necessary directories exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(RESOURCES_DIR, exist_ok=True)
