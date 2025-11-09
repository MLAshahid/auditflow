#D:\tintashProject\site_audit\severity.py

import yaml

def _parse_threshold(expr):
    # supports ">=4000", ">=0.25", or plain numbers
    if isinstance(expr, str) and expr.startswith(">="):
        return float(expr[2:])
    return float(expr)

def _grade_threshold(v, crit_expr, med_expr, default_level):
    if v is None:
        return default_level
    crit_v = _parse_threshold(crit_expr)
    med_v  = _parse_threshold(med_expr)
    if v >= crit_v:
        return "critical"
    if v >= med_v:
        return "medium"
    return "low"

class SeverityMapper:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.rules = (self.cfg.get("rules") or {})
        self.default = (self.cfg.get("defaults") or "low")

    @classmethod
    def from_yaml(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def grade(self, row, audits):
        aid = row["Rule ID"]
        rule = self.rules.get(aid)
        if not rule:
            return self.default

        # numeric thresholds
        if "crit" in rule or "med" in rule:
            if aid == "largest-contentful-paint":
                v = audits.get("largest-contentful-paint", {}).get("numericValue")
                return _grade_threshold(v, rule.get("crit"), rule.get("med"), self.default)

            if aid == "cumulative-layout-shift":
                v = audits.get("cumulative-layout-shift", {}).get("numericValue")
                return _grade_threshold(v, rule.get("crit"), rule.get("med"), self.default)

            # future:
            # if aid == "interactive":
            #     v = audits.get("interactive", {}).get("numericValue")
            #     return _grade_threshold(v, rule.get("crit"), rule.get("med"), self.default)

        # boolean rules
        if isinstance(rule, dict) and rule.get("crit") is True:
            return "critical"
        if isinstance(rule, dict) and rule.get("med") is True:
            return "medium"
        if rule is True:
            return "medium"

        return self.default
