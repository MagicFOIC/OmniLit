from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "packages" / "shared-schema" / "schemas" / "omnilit-v1.schema.json"
TS_PATH = ROOT / "packages" / "shared-schema" / "src" / "generated.ts"
PY_PATH = ROOT / "omnilit_qt" / "shared_protocol_models.py"


def _ref_name(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def _ts_type(spec: dict[str, Any]) -> str:
    if "anyOf" in spec:
        return " | ".join(_ts_type(item) for item in spec["anyOf"])
    if "$ref" in spec:
        return _ref_name(spec["$ref"])
    if "const" in spec:
        return json.dumps(spec["const"])
    if "enum" in spec:
        return " | ".join(json.dumps(item) for item in spec["enum"])
    kind = spec.get("type")
    if kind == "string": return "string"
    if kind in {"integer", "number"}: return "number"
    if kind == "boolean": return "boolean"
    if kind == "array": return f"Array<{_ts_type(spec.get('items') or {})}>"
    if kind == "object":
        extra = spec.get("additionalProperties")
        return f"Record<string, {_ts_type(extra)}>" if isinstance(extra, dict) else "Record<string, unknown>"
    return "unknown"


def _py_type(spec: dict[str, Any]) -> str:
    if "anyOf" in spec:
        return " | ".join(_py_type(item) for item in spec["anyOf"])
    if "$ref" in spec:
        return _ref_name(spec["$ref"])
    if "const" in spec:
        return f"Literal[{spec['const']!r}]"
    if "enum" in spec:
        return "Literal[" + ", ".join(repr(item) for item in spec["enum"]) + "]"
    kind = spec.get("type")
    if kind == "string": return "str"
    if kind == "integer": return "int"
    if kind == "number": return "float"
    if kind == "boolean": return "bool"
    if kind == "array": return f"list[{_py_type(spec.get('items') or {})}]"
    if kind == "object":
        extra = spec.get("additionalProperties")
        return f"dict[str, {_py_type(extra)}]" if isinstance(extra, dict) else "dict[str, Any]"
    return "Any"


def _typescript(definitions: dict[str, Any]) -> str:
    lines = ["// Generated from omnilit-v1.schema.json. Do not edit.", "", "export type JsonValue = unknown", ""]
    for name, spec in definitions.items():
        required = set(spec.get("required") or [])
        lines.append(f"export interface {name} {{")
        for field, field_spec in (spec.get("properties") or {}).items():
            optional = "" if field in required else "?"
            lines.append(f"  {field}{optional}: {_ts_type(field_spec)}")
        lines.extend(["  [key: string]: unknown", "}", ""])
    lines.extend(['export const PROTOCOL_VERSION = "1.0" as const', "export const GRAPH_SCHEMA_VERSION = 1 as const", ""])
    return "\n".join(lines)


def _python(definitions: dict[str, Any]) -> str:
    lines = [
        '"""Generated from omnilit-v1.schema.json. Do not edit."""',
        "from __future__ import annotations", "", "from typing import Any, Literal, NotRequired, TypedDict", "",
    ]
    for name, spec in definitions.items():
        required = set(spec.get("required") or [])
        lines.append(f"class {name}(TypedDict):")
        properties = spec.get("properties") or {}
        if not properties:
            lines.append("    pass")
        for field, field_spec in properties.items():
            annotation = _py_type(field_spec)
            if field not in required:
                annotation = f"NotRequired[{annotation}]"
            lines.append(f"    {field}: {annotation}")
        lines.append("")
    lines.extend(['PROTOCOL_VERSION: Literal["1.0"] = "1.0"', "GRAPH_SCHEMA_VERSION: Literal[1] = 1", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    outputs = {TS_PATH: _typescript(schema["$defs"]), PY_PATH: _python(schema["$defs"])}
    stale = [path for path, content in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != content]
    if args.check:
        if stale:
            print("Generated shared protocol types are stale: " + ", ".join(str(path.relative_to(ROOT)) for path in stale))
            return 1
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
