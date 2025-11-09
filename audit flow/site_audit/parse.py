#D:\tintashProject\site_audit\parse.py

def _metric(audits, key):
    a = audits.get(key, {})
    return a.get("numericValue")

def rows_from_lhr(lhr: dict):
    url = lhr.get("finalUrl","")
    audits = lhr.get("audits", {})
    rows = []
    for aid, a in audits.items():
        title = a.get("title")
        if not title:
            continue

        score = a.get("score")
        # skip clean passes
        if score is not None and score >= 1:
            continue

        details = a.get("details") or {}
        items = details.get("items") if isinstance(details.get("items"), list) else []
        example = ""
        if items:
            x = items[0]
            example = (x.get("node") or {}).get("snippet") or x.get("source") or ""

        rows.append({
            "Page URL": url,
            "Category": a.get("group") or "",
            "Rule ID": aid,
            "Title": title,
            "Example": example,
            "LCP": _metric(audits, "largest-contentful-paint"),
            "CLS": _metric(audits, "cumulative-layout-shift"),
            "TTI": _metric(audits, "interactive"),
            "LH Score": score,
        })
    return rows
