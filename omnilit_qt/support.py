from __future__ import annotations

import base64
import csv
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_KEY_FORMAT = "omnilit-default-api-key-v1"
DEFAULT_KEY_KDF_ITERATIONS = 260_000
DEFAULT_KEY_AUTO_PASSWORD = "omnilit-bundled-deepseek-key-v1"
DEFAULT_KEY_ENV_NAMES = ("OMNILIT_DEFAULT_DEEPSEEK_API_KEY", "OMNILIT_DEFAULT_API_KEY")
DEFAULT_KEY_FILE_NAME = "APIKey.enc"
USER_KEY_FILE_NAME = "UserAPIKey.enc"
DEFAULT_GLOSSARY_FILENAMES = (
    "00_general_academic.csv",
    "01_ai_ml_data_science.csv",
    "02_catalysis_chemistry_materials.csv",
    "03_biology_medicine_pharmaceuticals.csv",
    "04_energy_environment_chemical_engineering.csv",
    "05_physics_electronics_mechanical_engineering.csv",
    "06_computer_science_software.csv",
    "07_economics_management_finance.csv",
    "08_social_science_education_psychology.csv",
)
GLOSSARY_FILE_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".md"}


@dataclass(frozen=True)
class ModelProfile:
    """描述可选模型档案。"""
    label: str
    provider: str
    model: str
    base_url: str
    note: str
    custom: bool = False


