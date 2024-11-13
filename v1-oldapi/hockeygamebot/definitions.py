import os
from hockeygamebot.helpers import arguments

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCES_PATH = os.path.join(PROJECT_ROOT, "resources")
IMAGES_PATH = os.path.join(RESOURCES_PATH, "images")
LOGS_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, os.pardir, "logs"))
TESTS_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, os.pardir, "tests"))
TESTS_RESOURCES_PATH = os.path.join(TESTS_ROOT, "resources")

# Define CONFIG_PATH separately in case of override
args = arguments.get_arguments()
URLS_PATH = os.path.join(PROJECT_ROOT, "config", "urls.yaml")
CONFIG_FILE = "config.yaml" if not args.config else args.config
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", CONFIG_FILE)

VERSION = "2.0.1"
