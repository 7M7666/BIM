import argparse
import json
from pathlib import Path
from typing import Sequence

from bim_evidence_qa.evaluation.development_cases import DEVELOPMENT_CASES
from bim_evidence_qa.evaluation.runner import EvaluationRunner, format_evaluation_report
from bim_evidence_qa.parsers import SyntheticFixtureParser
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "synthetic_project.json"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the development-only BIM QA evaluation harness."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args(argv)

    dataset = SyntheticFixtureParser().parse(arguments.fixture)
    report = EvaluationRunner(DevelopmentNaturalLanguagePlanner()).run(
        dataset,
        DEVELOPMENT_CASES,
    )
    if arguments.as_json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_evaluation_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
