# D:\tintashProject\site_audit\lighthouse_runner.py
import subprocess, shutil, re, os
from pathlib import Path

def _slug(url: str) -> str:
    s = re.sub(r"^https?://", "", url)
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:120] or "home"

def _find(exe_names):
    # try PATH first
    for name in exe_names:
        p = shutil.which(name)
        if p:
            return p
    # common Windows npm global dir
    npm_roam = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Roaming", "npm")
    for name in exe_names:
        cand = os.path.join(npm_roam, name)
        if os.path.exists(cand):
            return cand
    return None

def _find_lighthouse():
    # allow explicit override
    env = os.getenv("LIGHTHOUSE_PATH")
    if env and os.path.exists(env):
        return env
    # Windows often has .CMD wrappers
    return _find(["lighthouse", "lighthouse.cmd", "lighthouse.exe"])

def _find_npx():
    env = os.getenv("NPX_PATH")
    if env and os.path.exists(env):
        return env
    return _find(["npx", "npx.cmd", "npx.exe"])

def run_lighthouse_json(url: str, out_dir: Path, device="mobile",
                        quiet=True, chrome_path=None, also_html=False) -> Path:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / _slug(url)  # LH will append .report.json / .report.html

    lh = _find_lighthouse()
    if lh:
        cmd = [lh, url]
    else:
        npx = _find_npx()
        if not npx:
            raise RuntimeError(
                "lighthouse CLI not found. Install with `npm i -g lighthouse`, "
                "ensure %USERPROFILE%\\AppData\\Roaming\\npm is on PATH, "
                "or set LIGHTHOUSE_PATH to lighthouse(.cmd)."
            )
        cmd = [npx, "lighthouse", url]

    outputs = ["--output=json"]
    if also_html:
        outputs += ["--output=html"]

    flags = [
        "--only-categories=performance,accessibility,seo,best-practices",
        *outputs,
        "--chrome-flags=--headless=new",
        "--enable-error-reporting=false",
        "--output-path", str(base),
    ]
    if device == "desktop":
        flags += ["--preset=desktop"]          # valid in LH 13
    else:
        flags += ["--form-factor=mobile"]      # mobile form-factor, no invalid 'preset=mobile'

    if chrome_path:
        flags += ["--chrome-path", chrome_path]
    if quiet:
        flags.append("--quiet")

    subprocess.run(
        cmd + flags,
        check=False,
        stdout=(subprocess.DEVNULL if quiet else None),
        stderr=(subprocess.DEVNULL if quiet else None),
    )
    # IMPORTANT: Lighthouse writes "<base>.report.json", not by replacing extension.
    return Path(str(base) + ".report.json")
