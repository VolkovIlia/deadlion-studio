"""Preserve witnesses and merge corroboration only at a known source range."""
from pathlib import Path


def aggregate(findings):
    reports = []
    by_problem = {}
    for finding in findings:
        source = finding.get("source", "native")
        region = finding.get("range")
        evidence = dict(source=source, rule=finding["rule"], explanation=finding["explanation"])
        # An identical rule family or message at an exact range can corroborate
        # another observation. A line number alone cannot identify an expression.
        location = (str(Path(finding["file"]).resolve()), tuple(sorted(region.items()))) if region else None
        keys = [(location, kind, finding[kind]) for kind in ("rule", "explanation")] if location else []
        item = next((by_problem[k] for k in keys if k in by_problem), None)
        if item is None:
            item = dict(finding, provenance=[], category="performance",
                        evidenceLevel=finding["confidence"] if finding["confidence"] in
                        {"STATICALLY BOUNDED", "INCONCLUSIVE"} else "HEURISTIC")
            reports.append(item)
        if evidence not in item["provenance"]:
            item["provenance"].append(evidence)
        for key in keys:
            by_problem[key] = item
    return reports
