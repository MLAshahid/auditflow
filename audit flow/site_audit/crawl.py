# D:\tintashProject\site_audit\crawl.py
import urllib.parse, requests
from collections import deque
from bs4 import BeautifulSoup

def _norm(u: str) -> str:
    """Normalize URL: keep scheme/host/path/query, drop fragment; ensure path present."""
    try:
        p = urllib.parse.urlsplit(u)
        path = p.path or "/"
        return urllib.parse.urlunsplit(
            (p.scheme, p.netloc.lower(), path, p.query, "")
        )  # strip fragment
    except Exception:
        return u

def _is_http(u: str) -> bool:
    s = urllib.parse.urlsplit(u).scheme.lower()
    return s in ("http", "https")

def _same_origin(a: str, b: str) -> bool:
    pa, pb = urllib.parse.urlsplit(a), urllib.parse.urlsplit(b)
    return (pa.scheme, pa.netloc.lower()) == (pb.scheme, pb.netloc.lower())

def _should_enqueue(href: str) -> bool:
    if not href:
        return False
    href = href.strip()
    bad_prefixes = ("javascript:", "mailto:", "tel:", "data:", "#")
    return not any(href.lower().startswith(p) for p in bad_prefixes)

def crawl_same_origin(start, max_pages=25, timeout=25, log=lambda *a, **k: None):
    start = _norm(start)
    origin = start
    seen, q, out = set([start]), deque([start]), []

    sess = requests.Session()
    # Pretend to be Chrome so we don't get weird placeholder content
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    while q and len(out) < max_pages:
        u = q.popleft()

        # fetch page
        try:
            r = sess.get(u, timeout=timeout, allow_redirects=True)
            if r.status_code >= 400:
                log(f"skip {u} [{r.status_code}]")
                continue

            ctype = r.headers.get("Content-Type", "").lower()
            if "text/html" not in ctype:
                log(f"skip non-HTML {u} [{ctype}]")
                continue

            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            log(f"error {u}: {e}")
            continue

        # if we reach here, it's a valid HTML page we actually saw
        out.append(u)

        # discover links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not _should_enqueue(href):
                continue

            nu = urllib.parse.urljoin(u, href)
            if not _is_http(nu):
                continue

            nu = _norm(nu)

            if _same_origin(nu, origin) and nu not in seen:
                seen.add(nu)
                q.append(nu)

    return out
