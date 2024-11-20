# paths.py

import os

# Get the absolute path to the project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Define paths relative to the project root
RESOURCES_PATH = os.path.join(PROJECT_ROOT, "resources")
IMAGES_PATH = os.path.join(RESOURCES_PATH, "images")
LOGS_PATH = os.path.join(PROJECT_ROOT, "logs")
TESTS_ROOT = os.path.join(PROJECT_ROOT, "tests")
TESTS_RESOURCES_PATH = os.path.join(TESTS_ROOT, "resources")

# Define the configuration file path
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configuration", "config.yaml")

# Application version
VERSION = "2.0.0"
