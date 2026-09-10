"""
CLI entrypoint: setup, ingest, index, ask.

    python -m src.main setup                    # rebuild indexes from committed units
    python -m src.main ingest --data data/sample_stocks.csv --domain financial
    python -m src.main ingest --data data/medical_placeholder.csv --domain medical
    python -m src.main ingest --data data/medical_guideline_placeholder.docx --domain medical
    python -m src.main index  --domain financial
    python -m src.main index  --domain medical
    python -m src.main ask    --domain financial --question "..."

`ingest` dispatches on FILE EXTENSION and tags with the DOMAIN you pass.
Those are two independent axes, which is the architectural claim this project
is making: the same tabular extractor serves financial and medical CSVs, and
domain is metadata supplied by the caller, never inferred from the data.

Both steps are re-runnable. Ingesting a second file adds to the domain rather
than replacing it — medical data arrives in pieces, not as one drop.

Until the domain router lands (Phase 5), `ask` requires --domain explicitly.
After it, --domain becomes an optional override of the router's decision.
"""
import argparse
import sys
from pathlib import Path

from src.agent import ask as agent_ask
from src.build_index import build_index, ensure_index
from src.extractors.tabular_extractor import extract_tabular
from src.extractors.text_extractor import extract_text
from src.schema import KnowledgeUnit
from src.unit_store import load_units, merge_units, units_path

DOMAINS = ("medical", "financial")

TABULAR_SUFFIXES = {".csv", ".xlsx", ".xls"}
TEXTUAL_SUFFIXES = {".docx"}


def extract_any(file_path: str, domain: str) -> list[KnowledgeUnit]:
    """Route one file to the right extractor based on its format.

    This is the only place format dispatch happens. Everything downstream
    sees KnowledgeUnits and cannot tell which branch produced them.
    """
    suffix = Path(file_path).suffix.lower()

    if suffix in TABULAR_SUFFIXES:
        return extract_tabular(file_path, domain=domain)

    if suffix in TEXTUAL_SUFFIXES:
        if domain != "medical":
            raise ValueError(
                f"The text extractor is tied to the medical domain, but "
                f"--domain {domain} was passed for {file_path}. DOCX ingestion "
                "for another domain would need its own extractor (the domain is "
                "hardcoded there deliberately — see AGENTS.md, Agent 5)."
            )
        return extract_text(file_path)

    supported = sorted(TABULAR_SUFFIXES | TEXTUAL_SUFFIXES)
    raise ValueError(f"Unsupported file type '{suffix}'. Supported: {', '.join(supported)}")


def cmd_ingest(args: argparse.Namespace) -> None:
    print(f"Extracting {args.data}  (domain={args.domain})")
    units = extract_any(args.data, args.domain)

    all_units, added, updated = merge_units(units, args.domain)
    print(f"\n{len(units)} units extracted from this file")
    print(f"  {added} new, {updated} updated in place")
    print(f"  Domain '{args.domain}' now holds {len(all_units)} units")
    print(f"  Saved to {units_path(args.domain)}")
    print(f"\nNext: python -m src.main index --domain {args.domain}")


def cmd_setup(args: argparse.Namespace) -> None:
    """Rebuild every index from the committed unit store. Zero API calls.

    This is what a fresh clone runs, and what the deployed API runs at startup:
    the index is not in version control (Chroma dirties its files on read), but
    the units it is built from are.
    """
    built = ensure_index(rebuild=args.rebuild)
    if not built:
        raise SystemExit(
            "No extracted units found. Run `ingest` first, or check that "
            "data/generated/ is present."
        )
    for domain, count in built.items():
        print(f"  {domain}: {count} units ready")
    print("\nReady. Try: python -m src.main ask --domain financial --question \"...\"")


def cmd_index(args: argparse.Namespace) -> None:
    units = load_units(args.domain)
    if not units:
        raise SystemExit(
            f"No extracted units for domain '{args.domain}'. "
            f"Run `python -m src.main ingest --data <file> --domain {args.domain}` first."
        )
    build_index(units, args.domain)


def cmd_ask(args: argparse.Namespace) -> None:
    trace = agent_ask(args.question, args.domain)

    print(f"\nroute    {trace.routing.domain}  ({trace.routing.method})")
    print(f"plan     {len(trace.planning.subqueries)} sub-quer"
          f"{'y' if len(trace.planning.subqueries) == 1 else 'ies'}")
    for sq in trace.planning.subqueries:
        print(f"           - {sq}")
    print(f"retrieve {len(trace.retrieval.sources)} of "
          f"{trace.retrieval.n_candidates} candidates")
    for source in trace.retrieval.sources:
        print(f"           [S{source.rank}] {source.id}  (rrf {source.score})")

    print("\n" + "=" * 68)
    print(trace.synthesis.answer)
    print("=" * 68)

    unresolved = trace.synthesis.unresolved_citations
    if unresolved:
        # The model cited a source number it was never given — a hallucination
        # signal that costs nothing to detect.
        print(f"WARNING  answer cites {', '.join(unresolved)}, which "
              f"{'was' if len(unresolved) == 1 else 'were'} never supplied")

    print(trace.summary())
    print(f"trace    {trace.trace_id} -> logs/traces.jsonl")


def main() -> None:
    # Windows consoles default to cp1252, which cannot encode the typographic
    # characters LLMs emit constantly (em dashes, non-breaking hyphens, curly
    # quotes). Without this, a perfectly good answer crashes on print().
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="PRISM — agentic RAG pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Extract a file into KnowledgeUnits")
    p_ingest.add_argument("--data", required=True, help="Path to a .csv, .xlsx or .docx file")
    p_ingest.add_argument("--domain", required=True, choices=DOMAINS)
    p_ingest.set_defaults(func=cmd_ingest)

    p_setup = sub.add_parser(
        "setup", help="Rebuild all indexes from the committed units (no API calls)"
    )
    p_setup.add_argument("--rebuild", action="store_true",
                         help="Rebuild even if an index already exists")
    p_setup.set_defaults(func=cmd_setup)

    p_index = sub.add_parser("index", help="Build the hybrid index for one domain")
    p_index.add_argument("--domain", required=True, choices=DOMAINS)
    p_index.set_defaults(func=cmd_index)

    p_ask = sub.add_parser("ask", help="Ask a question against one domain")
    p_ask.add_argument("--domain", required=True, choices=DOMAINS)
    p_ask.add_argument("--question", required=True)
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
