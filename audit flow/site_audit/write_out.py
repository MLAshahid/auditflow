#D:\tintashProject\site_audit\write_out.py
import pandas as pd
import re
from pathlib import Path

def _sheet_name_from_url(url: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", url.split("://",1)[-1])
    return s[:31] or "home"

def write_csvs(all_pages: dict, out_dir: Path | str):
    out_dir = Path(out_dir)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for url, rows in all_pages.items():
        df = pd.DataFrame(rows)
        df.to_csv(pages_dir / f"{_sheet_name_from_url(url)}.csv", index=False)

        lcp = pd.to_numeric(df.get("LCP"), errors="coerce").mean()
        cls = pd.to_numeric(df.get("CLS"), errors="coerce").mean()
        tti = pd.to_numeric(df.get("TTI"), errors="coerce").mean()
        sev = df.get("Severity")
        summary_rows.append({
            "Page": url,
            "Critical": int((sev == "critical").sum()) if sev is not None else 0,
            "Medium":  int((sev == "medium").sum()) if sev is not None else 0,
            "Low":     int((sev == "low").sum()) if sev is not None else 0,
            "Avg LCP": lcp,
            "Avg CLS": cls,
            "Avg TTI": tti,
        })
    pd.DataFrame(summary_rows).to_csv(out_dir / "summary.csv", index=False)

def write_xlsx(all_pages: dict, xlsx_path: Path | str):
    xlsx_path = Path(xlsx_path)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xl:
        # one sheet per page
        for url, rows in all_pages.items():
            pd.DataFrame(rows).to_excel(xl, index=False, sheet_name=_sheet_name_from_url(url))
        # summary
        srows = []
        for url, rows in all_pages.items():
            df = pd.DataFrame(rows)
            sev = df.get("Severity")
            srows.append({
                "Page": url,
                "Critical": int((sev == "critical").sum()) if sev is not None else 0,
                "Medium":  int((sev == "medium").sum()) if sev is not None else 0,
                "Low":     int((sev == "low").sum()) if sev is not None else 0,
                "Avg LCP": pd.to_numeric(df.get("LCP"), errors="coerce").mean(),
                "Avg CLS": pd.to_numeric(df.get("CLS"), errors="coerce").mean(),
                "Avg TTI": pd.to_numeric(df.get("TTI"), errors="coerce").mean(),
            })
        pd.DataFrame(srows).to_excel(xl, index=False, sheet_name="summary")
