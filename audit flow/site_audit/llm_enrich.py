# D:\tintashProject\site_audit\llm_enrich.py
import os, json, time, requests, re, hashlib
from typing import List, Dict, Any, Optional

# Defaults point at your LM Studio local server.
# You can still override with --llm-base-url / --llm-model / --llm-api-key.
DEF_BASE   = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
DEF_MODEL  = os.getenv("LLM_MODEL", "llama-3.2-3b-instruct")
DEF_KEY    = os.getenv("LLM_API_KEY", None)
CACHE_PATH = os.getenv("LLM_CACHE", "report/llm_cache.jsonl")


def _clip(s: Any, n=400) -> str:
    t = str(s or "")
    return t if len(t) <= n else t[:n] + " …"


def _prompt(row: Dict[str, Any]) -> str:
    """
    Per-row prompt we send to the model.
    We include key context so the model can explain root cause + fix.
    """
    return (
        "You are a senior web performance & accessibility engineer.\n"
        "Given one Lighthouse finding, return ONLY JSON with keys "
        '{"root_cause":"...","recommendation":"..."}.\n'
        "Be specific, reference WCAG 2.1 AA correctly when relevant, "
        "and do not invent fake metrics or section numbers.\n\n"
        f"Finding:\n"
        f"page_url: {_clip(row.get('Page URL'), 200)}\n"
        f"category: {_clip(row.get('Category'), 120)}\n"
        f"rule_id: {_clip(row.get('Rule ID'), 120)}\n"
        f"title: {_clip(row.get('Title'), 220)}\n"
        f"example: {_clip(row.get('Example'), 400)}\n"
        f"severity: {_clip(row.get('Severity'), 40)}\n"
        f"LCP: {row.get('LCP')} | CLS: {row.get('CLS')} | TTI: {row.get('TTI')}\n"
    )


def _headers(api_key: Optional[str]):
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _json_from_content(content: str) -> Dict[str, Any]:
    """
    Try to parse JSON. If model babbles around it, grab the first {...} block.
    We keep it non-greedy so we don't swallow trailing junk.
    """
    try:
        return json.loads(content)
    except Exception:
        m = re.search(r"\{.*?\}", content, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"root_cause": "", "recommendation": ""}


