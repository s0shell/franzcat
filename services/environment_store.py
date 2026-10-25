"""
Environment definitions (connection presets) loaded from ./profiles/*.json.

One JSON file per environment; every section is optional. Secrets such as
the key passphrase are not supported. This module is UI-free: it turns files
into flat {settings-key: value} dicts that SettingsStore can apply.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_FORMAT_VERSION = 1

# <section>.<field> -> (type, [settings keys it fills])
_FIELD_MAP = {
    "schema_registry.url":  (str,  ["schema.url"]),
    "schema_registry.mtls": (bool, ["certs.mtls_sr"]),
    "broker.bootstrap":     (str,  ["reader.bar_broker", "writer.bar_broker"]),
    "broker.mtls":          (bool, ["certs.mtls_broker"]),
    "certs.ca_cert":        (str,  ["certs.ca_cert"]),
    "certs.client_cert":    (str,  ["certs.client_cert"]),
    "certs.client_key":     (str,  ["certs.client_key"]),
    "certs.verify":         (bool, ["certs.verify"]),
    "defaults.topic":          (str, ["reader.bar_topic", "writer.bar_topic"]),
    "defaults.consumer_group": (str, ["reader.bar_group"]),
}
_PATH_FIELDS = {"certs.ca_cert", "certs.client_cert", "certs.client_key"}

# every settings key an environment may touch
ENV_KEYS = sorted({k for _, keys in _FIELD_MAP.values() for k in keys})


def environments_dir() -> Path:
    """./profiles next to the application sources."""
    return Path(__file__).resolve().parent.parent / "profiles"


@dataclass
class Environment:
    name: str
    description: str = ""
    values: dict = field(default_factory=dict)   # settings key -> value
    source: str = ""


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def parse_environment(raw, filename: str) -> Environment:
    """Build an Environment from decoded JSON; raises ValueError if unusable."""
    if not isinstance(raw, dict):
        raise ValueError("top level must be a JSON object")
    version = raw.get("version", ENV_FORMAT_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version > ENV_FORMAT_VERSION:
        raise ValueError(f"unsupported version {version!r}")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        name = Path(filename).stem
    desc = raw.get("description")
    env = Environment(name.strip(), desc if isinstance(desc, str) else "", source=filename)

    for dotted, (typ, keys) in _FIELD_MAP.items():
        section, key = dotted.split(".")
        value = (raw.get(section) or {}).get(key) if isinstance(raw.get(section), dict) else None
        if value is None:
            continue
        if not isinstance(value, typ):
            raise ValueError(f"'{dotted}' must be {typ.__name__}")
        if dotted in _PATH_FIELDS:
            value = _expand(value)
        for k in keys:
            env.values[k] = value
    return env


def load_environments(directory: Path | None = None) -> tuple[list[Environment], list[str]]:
    """Return (environments sorted by name, warnings). Bad files are skipped."""
    directory = directory or environments_dir()
    envs: dict[str, Environment] = {}
    warnings: list[str] = []
    if not directory.is_dir():
        return [], warnings

    for path in sorted(directory.glob("*.json")):
        try:
            env = parse_environment(json.loads(path.read_text(encoding="utf-8")), path.name)
        except (OSError, ValueError) as exc:
            warnings.append(f"{path.name}: {exc}")
            continue
        if env.name in envs:
            warnings.append(f"{path.name}: duplicate name '{env.name}' ignored")
            continue
        envs[env.name] = env
    return sorted(envs.values(), key=lambda e: e.name.lower()), warnings