MODEL_PROFILES = (
    ModelProfile("DeepSeek: deepseek-v4-flash", "DeepSeek", "deepseek-v4-flash", "https://api.deepseek.com", "DeepSeek V4 Flash，适合批量论文翻译。"),
    ModelProfile("DeepSeek: deepseek-v4-pro", "DeepSeek", "deepseek-v4-pro", "https://api.deepseek.com", "DeepSeek V4 Pro，质量优先。"),
    ModelProfile("OpenAI: gpt-5.4", "OpenAI", "gpt-5.4", "https://api.openai.com/v1", "OpenAI 高能力模型。"),
    ModelProfile("OpenAI: gpt-5.4-mini", "OpenAI", "gpt-5.4-mini", "https://api.openai.com/v1", "OpenAI 较快、成本较低模型。"),
    ModelProfile("Qwen: qwen3.6-plus", "Qwen / DashScope", "qwen3.6-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", "通义千问均衡模型。"),
    ModelProfile("Qwen: qwen3.6-flash", "Qwen / DashScope", "qwen3.6-flash", "https://dashscope.aliyuncs.com/compatible-mode/v1", "通义千问快速模型。"),
    ModelProfile("Kimi: kimi-k2.6", "Kimi / Moonshot", "kimi-k2.6", "https://api.moonshot.ai/v1", "Kimi 长文本模型。"),
    ModelProfile("Gemini: gemini-2.5-pro", "Google Gemini", "gemini-2.5-pro", "https://generativelanguage.googleapis.com/v1beta/openai/", "Gemini 高质量模型。"),
    ModelProfile("Gemini: gemini-2.5-flash", "Google Gemini", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", "Gemini 快速模型。"),
    ModelProfile("Custom model", "Custom", "", "", "Enter the model ID, API URL, and matching API key.", True),
)


def _import_crypto():
    """加载 Key 加密依赖。参数：无。返回值：cryptography 组件。"""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as exc:
        raise RuntimeError("缺少 cryptography 依赖，无法读写加密 Key。") from exc
    return Fernet, InvalidToken, hashes, PBKDF2HMAC


def _derive_key(password: str, salt: bytes, iterations: int = DEFAULT_KEY_KDF_ITERATIONS) -> bytes:
    """派生 Fernet 密钥。参数：密码、盐和迭代次数。返回值：密钥字节。"""
    _fernet, _invalid_token, hashes, PBKDF2HMAC = _import_crypto()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_api_key(api_key: str, password: str) -> str:
    """加密 API Key。参数：Key 和密码。返回值：JSON 密文。"""
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API Key 不能为空。")
    if not password:
        raise ValueError("加密密码不能为空。")
    Fernet, _invalid_token, _hashes, _kdf = _import_crypto()
    salt = os.urandom(16)
    token = Fernet(_derive_key(password, salt)).encrypt(api_key.encode("utf-8"))
    return json.dumps(
        {
            "format": DEFAULT_KEY_FORMAT,
            "kdf": "PBKDF2HMAC-SHA256",
            "iterations": DEFAULT_KEY_KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "token": token.decode("ascii"),
        },
        ensure_ascii=False,
        indent=2,
    )


def decrypt_api_key(payload_text: str, password: str) -> str:
    """解密 API Key。参数：JSON 密文和密码。返回值：Key 明文。"""
    if not password:
        raise ValueError("请输入 Key 解密密码。")
    Fernet, InvalidToken, _hashes, _kdf = _import_crypto()
    try:
        payload = json.loads(payload_text)
        if not isinstance(payload, dict) or payload.get("format") != DEFAULT_KEY_FORMAT:
            raise ValueError("Key 文件格式不受支持。")
        salt = base64.b64decode(str(payload["salt"]))
        token = str(payload["token"]).encode("ascii")
        iterations = int(payload.get("iterations") or DEFAULT_KEY_KDF_ITERATIONS)
        value = Fernet(_derive_key(password, salt, iterations)).decrypt(token).decode("utf-8").strip()
    except InvalidToken as exc:
        raise ValueError("Key 解密失败：密码不正确或文件已损坏。") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Key "):
            raise
        raise ValueError("Key 文件不是有效的加密 JSON。") from exc
    if not value:
        raise ValueError("Key 文件解密后为空。")
    return value


def write_encrypted_key(path: Path, api_key: str, password: str) -> Path:
    """原子写入 Key。参数：路径、Key 和密码。返回值：目标路径。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encrypt_api_key(api_key, password), encoding="utf-8")
    temporary.replace(path)
    return path


def load_encrypted_key(path: Path, password: str) -> str:
    """读取加密 Key。参数：路径和密码。返回值：Key 明文。"""
    if not path.exists():
        raise FileNotFoundError(path)
    return decrypt_api_key(path.read_text(encoding="utf-8"), password)


def load_default_key(translate_dir: Path, resource_translate_dir: Path, password: str) -> tuple[str, str]:
    """按优先级加载默认 Key。参数：数据目录、资源目录和密码。返回值：Key 与来源。"""
    for path in (translate_dir / DEFAULT_KEY_FILE_NAME, resource_translate_dir / DEFAULT_KEY_FILE_NAME):
        if path.exists():
            return load_encrypted_key(path, password), str(path)
    for env_name in DEFAULT_KEY_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value:
            return value, f"Environment variable {env_name}"
    return "", ""


def load_bundled_default_key(translate_dir: Path, resource_translate_dir: Path) -> tuple[str, str]:
    """Load the bundled deployment key without asking the user for a password."""
    target = translate_dir / DEFAULT_KEY_FILE_NAME
    source = resource_translate_dir / DEFAULT_KEY_FILE_NAME
    if not target.exists() and source.exists() and source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return load_default_key(translate_dir, resource_translate_dir, DEFAULT_KEY_AUTO_PASSWORD)


def glossary_catalog(glossary_dir: Path) -> list[dict[str, object]]:
    """扫描可写术语表。参数：术语表目录。返回值：界面目录条目。"""
    items: list[dict[str, object]] = []
    paths = sorted(
        (
            path for path in glossary_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in GLOSSARY_FILE_EXTENSIONS
            and not path.name.startswith(("~", "_"))
            and "README" not in path.name.upper()
        ),
        key=lambda path: (0 if path.name in DEFAULT_GLOSSARY_FILENAMES else 1, path.name.lower()),
    ) if glossary_dir.exists() else []
    for path in paths:
        filename = path.name
        count = 0
        if path.exists():
            with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
                count = sum(1 for row in csv.reader(handle) if row and any(cell.strip() for cell in row))
        items.append({"name": filename, "path": str(path), "terms": count, "selected": filename == DEFAULT_GLOSSARY_FILENAMES[0]})
    return items


def profile_maps() -> list[dict[str, object]]:
    """导出模型档案。参数：无。返回值：QML 字典列表。"""
    return [asdict(profile) for profile in MODEL_PROFILES]