def _call_openai_compatible(
    prompt: str,
    base_url: str,
    model: str,
    api_key: Optional[str],
    temperature=0,
    max_tokens=200,
):
    """
    Try structured JSON first (response_format). If server doesn't support it,
    fall back to a hard 'ONLY JSON' instruction.
    """

    url = base_url.rstrip("/") + "/chat/completions"

    policy_msg = (
        "You output ONLY compact JSON like "
        "{\"root_cause\":\"...\",\"recommendation\":\"...\"} "
        "No prose before or after. No code blocks. No ```.\n"
        "\n"
        "Guidance for correctness:\n"
        "- LCP: Say that LCP above ~2.5 seconds on mobile hurts perceived load speed. "
        "Causes: large hero image, render-blocking CSS/JS, slow server response. "
        "Fixes: compress/resize hero image, inline critical CSS, defer non-critical JS, use caching/CDN. "
        "Do not tell them to 'use a faster network connection'. Do not claim WCAG sets an exact LCP time limit.\n"
        "- CLS: Say layout shifts because elements load without reserved space. "
        "Fixes: reserve width/height or aspect-ratio boxes for images/ads/embeds, avoid injecting banners above existing content. "
        "Do NOT frame CLS as an accessibility/visual impairment issue.\n"
        "- Color contrast: Refer to WCAG 2.1 AA Success Criterion 1.4.3 Contrast (Minimum). "
        "Say text should have at least 4.5:1 contrast for normal text, 3:1 for large text. "
        "Do NOT invent fake WCAG section numbers like '4.5.3' or '1.4.3.3'.\n"
        "- Alt text: If missing alt, say 'Add meaningful alt text for informative images, and empty alt (alt=\"\") for decorative images.'\n"
        "- Keep it practical, not legal.\n"
    )

    # Attempt 1: ask for structured json via response_format (if the server supports it)
    schema_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": policy_msg,
            },
            {
                "role": "user",
                "content": (
                    prompt
                    + "\nRespond ONLY as one JSON object with keys "
                    '{"root_cause":"...","recommendation":"..."}'
                ),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "lh_finding",
                "schema": {
                    "type": "object",
                    "properties": {
                        "root_cause": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["root_cause", "recommendation"],
                    "additionalProperties": False,
                },
            },
        },
    }

    # Attempt 2: fallback plain body with stop tokens to discourage ``` blocks
    text_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": policy_msg,
            },
            {
                "role": "user",
                "content": (
                    prompt
                    + "\nRespond ONLY as one JSON object with keys "
                    '{"root_cause":"...","recommendation":"..."} '
                    "Do not include backticks. Do not include code fences. "
                    "Do not explain yourself."
                ),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stop": ["```", "\n```"],
    }

    last_err = ""

    # Try schema-style first
    try:
        r = requests.post(url, headers=_headers(api_key), json=schema_body, timeout=45)
        r.raise_for_status()
        resp_json = r.json()
        content = resp_json["choices"][0]["message"]["content"]
        return _json_from_content(content)
    except Exception as e:
        last_err = str(e)

    # Fallback plain style
    try:
        r = requests.post(url, headers=_headers(api_key), json=text_body, timeout=45)
        r.raise_for_status()
        resp_json = r.json()
        raw_content = resp_json["choices"][0]["message"]["content"]

        # Some servers might return list chunks
        if isinstance(raw_content, list):
            chunks = []
            for ch in raw_content:
                if isinstance(ch, dict) and "text" in ch:
                    chunks.append(ch["text"])
                elif isinstance(ch, str):
                    chunks.append(ch)
            content = "\n".join(chunks)
        else:
            content = raw_content

        return _json_from_content(content)
    except Exception as e:
        last_err = str(e)

    # If both attempts fail
    return {"root_cause": "", "recommendation": "", "_error": last_err}


def _key(row: Dict[str, Any]) -> str:
    """
    Hash identifying columns so we can reuse the same
    explanation next run without re-calling the model.
    """
    sig = "|".join(
        str(row.get(k, "")) for k in ("Page URL", "Rule ID", "Title", "Example", "Severity")
    )
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


def _load_cache(path: str) -> Dict[str, Dict[str, Any]]:
    d: Dict[str, Dict[str, Any]] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    d[obj["k"]] = obj["v"]
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return d


