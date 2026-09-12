from bim_evidence_qa.evaluation.external import (
    choose_language_cases,
    normalize_length,
    score_numeric,
)


def test_numeric_scoring_requires_an_explicit_convertible_unit():
    expected = {"value": 1.0, "unit": "m", "absolute_tolerance": 0.001}

    assert score_numeric(1000, "mm", expected)["correct"] is True
    assert score_numeric(1.0, None, expected) == {
        "expected_value": 1.0,
        "expected_unit": "m",
        "actual_value": 1.0,
        "actual_unit": None,
        "normalized_expected_m": 1.0,
        "normalized_actual_m": None,
        "value_correct": False,
        "unit_correct": False,
        "correct": False,
    }


def test_length_normalization_does_not_guess_unknown_units():
    assert normalize_length(3.28084, "ft") == 1.000000032
    assert normalize_length(1, "m²") is None
    assert normalize_length("1", "m") is None


def test_language_subset_is_seeded_and_capped_at_ten():
    cases = [
        {"benchmark_id": str(index), "expected_support_status": "supported"}
        for index in range(1, 17)
    ]
    cases.append({"benchmark_id": "99", "expected_support_status": "unsupported"})

    selected = choose_language_cases(cases)

    assert selected == choose_language_cases(cases)
    assert len(selected) == 10
    assert set(selected).issubset({str(index) for index in range(1, 17)})
