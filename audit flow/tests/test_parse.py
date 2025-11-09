import json
from pathlib import Path
from site_audit.parse import rows_from_lhr
from site_audit.severity import SeverityMapper

ROOT = Path(__file__).resolve().parents[1]
LHR = ROOT / "tests" / "data" / "sample_lhr.json"
RULES = ROOT / "config" / "rules.yaml"

def test_parse_and_severity():
    with LHR.open(encoding="utf-8") as f:
        lhr = json.load(f)
    rows = rows_from_lhr(lhr)
    assert any(r["Rule ID"] == "largest-contentful-paint" for r in rows)

    mapper = SeverityMapper.from_yaml(str(RULES))
    audits = lhr["audits"]

    lcp_row = [r for r in rows if r["Rule ID"] == "largest-contentful-paint"][0]
    assert mapper.grade(lcp_row, audits) == "critical"

    cls_row = [r for r in rows if r["Rule ID"] == "cumulative-layout-shift"][0]
    assert mapper.grade(cls_row, audits) == "critical"

    cc_row = [r for r in rows if r["Rule ID"] == "color-contrast"][0]
    assert mapper.grade(cc_row, audits) == "critical"

    md_row = [r for r in rows if r["Rule ID"] == "meta-description"][0]
    assert mapper.grade(md_row, audits) == "medium"
