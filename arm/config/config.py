#!/usr/bin/python3
"""yaml config loader"""
import json
import os
import yaml

import arm.config.config_utils as config_utils

arm_config: dict[str, str]
arm_config_path: str = os.environ.get("ARM_CONFIG_FILE", "/etc/arm/config/arm.yaml")

abcde_config: dict[str, str]
abcde_config_path: str

apprise_config: dict[str, str]
apprise_config_path: str


def _load_config(fp):
    with open(fp, "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


def _load_abcde(fp):
    with open(fp, "r") as abcde_read_file:
        config = abcde_read_file.read()
    return config


# arm config, open and read yaml contents
# handle arm.yaml migration here
# Load user config
cur_cfg = _load_config(arm_config_path)
# Load template config
arm_config = _load_config(os.path.join(cur_cfg["INSTALLPATH"], "setup/arm.yaml"))

# Update the template config with the user's values
arm_config.update(cur_cfg)

try:
    # Rewrite arm.yaml with any new template keys and the comments.json comments. Values keep their YAML
    # types, the write is skipped when nothing changed, and the file is replaced atomically, so another
    # ARM process starting at the same time never reads a truncated file.
    with open(os.path.join(cur_cfg["INSTALLPATH"], "arm/ui/comments.json"), "r") as comments_file:
        comments = json.load(comments_file)
    config_utils.write_yaml_file(arm_config_path, config_utils.render_arm_yaml(arm_config, comments), arm_config)
except (OSError, ValueError):
    pass

# abcde config file, open and read contents
abcde_config_path = arm_config["ABCDE_CONFIG_FILE"]
abcde_config = _load_abcde(abcde_config_path)

# apprise config, open and read yaml contents
apprise_config_path = arm_config["APPRISE"] or "/etc/arm/config/apprise.yaml"
try:
    apprise_config = _load_config(apprise_config_path)
except OSError:
    apprise_config = {}
