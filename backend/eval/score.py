"""Score exact fields on the synthetic eval set. Run from backend/ with python -m eval.score."""
import argparse
import asyncio
import csv
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def grade(case, actions):
    # All cases contain one request. An extra proposed action invalidates the prediction.
    action = actions[0] if len(actions) == 1 else {}
    args = action.get("args", {})
    amount = args.get("amount")
    return {
        "action": action.get("tool") == case["action"],
        "name": args.get("name") == case["name"],
        "amount": None if not case["amount"] else amount == float(case["amount"]),
    }


def run(mode, output):
    # Import the application only after selecting the private evaluation database.
    from brain import planner
    import config
    import db
    import seed
    from voice import audio, local

    if mode == "local" and not local.stt_ready():
        raise SystemExit("Install the local model with python -m voice.setup before running this mode.")
    keys = [config.SARVAM_API_KEY, config.GROQ_API_KEY, config.GEMINI_API_KEY]
    if mode == "llm" and not any(keys):
        raise SystemExit("LLM benchmark unrun: no hosted planner is configured.")
    if mode == "dual" and sum(bool(key) for key in keys) < 2:
        raise SystemExit("Dual STT benchmark unrun: two hosted speech engines are required.")
    seed.run("kirana")
    results = []
    progress_dir = Path(config.ROOT) / "data" / "eval-progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress = progress_dir / (mode + ".jsonl")
    progress.write_text("", encoding="utf8")
    with (HERE / "cases.csv").open(newline="", encoding="utf8") as source:
        for case in csv.DictReader(source):
            text = case["reference"]
            alternate = ""
            engines = []
            if mode in {"local", "dual"}:
                data = (HERE / "audio" / (case["id"] + ".wav")).read_bytes()
                # Decode audio with no language hint, label, name or transcript provided.
                wav = audio.clean(data, "wav")
                if mode == "local":
                    text, _, _ = local.transcribe(wav)
                    engines = [Path(config.LOCAL_STT_MODEL).name]
                else:
                    from brain.agent import _keyterms
                    from voice import stt
                    a, b = asyncio.run(stt.hear_twice(wav, _keyterms()))
                    text, alternate = a.text, b.text
                    engines = [part.engine for part in (a, b) if part.text]
            provider = "rules"
            if mode == "dual" and len(set(engines)) < 2:
                actions, provider = [], "two transcripts unavailable"
            elif mode in {"llm", "dual"}:
                actions, provider = planner.plan(text, "owner", alternate)
                if provider == "rules":
                    actions, provider = [], "hosted planner unavailable"
            else:
                actions = planner.rule_plan(text, "owner")
            results.append({"id": case["id"], "transcript": text, "alternate": alternate,
                            "engines": engines, "planner": provider, "prediction": actions, "correct": grade(case, actions)})
            with progress.open("a", encoding="utf8") as completed:
                completed.write(json.dumps(results[-1], ensure_ascii=False) + "\n")
            print(case["id"], results[-1]["correct"], flush=True)
    totals = {}
    for field in ("amount", "name", "action"):
        scores = [row["correct"][field] for row in results if row["correct"][field] is not None]
        totals[field] = {"correct": sum(scores), "eligible": len(scores)}
    report = {"mode": mode, "model": Path(config.LOCAL_STT_MODEL).name if mode == "local" else None,
              "notes": len(results), "totals": totals, "results": results}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(totals), flush=True)
    db._conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["rules", "local", "llm", "dual"],
                        help="rules and local run offline; llm and dual use the explicitly configured hosted services")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bolo-eval-", ignore_cleanup_errors=True) as folder:
        os.environ["BOLO_DATA_DIR"] = folder
        run(args.mode, args.output or HERE / (args.mode + ".json"))


if __name__ == "__main__":
    main()
