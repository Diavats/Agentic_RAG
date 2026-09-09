"""
CLI entrypoint. Three commands: ingest, index, ask.

Usage:
    python -m src.main ingest --data data/sample_stocks.csv --dataset-name stocks
    python -m src.main index  --dataset-name stocks
    python -m src.main ask    --dataset-name stocks --question "..."

To prove the pipeline is data-agnostic, run the exact same three commands
against data/sample_products.csv with --dataset-name products.
No code changes needed.
"""
import argparse
import json
from pathlib import Path

from src.agent import ask as agent_ask
from src.build_index import build_index
from src.config import GENERATED_DIR
from src.loader import load_tabular
from src.narrative_generator import generate_all


def cmd_ingest(args: argparse.Namespace) -> None:
    rows = load_tabular(args.data)
    print(f"Loaded {len(rows)} rows from {args.data}")
    stories = generate_all(rows)

    out_dir = Path(GENERATED_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.dataset_name}_stories.json"
    with open(out_path, "w") as f:
        json.dump(stories, f, indent=2)
    print(f"Saved {len(stories)} generated stories to {out_path}")


def cmd_index(args: argparse.Namespace) -> None:
    stories_path = Path(GENERATED_DIR) / f"{args.dataset_name}_stories.json"
    with open(stories_path) as f:
        stories = json.load(f)
    build_index(stories, args.dataset_name)


def cmd_ask(args: argparse.Namespace) -> None:
    result = agent_ask(args.question, args.dataset_name)
    print("\n" + "=" * 60)
    print("ANSWER:")
    print(result["answer"])
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic RAG pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Load data + generate narrative stories")
    p_ingest.add_argument("--data", required=True, help="Path to a .csv or .xlsx file")
    p_ingest.add_argument("--dataset-name", required=True, help="Name for this dataset")
    p_ingest.set_defaults(func=cmd_ingest)

    p_index = sub.add_parser("index", help="Build hybrid retrieval index from generated stories")
    p_index.add_argument("--dataset-name", required=True)
    p_index.set_defaults(func=cmd_index)

    p_ask = sub.add_parser("ask", help="Ask a question using the agentic RAG pipeline")
    p_ask.add_argument("--dataset-name", required=True)
    p_ask.add_argument("--question", required=True)
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()