def _append_cache(path: str, k: str, v: Dict[str, Any]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")


def enrich_rows_llm(
    rows: List[Dict[str, Any]],
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    rate_limit_s: float = 0.25,
) -> List[Dict[str, Any]]:

    base_url = base_url or DEF_BASE
    model    = model    or DEF_MODEL
    api_key  = api_key  or DEF_KEY

    # allow no API key only if local
    is_local = base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1")
    if not api_key and not is_local:
        # hosted model with no key: skip
        for r in rows:
            r.setdefault("Root Cause", "")
            r.setdefault("Recommendation", "")
        return rows

    cache = _load_cache(CACHE_PATH)
    out: List[Dict[str, Any]] = []

    for r in rows:
        k = _key(r)

        # 1. if we already cached something, reuse it
        if k in cache:
            got = cache[k]
            r["Root Cause"] = got.get("root_cause", "")
            r["Recommendation"] = got.get("recommendation", "")
            out.append(r)
            continue

        # 2. call local model
        resp = _call_openai_compatible(
            _prompt(r),
            base_url,
            model,
            api_key,
            temperature=0,
            max_tokens=200,
        )

        root = str(resp.get("root_cause", "") or "").strip()
        rec  = str(resp.get("recommendation", "") or "").strip()

        # 3. sanitize obvious junk

        # drop any code fences / ``` leftovers
        for bad in ("```", "```python", "```json", "```js"):
            root = root.replace(bad, "")
            rec  = rec.replace(bad, "")

        # collapse accidental repeats like "2.1 AA 2.1 AA"
        root = re.sub(r"(2\.1 AA\s+)\1+", r"\1", root)
        rec  = re.sub(r"(2\.1 AA\s+)\1+", r"\1", rec)

        rid = str(r.get("Rule ID", "")).lower()

        # ---------- COLOR CONTRAST CLEANUP ----------
        if "color" in rid or "contrast" in rid:
            # normalize ratio phrasing
            root = root.replace("1.4.3:1", "4.5:1")
            rec  = rec.replace("1.4.3:1", "4.5:1")

            # force correct WCAG story if it's talking about contrast
            if "contrast" in root.lower() and "4.5:1" not in root:
                root += (
                    " Text contrast should be at least 4.5:1 for normal text "
                    "(WCAG 2.1 AA 1.4.3)."
                )
            if "contrast" in rec.lower() and "4.5:1" not in rec:
                rec += (
                    " Aim for at least 4.5:1 contrast for normal text "
                    "(WCAG 2.1 AA 1.4.3)."
                )

            # kill fake section numbers like '1.4.3.3'
            root = re.sub(r"1\.4\.3(\.\d+)+", "1.4.3", root)
            rec  = re.sub(r"1\.4\.3(\.\d+)+", "1.4.3", rec)

        # ---------- CLS CLEANUP ----------
        if rid == "cumulative-layout-shift":
            # Rewrite root to talk about layout jumps and reserved space.
            # If it mentioned accessibility, hero image causes CLS, visual impairment, etc,
            # we still normalize it to the stable CLS story.
            if (
                "accessib" in root.lower()
                or "visual" in root.lower()
                or "hero image" in root.lower()
                or "cumulative layout shift" in root.lower()
                or "cls" in root.lower()
                or "shift" in root.lower()
            ):
                root = (
                    "Layout is jumping during load (high CLS). Elements like images, ads, "
                    "or banners are loading without reserved space, so content moves after "
                    "first paint."
                )

            if (
                "accessib" in rec.lower()
                or "visual" in rec.lower()
                or "hero image" in rec.lower()
                or "shift" in rec.lower()
                or "cls" in rec.lower()
            ):
                rec = (
                    "Reserve explicit width/height or aspect-ratio boxes for images/ads/"
                    "embeds, and avoid injecting banners above existing content so the "
                    "page stays stable."
                )

        # ---------- LCP CLEANUP ----------
        if rid == "largest-contentful-paint":
            # Rewrite bad advice like 'use a faster network connection'.
            if "faster network" in root.lower():
                root = (
                    "Largest Contentful Paint (LCP) is above ~2.5s on mobile. Likely "
                    "causes: large hero image, render-blocking CSS/JS, or slow initial "
                    "server response."
                )
            if "faster network" in rec.lower():
                rec = (
                    "Compress/resize hero images, inline critical CSS, defer non-critical "
                    "JS, and enable caching/CDN to get LCP under ~2.5s on mobile."
                )

            # Kill fake 'WCAG says 1.3s' style claims. WCAG does not define an LCP time limit.
            if ("wcag" in root.lower() and "1.3" in root) or "wcag" in root.lower():
                root = (
                    "Largest Contentful Paint (LCP) is slower than target (~2.5s on mobile). "
                    "Heavy hero media or render-blocking resources are delaying first "
                    "meaningful paint."
                )
            if ("wcag" in rec.lower() and "1.3" in rec) or "wcag" in rec.lower():
                rec = (
                    "Compress/resize the main hero image (aim for a lightweight hero, "
                    "~100KB or less), inline critical CSS, defer non-critical JS, and use "
                    "CDN caching so above-the-fold content renders sooner."
                )

        # 4. stick sanitized text back on the row
        r["Root Cause"] = root
        r["Recommendation"] = rec

        # 5. write to cache
        _append_cache(
            CACHE_PATH,
            k,
            {"root_cause": root, "recommendation": rec},
        )

        out.append(r)

        # 6. throttle between calls so we don't hammer LM Studio
        if rate_limit_s:
            time.sleep(rate_limit_s)

    return out


   
