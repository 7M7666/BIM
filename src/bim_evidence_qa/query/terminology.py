"""Controlled terminology normalization; no values or IFC field selection."""

import re


ENTITY_ALIASES = {
    "横梁": "beam", "梁": "beam", "柱子": "column", "柱": "column",
    "楼板": "slab", "板": "slab", "基础构件": "footing", "基础": "footing",
    "桩基": "pile", "桩": "pile", "门": "door", "窗户": "window", "窗": "window",
    "墙体": "wall", "墙": "wall", "房间": "space", "空间": "space",
    "楼层": "storey", "层": "storey",
}
PROPERTY_ALIASES = {
    "长度": "length", "多长": "length", "宽度": "width", "多宽": "width",
    "高度": "height", "多高": "height", "面积": "area", "多大": "area",
    "体积": "volume", "属性": "properties", "参数": "properties",
}
OPERATION_ALIASES = {
    "平均值": "average", "平均": "average", "最大的": "max", "最大": "max",
    "最小的": "min", "最小": "min", "显示所有": "list", "列出": "list",
    "哪些": "list", "多少": "count", "数量": "count", "有几": "count",
}
OVERVIEW_ALIASES = {
    "有什么": "overview", "有哪些": "overview", "包含": "overview",
    "包括": "overview", "概览": "overview", "构成": "overview",
}
IFC_KINDS = {
    "IfcBeam": "beam", "IfcColumn": "column", "IfcSlab": "slab", "IfcFooting": "footing",
    "IfcPile": "pile", "IfcDoor": "door", "IfcWindow": "window", "IfcWall": "wall",
    "IfcSpace": "space", "IfcBuildingStorey": "storey",
}
OVERVIEW_ENTITY_TERMS = {
    "room", "rooms", "space", "spaces", "door", "doors", "window", "windows",
    "wall", "walls", "beam", "beams", "column", "columns", "slab", "slabs",
    "footing", "footings", "pile", "piles", "storey", "storeys", "level", "levels",
    *ENTITY_ALIASES.values(), *IFC_KINDS.values(),
}


def normalize_question(question: str, names=()) -> str:
    # Protect literal object names so their Chinese words are not interpreted as intent.
    protected = {}
    for name in sorted(names, key=lambda n: (-len(n), n)):
        pattern = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])"
        if name and re.search(pattern, question, re.I):
            token = f"OBJECTTOKEN{len(protected)}"
            question = re.sub(pattern, lambda _: token, question, flags=re.I)
            protected[token] = name
    question = question.translate(str.maketrans({"？": "?", "。": ".", "：": ":", "＝": "="}))
    if re.fullmatch(r"\s*(?:(?:这个|这栋|该)?建筑)?(?:有)?(?:几层(?:楼)?|多少层(?:楼)?|多少楼层|多少楼)[?.!]?\s*", question):
        return "count storey"
    question = question.replace("参考楼层", " Reference Level ")
    question = re.sub(r"第?([一二12])层", lambda m: " Level " + {"一": "1", "二": "2"}.get(m[1], m[1]) + " ", question)
    reference = re.search(r"\breference\s+level\s*(?:=|为|是|is)?\s*(Level\s+\d+)\b", question, re.I)
    scope = None
    if reference:
        scope = " have Reference Level " + reference[1]
        question = question[:reference.start()] + " " + question[reference.end():]
    elif re.match(r"\s*Level\s+\d+\b", question, re.I):
        match = re.match(r"\s*(Level\s+\d+)\b", question, re.I)
        scope = " on " + match[1]
        question = question[match.end():]
    for alias, canonical in IFC_KINDS.items():
        question = re.sub(r"(?<![A-Za-z0-9_])" + alias + r"(?![A-Za-z0-9_])", canonical, question, flags=re.I)
    aliases = {
        **ENTITY_ALIASES,
        **PROPERTY_ALIASES,
        **OPERATION_ALIASES,
        **OVERVIEW_ALIASES,
    }
    pattern = "|".join(map(re.escape, sorted(aliases, key=len, reverse=True)))
    question = re.sub(pattern, lambda m: " " + aliases[m[0]] + " ", question)
    question = re.sub(r"这个|该对象|它", " unresolved_this ", question)
    question = re.sub(r"所有|请|显示|[有的是为在根个扇面块？]", " ", question)
    question = " ".join(question.split()).rstrip("?!")
    question = re.sub(r"\s+([.?!])", r"\1", question)
    if scope:
        question += scope
    # Controlled Chinese syntax may place the operation after the subject.
    words = question.split()
    if "list" in words and words[0] != "list":
        words.remove("list")
        question = "list " + " ".join(words)
    for token, name in protected.items():
        question = question.replace(token, name)
    return question


def is_overview_intent(question: str) -> bool:
    """Recognize a project-level inventory request without selecting an entity."""

    normalized = " ".join(question.casefold().split())
    tokens = set(re.findall(r"[a-z0-9_-]+", normalized))
    has_target = bool(
        tokens & {"building", "model", "project"}
        or any(marker in normalized for marker in ("建筑", "模型", "项目"))
    )
    if not has_target:
        return False

    specific_terms = {*OVERVIEW_ENTITY_TERMS, *PROPERTY_ALIASES.values()}
    if tokens & specific_terms:
        return False

    has_english_overview_cue = bool(
        tokens & {"contain", "contains", "include", "includes", "overview"}
        or ({"kind", "kinds"} & tokens and {"element", "elements", "component", "components"} & tokens)
    )
    return "overview" in tokens or has_english_overview_cue
