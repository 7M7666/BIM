from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingEntity,
    QueryOperation,
    QueryPlan,
    QueryResult,
)
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    QueryCatalog,
    QueryEngine,
)


def _run_question(question, synthetic_dataset):
    catalog = QueryCatalog.from_dataset(synthetic_dataset)
    plan = DevelopmentNaturalLanguagePlanner().plan(question, catalog)
    result = QueryEngine().execute(plan, synthetic_dataset)
    answer = AnswerBuilder().build(plan, result)
    return plan, result, answer


def test_find_answer_carries_original_global_id(synthetic_dataset):
    _, _, answer = _run_question("Find Room 101", synthetic_dataset)

    assert answer.status == "ok"
    assert answer.text == "Found Room 101."
    assert answer.evidence[0].global_id == "SYNTHETIC-SPACE-101"


def test_max_answer_carries_room_202_evidence(synthetic_dataset):
    _, _, answer = _run_question(
        "Which room has the largest area?", synthetic_dataset
    )

    assert answer.text == "Room 202 has the maximum area: 30.0."
    assert answer.value == 30.0
    assert answer.evidence[0].name == "Room 202"
    assert answer.evidence[0].global_id == "SYNTHETIC-SPACE-202"


def test_count_answer_value_is_query_result_value(synthetic_dataset):
    _, result, answer = _run_question(
        "How many rooms are there?", synthetic_dataset
    )

    assert answer.text == "There are 5 spaces."
    assert answer.value == result.value == 5
    assert len(answer.evidence) == 5


def test_average_answer_does_not_modify_value_or_add_unit(synthetic_dataset):
    _, result, answer = _run_question(
        "What is the average room area?", synthetic_dataset
    )

    assert answer.value == result.value == 21.0
    assert answer.text == "The average space area is 21.0."
    assert "m²" not in answer.text


def test_min_answer_uses_query_result(synthetic_dataset):
    _, result, answer = _run_question(
        "Which room has the smallest area?", synthetic_dataset
    )

    assert result.value == answer.value == 12.0
    assert answer.text == "Room 201 has the minimum area: 12.0."
    assert answer.evidence[0].global_id == "SYNTHETIC-SPACE-201"


def test_answer_builder_preserves_missing_global_id_and_warns():
    entity = BuildingEntity(
        entity_id="space-without-global-id",
        kind="space",
        name="Room Without ID",
        global_id=None,
    )
    plan = QueryPlan(operation=QueryOperation.FIND, name="Room Without ID")
    result = QueryResult(operation=QueryOperation.FIND, entities=(entity,))

    answer = AnswerBuilder().build(plan, result)

    assert answer.evidence[0].global_id is None
    assert answer.warnings == (
        "GlobalId unavailable for entity 'space-without-global-id'.",
    )


def test_answer_builder_does_not_generate_global_id():
    entity = BuildingEntity(entity_id="space-unknown", kind="space")
    plan = QueryPlan(operation=QueryOperation.FIND, kind="space")
    result = QueryResult(operation=QueryOperation.FIND, entities=(entity,))

    answer = AnswerBuilder().build(plan, result)

    assert answer.evidence[0].global_id is None


def test_full_question_to_grounded_answer_pipeline(synthetic_dataset):
    plan, result, answer = _run_question(
        "Which room has the largest area?", synthetic_dataset
    )

    assert plan.aggregate_function is AggregateFunction.MAX
    assert result.value == answer.value == 30.0
    assert answer.evidence[0].name == "Room 202"
    assert answer.evidence[0].global_id == result.entities[0].global_id
    assert answer.evidence[0].global_id == "SYNTHETIC-SPACE-202"


def test_bilingual_answers_preserve_values_and_provenance(synthetic_dataset):
    for question in ("How many rooms are there?", "Find Room 101", "Which room has the largest area?", "What is the average room area?"):
        plan, result, english = _run_question(question, synthetic_dataset)
        chinese = AnswerBuilder().build(plan, result, "zh")
        assert chinese.value == english.value
        assert chinese.evidence == english.evidence
        assert chinese.text != english.text
        assert any("\u4e00" <= c <= "\u9fff" for c in chinese.text)


def test_chinese_wall_and_door_templates():
    for kind, value, text in (("wall", 47, "这个建筑共有 47 面墙。"), ("door", 16, "这个建筑共有 16 扇门。")):
        plan = QueryPlan(QueryOperation.COUNT, kind=kind)
        result = QueryResult(QueryOperation.COUNT, (), value)
        assert AnswerBuilder().build(plan, result, "zh").text == text


def test_chinese_property_value_and_reference_level_diagnostic():
    from bim_evidence_qa.domain import PropertySource, PropertyValue
    prop = PropertyValue(PropertySource.QUANTITY, "Qto_BeamBaseQuantities", "Length", 4242.6, unit="mm")
    entity = BuildingEntity("internal-id", "beam", "Beam:1046268", "GLOBAL", properties=(prop,))
    plan = QueryPlan(QueryOperation.FIND, kind="beam", requested_property="length")
    result = QueryResult(QueryOperation.FIND, (entity,), 4242.6, ("Property-based level: Constraints.Reference Level eq 'Level 2'. This is not IfcBuildingStorey containment.",), (prop,))
    zh = AnswerBuilder().build(plan, result, "zh")
    en = AnswerBuilder().build(plan, result, "en")
    assert "长度为 4242.6 mm" in zh.text
    assert "按属性 Reference Level = Level 2" in zh.text
    assert "不是 IfcBuildingStorey" in zh.text
    assert zh.value == en.value and zh.evidence == en.evidence
    assert "4242.6 mm" in en.text
