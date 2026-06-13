from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PaddleOCR-VL document parsing outside the OmniLit main env.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--server-url", default="")
    parser.add_argument("--model", default="PaddlePaddle/PaddleOCR-VL-1.6")
    parser.add_argument("--pipeline-version", default="v1.6", choices=["v1.5", "v1.6"])
    parser.add_argument("--engine", default="paddle", choices=["transformers", "paddle", "server"])
    parser.add_argument("--merge-tables", action="store_true")
    parser.add_argument("--relevel-titles", action="store_true")
    args = parser.parse_args(argv)

    input_pdf = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    from paddleocr import PaddleOCRVL

    pipeline_kwargs: dict[str, Any] = {}
    if args.pipeline_version == "v1.5":
        pipeline_kwargs["pipeline_version"] = "v1.5"
    elif args.pipeline_version == "v1.6":
        pipeline_kwargs["pipeline_version"] = "v1.6"

    if args.server_url:
        pipeline_kwargs.update(
            {
                "vl_rec_backend": "vllm-server",
                "vl_rec_server_url": args.server_url,
                "vl_rec_api_model_name": args.model,
            }
        )
    elif args.engine:
        pipeline_kwargs["engine"] = args.engine

    try:
        pipeline = PaddleOCRVL(**pipeline_kwargs)
    except TypeError:
        pipeline_kwargs.pop("pipeline_version", None)
        pipeline = PaddleOCRVL(**pipeline_kwargs)

    output = pipeline.predict(input=str(input_pdf))
    pages_res = list(output)
    restructure = getattr(pipeline, "restructure_pages", None)
    if callable(restructure):
        try:
            restructured = restructure(
                pages_res,
                merge_tables=bool(args.merge_tables),
                relevel_titles=bool(args.relevel_titles),
            )
            if restructured is not None:
                pages_res = list(restructured)
        except Exception:
            pass

    pages = []
    markdown_parts: list[str] = []
    for page_index, result in enumerate(pages_res):
        _try_save(result, "save_to_json", output_dir)
        _try_save(result, "save_to_markdown", output_dir)
        json_value = _jsonable(getattr(result, "json", None))
        markdown_value = str(getattr(result, "markdown", "") or "")
        if markdown_value:
            markdown_parts.append(markdown_value)
        pages.append(
            {
                "page": page_index,
                "json": json_value,
                "markdown": markdown_value,
                "raw": _jsonable(result),
            }
        )

    result_payload = {
        "engine": "paddleocr_vl",
        "model": args.model,
        "pipelineVersion": args.pipeline_version,
        "pages": pages,
    }
    (output_dir / "paddleocr_vl_result.json").write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "paddleocr_vl.md").write_text("\n\n".join(markdown_parts), encoding="utf-8")
    return 0


def _try_save(result: Any, method_name: str, output_dir: Path) -> None:
    method = getattr(result, method_name, None)
    if not callable(method):
        return
    try:
        method(save_path=str(output_dir))
    except TypeError:
        method(str(output_dir))
    except Exception:
        return


def _jsonable(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except Exception:
            pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
