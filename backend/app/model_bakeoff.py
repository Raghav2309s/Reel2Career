from __future__ import annotations

"""
Isolated Reel2Career model bake-off.

This script deliberately does NOT write Analysis/Action/Resource rows.
It reuses the production evidence collection, prompt, JSON parser, and
validator so model comparisons measure the actual Reel2Career contract.

Windows example:
    set REEL2CAREER_REEL_ID=7
    python backend\app\model_bakeoff.py

Override the model list with a comma-separated environment variable:
    set REEL2CAREER_BAKEOFF_MODELS=gemini/gemini-2.5-flash,gemini/gemini-2.5-flash-lite

The final report is written to vault/ai_prompts/bakeoff/.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from ai_extracted import (
    SessionLocal,
    Reel,
    build_prompt,
    collect_evidence,
    parse_ai_json_output,
    validate_ai_result,
)


OMNIROUTE = BASE_DIR / "node_modules" / ".bin" / "omniroute.cmd"
OUTPUT_DIR = BASE_DIR / "vault" / "ai_prompts" / "bakeoff"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODELS = [
    "gemini/gemini-2.5-flash",
    "gemini/gemini-2.5-flash-lite",
]

MODELS = [
    item.strip()
    for item in os.getenv(
        "REEL2CAREER_BAKEOFF_MODELS",
        ",".join(DEFAULT_MODELS),
    ).split(",")
    if item.strip()
]

MAX_TOKENS = int(os.getenv("REEL2CAREER_BAKEOFF_MAX_TOKENS", "8000"))
TIMEOUT_SECONDS = int(os.getenv("REEL2CAREER_BAKEOFF_TIMEOUT", "180"))


def run_model(prompt: str, model: str, reel_id: int) -> dict:
    """Run one model and return transport/parse/validation metrics."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = model.replace("/", "__").replace(":", "_")
    prompt_path = OUTPUT_DIR / f"reel_{reel_id}_{safe_model}_{stamp}_prompt.txt"
    output_path = OUTPUT_DIR / f"reel_{reel_id}_{safe_model}_{stamp}_raw.txt"

    prompt_path.write_text(prompt, encoding="utf-8")

    command = [
        "cmd.exe",
        "/d",
        "/c",
        str(OMNIROUTE),
        "chat",
        "--file",
        str(prompt_path),
        "--model",
        model,
        "--max-tokens",
        str(MAX_TOKENS),
        "--no-history",
    ]

    started = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        return {
            "model": model,
            "status": "timeout",
            "elapsed_seconds": round(elapsed, 2),
            "error": f"Timed out after {TIMEOUT_SECONDS}s",
        }

    elapsed = time.perf_counter() - started
    raw = completed.stdout.strip()
    output_path.write_text(
        raw + ("\n\nSTDERR:\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )

    result = {
        "model": model,
        "status": "transport_error" if completed.returncode else "received",
        "elapsed_seconds": round(elapsed, 2),
        "return_code": completed.returncode,
        "prompt_chars": len(prompt),
        "raw_output_chars": len(raw),
        "prompt_file": str(prompt_path.relative_to(BASE_DIR)),
        "raw_output_file": str(output_path.relative_to(BASE_DIR)),
    }

    if completed.returncode:
        result["error"] = (completed.stderr or completed.stdout)[-4000:]
        return result

    try:
        parsed = parse_ai_json_output(raw)
        result["json_parse"] = "pass"
    except ValueError as exc:
        result["json_parse"] = "fail"
        result["validation"] = "not_run"
        result["error"] = str(exc)
        return result

    try:
        validated = validate_ai_result(parsed, current_evidence)
        result["validation"] = "pass"
        result["summary"] = validated.get("summary", "")
        result["topic"] = validated.get("topic", "")
        result["career_area"] = validated.get("career_area", "")
        result["career_relevance"] = validated.get("career_relevance", 0.0)
        result["skills"] = len(validated.get("skills", []))
        result["actions"] = len(validated.get("actions", []))
        result["suggested_next_steps"] = len(validated.get("suggested_next_steps", []))
        result["resources"] = len(validated.get("resources", []))
        result["claims"] = len(validated.get("claims", []))
    except ValueError as exc:
        result["validation"] = "fail"
        result["error"] = str(exc)

    return result


current_evidence = []


def main() -> int:
    global current_evidence

    if not OMNIROUTE.exists():
        print(f"OmniRoute executable not found: {OMNIROUTE}")
        return 1

    requested_id = os.getenv("REEL2CAREER_REEL_ID", "7").strip()
    try:
        reel_id = int(requested_id)
    except ValueError:
        print("REEL2CAREER_REEL_ID must be an integer.")
        return 1

    db = SessionLocal()
    try:
        reel = db.query(Reel).filter(Reel.id == reel_id).first()
        if reel is None:
            print(f"Reel {reel_id} was not found in the local SQLite database.")
            return 1

        current_evidence = collect_evidence(db, reel.id)
        prompt = build_prompt(reel, current_evidence)

        print("=== Reel2Career Model Bake-off ===")
        print(f"Reel: {reel.id}")
        print(f"Evidence records: {len(current_evidence)}")
        print(f"Prompt size: {len(prompt):,} characters")
        print(f"Models: {', '.join(MODELS)}")
        print()

        results = []
        for model in MODELS:
            print(f"Testing {model}...")
            result = run_model(prompt, model, reel.id)
            results.append(result)

            status = result.get("status")
            validation = result.get("validation", "not_run")
            print(
                f"  transport={status} "
                f"json={result.get('json_parse', 'not_run')} "
                f"validation={validation} "
                f"latency={result.get('elapsed_seconds', '?')}s"
            )

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reel_id": reel.id,
            "evidence_records": len(current_evidence),
            "prompt_chars": len(prompt),
            "models": MODELS,
            "results": results,
        }

        report_path = OUTPUT_DIR / f"reel_{reel.id}_bakeoff_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print()
        print(f"Report: {report_path.relative_to(BASE_DIR)}")
        print("No production database rows were written.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
