#D:\tintashProject\site_audit\template_enrich.py
from __future__ import annotations
from typing import List, Dict, Any

# Prewritten guidance per Lighthouse audit rule.
# Short, practical, WCAG-aware, no hallucination.
TEMPLATES: Dict[str, Dict[str, str]] = {
    "largest-contentful-paint": {
        "root": "LCP is high ({LCP} ms). Likely causes: render-blocking CSS/JS, slow server, or oversized hero media.",
        "rec":  "Inline critical CSS, defer non-critical JS, preload hero media, compress/resize hero image, use CDN caching."
    },
    "cumulative-layout-shift": {
        "root": "CLS is high ({CLS}). Page elements shift after first paint.",
        "rec":  "Reserve fixed space for images/video (width/height or aspect-ratio), avoid injecting banners above existing content, use font-display: swap, stabilize ad slots."
    },
    "uses-text-compression": {
        "root": "Text assets are sent uncompressed.",
        "rec":  "Enable Brotli or Gzip for HTML/CSS/JS/JSON/SVG. Confirm 'content-encoding' headers and reduced transfer size."
    },
    "render-blocking-resources": {
        "root": "Blocking CSS/JS delays first render.",
        "rec":  "Inline critical CSS, mark non-critical JS as defer/async, split large CSS, and preload only truly critical styles."
    },
    "unminified-css": {
        "root": "CSS is shipped unminified.",
        "rec":  "Minify CSS during build and serve the minified bundle to users."
    },
    "unminified-javascript": {
        "root": "JavaScript is shipped unminified.",
        "rec":  "Minify or terser/uglify JS in build; avoid shipping dev/debug bundles to production."
    },
    "uses-passive-event-listeners": {
        "root": "Scroll/touch listeners block the main thread.",
        "rec":  "Mark non-critical listeners as { passive: true } to avoid scroll jank."
    },
    "tap-targets": {
        "root": "Touch targets are too small or too close on mobile.",
        "rec":  "Give interactive elements ~48x48 CSS px tap area with spacing. Increase padding/line-height for links and buttons."
    },
    "image-alt": {
        "root": "Images are missing alt text or have unhelpful alt text.",
        "rec":  "Provide concise, meaningful alt for informative images. Use empty alt (alt=\"\") for decorative images so screen readers skip them."
    },
    "color-contrast": {
        "root": "Text/background contrast is below WCAG targets.",
        "rec":  "Meet WCAG AA contrast: 4.5:1 for normal text, 3:1 for large text. Darken text or lighten background to raise contrast."
    },
    "meta-description": {
        "root": "Page is missing a unique meta description or it's too generic.",
        "rec":  "Add a 50–160 character <meta name=\"description\"> that clearly summarizes the page intent using real keywords."
    },
    "document-title": {
        "root": "The <title> is missing or not descriptive.",
        "rec":  "Give each page a unique, specific <title> where the main topic comes first for clarity and SEO."
    },
    "is-on-https": {
        "root": "Page is served over HTTP instead of HTTPS.",
        "rec":  "Serve all content over HTTPS. Force redirect HTTP→HTTPS and enable HSTS to prevent downgrade."
    },
    "uses-http2": {
        "root": "Static assets are not served over HTTP/2.",
        "rec":  "Enable HTTP/2 or HTTP/3 on your CDN/origin to get multiplexing and lower request overhead."
    },
}

class _Safe(dict):
    # lets .format_map(...) not explode if a key is missing
    def __missing__(self, key):
        return ""

def _fmt(t: str, row: Dict[str, Any]) -> str:
    return (t or "").format_map(_Safe({k: row.get(k, "") for k in row.keys()}))

def enrich_rows_template(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rid = str(r.get("Rule ID", "")).lower()
        tpl = TEMPLATES.get(rid)
        if tpl:
            r.setdefault("Root Cause", _fmt(tpl.get("root", ""), r))
            r.setdefault("Recommendation", _fmt(tpl.get("rec", ""), r))
        else:
            r.setdefault("Root Cause", "")
            r.setdefault("Recommendation", "")
        out.append(r)
    return out
