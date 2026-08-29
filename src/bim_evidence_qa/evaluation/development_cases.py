from bim_evidence_qa.domain import QueryOperation
from bim_evidence_qa.evaluation.schema import EvaluationCase


SPACE_IDS = ("space-101", "space-102", "space-201", "space-202", "space-203")
SPACE_GLOBAL_IDS = (
    "SYNTHETIC-SPACE-101",
    "SYNTHETIC-SPACE-102",
    "SYNTHETIC-SPACE-201",
    "SYNTHETIC-SPACE-202",
    "SYNTHETIC-SPACE-203",
)
DOOR_IDS = ("door-d101", "door-d102", "door-d201", "door-d202")
DOOR_GLOBAL_IDS = (
    "SYNTHETIC-DOOR-D101",
    "SYNTHETIC-DOOR-D102",
    "SYNTHETIC-DOOR-D201",
    "SYNTHETIC-DOOR-D202",
)
STOREY_IDS = ("storey-level-1", "storey-level-2")
STOREY_GLOBAL_IDS = ("SYNTHETIC-STOREY-L1", "SYNTHETIC-STOREY-L2")


DEVELOPMENT_CASES = (
    EvaluationCase("count-rooms-1", "How many rooms are there?", QueryOperation.COUNT, 5, SPACE_IDS, SPACE_GLOBAL_IDS, "count"),
    EvaluationCase("count-rooms-2", "Count the rooms in this building.", QueryOperation.COUNT, 5, SPACE_IDS, SPACE_GLOBAL_IDS, "count"),
    EvaluationCase("count-rooms-3", "What's the number of spaces?", QueryOperation.COUNT, 5, SPACE_IDS, SPACE_GLOBAL_IDS, "count"),
    EvaluationCase("count-doors-1", "How many doors are there?", QueryOperation.COUNT, 4, DOOR_IDS, DOOR_GLOBAL_IDS, "count"),
    EvaluationCase("count-doors-2", "Count all doors.", QueryOperation.COUNT, 4, DOOR_IDS, DOOR_GLOBAL_IDS, "count"),
    EvaluationCase("count-storeys-1", "How many levels are there?", QueryOperation.COUNT, 2, STOREY_IDS, STOREY_GLOBAL_IDS, "count"),
    EvaluationCase("count-storeys-2", "Count the storeys.", QueryOperation.COUNT, 2, STOREY_IDS, STOREY_GLOBAL_IDS, "count"),
    EvaluationCase("find-room-1", "Find Room 101.", QueryOperation.FIND, None, ("space-101",), ("SYNTHETIC-SPACE-101",), "find"),
    EvaluationCase("find-room-2", "Show me Room 101.", QueryOperation.FIND, None, ("space-101",), ("SYNTHETIC-SPACE-101",), "find"),
    EvaluationCase("find-room-3", "Locate Room 202.", QueryOperation.FIND, None, ("space-202",), ("SYNTHETIC-SPACE-202",), "find"),
    EvaluationCase("find-door-1", "Find Door D101.", QueryOperation.FIND, None, ("door-d101",), ("SYNTHETIC-DOOR-D101",), "find"),
    EvaluationCase("max-area-1", "Which room has the largest area?", QueryOperation.AGGREGATE, 30.0, ("space-202",), ("SYNTHETIC-SPACE-202",), "aggregate"),
    EvaluationCase("max-area-2", "What is the biggest room by area?", QueryOperation.AGGREGATE, 30.0, ("space-202",), ("SYNTHETIC-SPACE-202",), "aggregate"),
    EvaluationCase("min-area-1", "Which room has the smallest area?", QueryOperation.AGGREGATE, 12.0, ("space-201",), ("SYNTHETIC-SPACE-201",), "aggregate"),
    EvaluationCase("average-area-1", "What is the average room area?", QueryOperation.AGGREGATE, 21.0, SPACE_IDS, SPACE_GLOBAL_IDS, "aggregate"),
    EvaluationCase("deliberate-answer-failure", "How many spaces exist?", QueryOperation.COUNT, 999, SPACE_IDS, SPACE_GLOBAL_IDS, "deliberate_failure"),
    EvaluationCase("unsupported-color", "What color is Room 101?", None, None, (), (), "unsupported", True),
    EvaluationCase("unsupported-elevator", "How many elevators are there?", None, None, (), (), "unsupported", True),
    EvaluationCase("unsupported-relationship", "Which doors connect Room 101?", None, None, (), (), "unsupported", True),
    EvaluationCase("unsupported-adjacency", "Is Room 101 adjacent to Room 102?", None, None, (), (), "unsupported", True),
)
