# D:\tintashProject\site_audit\cli.py
import argparse, os, sys, json
from pathlib import Path

from site_audit.crawl import crawl_same_origin
from site_audit.lighthouse_runner import run_lighthouse_json
from site_audit.parse import rows_from_lhr
from site_audit.severity import SeverityMapper
from site_audit.write_out import write_csvs
try:
    from site_audit.write_out import write_xlsx
except Exception:
    write_xlsx = None

from site_audit.llm_enrich import enrich_rows_llm
try:
    from site_audit.template_enrich import enrich_rows_template
except Exception:
    def enrich_rows_template(rows): return rows  # fallback no-op

SEV_RANK = {"low": 0, "medium": 1, "critical": 2}


def main():
    ap = argparse.ArgumentParser("site-audit")

    ap.add_argument("--start", help="Start URL (same-origin crawl). If omitted, program will prompt.")
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--device", choices=["mobile","desktop"], default="mobile")
    ap.add_argument("--out", default="report")
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--chrome-path", default=None)
    ap.add_argument("--also-html", action="store_true",
                    help="Also save Lighthouse HTML (near JSON).")

    # filtering / enrichment strategy
    ap.add_argument("--only-failing", action="store_true",
                    help="Drop rows graded 'low' after severity mapping "
                         "(keep only medium/critical).")
    ap.add_argument("--enrich-mode", choices=["template","llm","hybrid"], default="hybrid",
                    help="template = fast rule text only; "
                         "llm = call LLM only; "
                         "hybrid = template first, then LLM fills blanks.")

    # LLM controls
    ap.add_argument("--llm", action="store_true",
                    help="Allow LLM calls at all (ignored if not set).")
    ap.add_argument("--llm-base-url", default=None)
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("--llm-api-key", default=None)
    ap.add_argument("--llm-rate", type=float, default=0.4,
                    help="Seconds between LLM calls.")
    ap.add_argument("--llm-min-severity", choices=["low","medium","critical"], default="medium",
                    help="Only enrich rows at or above this severity.")
    ap.add_argument("--llm-top", type=int, default=50,
                    help="Max rows per page to consider (after filtering).")
    ap.add_argument("--llm-mode", choices=["row","rule"], default="row",
                    help="row = call LLM per row; "
                         "rule = de-dup by Rule ID so we call at most once per rule.")
    ap.add_argument("--llm-max-calls", type=int, default=0,
                    help="Hard cap on number of LLM calls per page (0 = unlimited).")

    ap.add_argument("--xlsx", action="store_true",
                    help="Also write workbook.xlsx")

    args = ap.parse_args()

    start = args.start or input("Start URL: ").strip()

    out_dir = Path(args.out)
    (out_dir / "raw_json").mkdir(parents=True, exist_ok=True)
    (out_dir / "pages").mkdir(parents=True, exist_ok=True)

    log = print if args.verbose else (lambda *_, **__: None)

    # 1. crawl
    log("[1/5] Crawling …")
    urls = crawl_same_origin(start, args.max_pages, timeout=args.timeout, log=log)
    (out_dir / "urls.txt").write_text("\n".join(urls), encoding="utf-8")
    print(f"Found {len(urls)} pages → {out_dir/'urls.txt'}")

    # 2. lighthouse
    log("[2/5] Lighthouse per page …")
    raw_json_dir = out_dir / "raw_json"
    json_files = []
    for i, u in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] LH: {u}")
        jf = run_lighthouse_json(
            u,
            raw_json_dir,
            device=args.device,
            quiet=not args.verbose,
            chrome_path=args.chrome_path,
            also_html=args.also_html,
        )
        json_files.append(jf)

    # 3. parse + severity
    log("[3/5] Parse + severity …")

    # project root (tintashProject)
    PKG_ROOT = Path(__file__).resolve().parents[1]
    RULES_PATH = PKG_ROOT / "config" / "rules.yaml"
    mapper = SeverityMapper.from_yaml(str(RULES_PATH))

    all_pages = {}

    for jf in sorted(json_files):
        p = Path(jf)
        if not p.exists():
            continue
        try:
            lhr = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        rows = rows_from_lhr(lhr)

        # assign severity for each row
        for r in rows:
            r["Severity"] = mapper.grade(r, lhr.get("audits", {}))

        # filter to only medium/critical if requested
        if args.only_failing:
            rows = [
                r for r in rows
                if str(r.get("Severity", "low")) in ("medium", "critical")
            ]

        if not rows:
            continue

        # 4a. template enrichment (fast, offline, deterministic)
        if args.enrich_mode in ("template", "hybrid"):
            rows = enrich_rows_template(rows)

        # 4b. LLM enrichment (either only-LLM or hybrid fallback)
        if args.llm and args.enrich_mode in ("llm", "hybrid"):
            min_rank = SEV_RANK[args.llm_min_severity]

            # pick rows that:
            # - meet severity threshold
            # - still missing Recommendation (template didn't fill)
            need = [
                r for r in rows
                if SEV_RANK.get(str(r.get("Severity", "low")), 0) >= min_rank
                and (not r.get("Recommendation"))
            ]

            # compress to unique Rule ID if --llm-mode rule
            if args.llm_mode == "rule":
                dedup = {}
                for r in need:
                    rid = str(r.get("Rule ID", ""))
                    if rid and rid not in dedup:
                        dedup[rid] = r
                need = list(dedup.values())

            # apply per-page caps
            if args.llm_top and args.llm_top > 0:
                need = need[: args.llm_top]
            if args.llm_max_calls and args.llm_max_calls > 0:
                need = need[: args.llm_max_calls]

            if need:
                enriched = enrich_rows_llm(
                    need,
                    base_url=args.llm_base_url,
                    model=args.llm_model,
                    api_key=args.llm_api_key,
                    rate_limit_s=args.llm_rate,
                )

                # Broadcast enriched answers to all matching rows
                by_exact = {}
                by_rule  = {}
                for idx, row_obj in enumerate(rows):
                    exact_key = (
                        row_obj.get("Page URL",""),
                        row_obj.get("Rule ID",""),
                        row_obj.get("Title",""),
                        row_obj.get("Example",""),
                        row_obj.get("Severity",""),
                    )
                    by_exact[exact_key] = idx

                    rule_key = (
                        row_obj.get("Page URL",""),
                        row_obj.get("Rule ID",""),
                        row_obj.get("Severity",""),
                    )
                    by_rule.setdefault(rule_key, []).append(idx)

                for er in enriched:
                    exact_key = (
                        er.get("Page URL",""),
                        er.get("Rule ID",""),
                        er.get("Title",""),
                        er.get("Example",""),
                        er.get("Severity",""),
                    )

                    targets = []
                    if exact_key in by_exact:
                        targets.append(by_exact[exact_key])

                    if args.llm_mode == "rule":
                        rule_key = (
                            er.get("Page URL",""),
                            er.get("Rule ID",""),
                            er.get("Severity",""),
                        )
                        targets.extend(by_rule.get(rule_key, []))

                    for idx in set(targets):
                        if not rows[idx].get("Root Cause"):
                            rows[idx]["Root Cause"] = er.get("Root Cause", "")
                        if not rows[idx].get("Recommendation"):
                            rows[idx]["Recommendation"] = er.get("Recommendation", "")

        # 5. collect rows for this page
        page_url = rows[0].get("Page URL", "UNKNOWN_PAGE")
        all_pages.setdefault(page_url, []).extend(rows)

    # Final write-out
    print(f"[5/5] Writing outputs → {out_dir}")
    write_csvs(all_pages, out_dir)
    if args.xlsx and write_xlsx:
        write_xlsx(all_pages, out_dir / "workbook.xlsx")
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
