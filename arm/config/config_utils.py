import contextlib
import json
import os
import re
import tempfile

import yaml


def arm_yaml_check_groups(comments, key):
    """
    Check the current key to be added to arm.yaml and insert the group
    separator comment, if the key matches\n
    :param comments: comments dict, containing all comments from the arm.yaml
    :param key: the current post key from form.args
    :return: arm.yaml config with any new comments added
    """
    comment_groups = {'COMPLETED_PATH': "\n" + comments['ARM_CFG_GROUPS']['DIR_SETUP'],
                      'WEBSERVER_IP': "\n" + comments['ARM_CFG_GROUPS']['WEB_SERVER'],
                      'SET_MEDIA_PERMISSIONS': "\n" + comments['ARM_CFG_GROUPS']['FILE_PERMS'],
                      'RIPMETHOD': "\n" + comments['ARM_CFG_GROUPS']['MAKE_MKV'],
                      'HB_PRESET_DVD': "\n" + comments['ARM_CFG_GROUPS']['HANDBRAKE'],
                      'EMBY_REFRESH': "\n" + comments['ARM_CFG_GROUPS']['EMBY']
                                      + "\n" + comments['ARM_CFG_GROUPS']['EMBY_ADDITIONAL'],
                      'NOTIFY_RIP': "\n" + comments['ARM_CFG_GROUPS']['NOTIFY_PERMS'],
                      'APPRISE': "\n" + comments['ARM_CFG_GROUPS']['APPRISE']}
    if key in comment_groups:
        arm_cfg = comment_groups[key]
    else:
        arm_cfg = ""
    return arm_cfg


def arm_yaml_test_bool(key, value):
    """
    we need to test if the key is a bool, as we need to lower() it for yaml\n\n
    or check if key is the webserver ip. \nIf not we need to wrap the value with quotes\n
    :param key: the current key
    :param value: the current value
    :return: the new updated arm.yaml config with new key: values
    """
    if value.lower() == 'false' or value.lower() == "true":
        arm_cfg = f"{key}: {value.lower()}\n"
    else:
        # If we got here, the only key that doesn't need quotes is the webserver key
        # everything else needs "" around the value
        if key == "WEBSERVER_IP":
            arm_cfg = f"{key}: {value.lower()}\n"
        else:
            # This isn't intended to be safe, it's to stop breakages - replace all non escaped quotes with escaped
            escaped = re.sub(r"(?<!\\)[\"\'`]", r'\"', value)
            arm_cfg = f"{key}: \"{escaped}\"\n"
    return arm_cfg


KEY_PATTERN = re.compile(r"[A-Za-z_]\w*")
INTEGER_PATTERN = re.compile(r"-?(?:0|[1-9]\d*)")


def yaml_value(value):
    """
    ``value`` as YAML text that loads back to the same value and type ('' for null)\n
    :param value: a value loaded from arm.yaml / apprise.yaml or converted from the settings form
    :return: the YAML text for the right-hand side of ``key: value``
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        # bools, numbers, mappings and lists in YAML's own (flow) form
        text = yaml.safe_dump(value, default_flow_style=True, width=1 << 30, sort_keys=False, allow_unicode=True)
        return text.strip().removesuffix("...").strip()
    # A JSON string is a valid YAML double-quoted scalar: quotes, backslashes and newlines survive
    return json.dumps(value, ensure_ascii=False)


def yaml_line(key, value):
    text = yaml_value(value)
    return f"{key}: {text}\n" if text else f"{key}:\n"


def display_value(value):
    """How the settings pages show a value, and so what they post back when the field is untouched"""
    return "" if value is None else str(value)


def form_value(text, current=None, has_current=False):
    """
    Convert a settings-form string to the value to save.\n
    An untouched field keeps the current value and type (null, mappings, digit-only strings such as '0123').
    Edited text becomes a bool, a plain integer, a mapping/list when the current value is one, or the string itself.
    """
    text = str(text).strip()
    if has_current and text == display_value(current).strip():
        return current
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if INTEGER_PATTERN.fullmatch(text):
        return int(text)
    if has_current and isinstance(current, (dict, list)):
        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, type(current)):
            return parsed
    return text


def merge_form(current, form_data):
    """
    ``current`` (key order kept) updated from the posted form fields\n
    :param current: the settings as currently loaded
    :param form_data: post data; keys missing from the post keep their current value
    :return: the new settings dict
    """
    values = dict(current or {})
    for key, text in form_data.items():
        # Skip the Cross Site Request Forgery (CSRF) token and anything that is not a plain key
        if key == "csrf_token" or not KEY_PATTERN.fullmatch(str(key)):
            continue
        values[key] = form_value(text, values.get(key), key in values)
    return values


def render_arm_yaml(values, comments):
    """
    Build arm.yaml text for ``values`` with the comments.json group and key comments\n
    :param values: settings dict
    :param comments: comments file loaded as dict
    :return: full arm.yaml as a String
    """
    text = comments['ARM_CFG_GROUPS']['BEGIN'] + "\n\n"
    for key, value in values.items():
        # Add any grouping comments
        text += arm_yaml_check_groups(comments, key)
        # Add the comment for this key from comments.json, if there is one
        comment = comments.get(str(key))
        text += f"\n{comment}\n" if comment else "\n"
        text += yaml_line(key, value)
    return text


def render_plain_yaml(values):
    """YAML text for ``values`` without comments (apprise.yaml)"""
    return "\n\n" + "".join(yaml_line(key, value) for key, value in values.items())


def write_yaml_file(path, text, expected):
    """
    Write ``text`` to ``path`` only if it loads back to ``expected``.\n
    The file is replaced atomically, so another ARM process importing the config never reads a truncated file.
    A file that cannot be replaced (e.g. a single-file bind mount) is rewritten in place after the same check.
    :raises ValueError: the text does not load back to ``expected`` (the file is left as it was)
    :return: False when the file already holds exactly ``text``, otherwise True
    """
    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"Refusing to write {path}: the new text is not valid YAML") from error
    if loaded != dict(expected):
        changed = sorted(key for key in set(loaded) | set(expected) if loaded.get(key) != expected.get(key))
        raise ValueError(f"Refusing to write {path}: {', '.join(changed)} would not load back unchanged")
    try:
        with open(path, "r") as existing:
            if existing.read() == text:
                return False
    except OSError:
        pass
    if not _replace_file(path, text):
        with open(path, "w") as stream:
            stream.write(text)
    return True


def _replace_file(path, text):
    """Atomically replace ``path`` with ``text``; False if the directory does not allow it"""
    try:
        handle, temporary = tempfile.mkstemp(prefix=".arm-yaml-", dir=os.path.dirname(os.path.abspath(path)))
    except OSError:
        return False
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        with contextlib.suppress(OSError):
            os.chmod(temporary, os.stat(path).st_mode & 0o7777)
        os.replace(temporary, path)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        return False
