# Reel2Career AI model bake-off

The repository already contains a production AI extraction pipeline in `backend/app/ai_extracted.py`. It collects evidence, builds the production prompt, parses model JSON, validates evidence grounding, and only then persists the result.

`model_bakeoff.py` is intentionally isolated from persistence. It reuses the same evidence collection, prompt, parser, and validator, then records transport, JSON, validation, latency, and output-size metrics under `vault/ai_prompts/bakeoff/`.

## Run

From the repository root on Windows:

```powershell
$env:REEL2CAREER_REEL_ID="7"
python backend\app\model_bakeoff.py
```

Default candidates:

- `gemini/gemini-2.5-flash`
- `gemini/gemini-2.5-flash-lite`

To test another set:

```powershell
$env:REEL2CAREER_BAKEOFF_MODELS="gemini/gemini-2.5-flash,gemini/gemini-2.5-flash-lite"
python backend\app\model_bakeoff.py
```

## Decision rule

Do not select a model from latency alone. A candidate should first pass the Reel2Career evidence validator consistently. Among passing candidates, compare quality, useful extraction counts, latency, and operational reliability.

No `Analysis`, `Action`, `Resource`, or other production database rows are written by the bake-off.
