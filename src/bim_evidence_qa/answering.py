import re
from dataclasses import dataclass

from bim_evidence_qa.domain import (
    AggregateFunction,
    QueryOperation,
    QueryPlan,
    QueryResult,
    ScalarValue,
    PropertyValue,
)


@dataclass(frozen=True, slots=True)
class EntityEvidence:
    entity_id: str
    kind: str
    name: str | None
    global_id: str | None
    properties: tuple[PropertyValue, ...] = ()


@dataclass(frozen=True, slots=True)
class Answer:
    status: str
    text: str
    value: ScalarValue
    evidence: tuple[EntityEvidence, ...]
    warnings: tuple[str, ...]


class AnswerBuilder:
    def build(self, plan: QueryPlan, result: QueryResult, locale: str = "en") -> Answer:
        if plan.operation is not result.operation:
            raise ValueError("QueryPlan and QueryResult operations do not match.")

        evidence = tuple(
            EntityEvidence(
                entity_id=entity.entity_id,
                kind=entity.kind,
                name=entity.name,
                global_id=entity.global_id,
                properties=result.properties if len(result.entities) == 1 else (),
            )
            for entity in result.entities
        )
        warnings = tuple(
            f"GlobalId unavailable for entity '{item.entity_id}'."
            for item in evidence
            if item.global_id is None
        )

        status, text = self._chinese_text(plan, result) if locale == "zh" else self._answer_text(plan, result)
        if result.diagnostics:
            text = " ".join((text, *(self._diagnostic_zh(d) if locale == "zh" else d for d in result.diagnostics)))
        return Answer(
            status=status,
            text=text,
            value=result.value,
            evidence=evidence,
            warnings=warnings,
        )

    def _answer_text(self, plan: QueryPlan, result: QueryResult) -> tuple[str, str]:
        if plan.requested_property is not None:
            entity = result.entities[0]
            if plan.requested_property == "properties":
                return "ok", f"Showing {len(result.properties)} scalar properties for {entity.name or entity.entity_id}."
            prop = result.properties[0]
            return "ok", (
                f"{entity.name or entity.entity_id}: {prop.path} = {prop.value} "
                f"{prop.unit or '(unit unavailable)'}."
            )
        if plan.operation is QueryOperation.COUNT:
            kind = plan.kind or "entity"
            return "ok", f"There are {result.value} {kind}s."

        if plan.operation is QueryOperation.OVERVIEW:
            labels = {
                "storey": "storeys", "space": "spaces", "door": "doors",
                "window": "windows", "wall": "walls", "beam": "beams",
                "column": "columns", "slab": "slabs", "footing": "footings",
                "pile": "piles",
            }
            summary = ", ".join(
                f"{count} {labels[kind]}"
                for kind, count in result.overview_counts.items()
            )
            return "ok", f"Project overview: {summary}."

        if plan.operation is QueryOperation.LOCATION:
            return "ok", self._location_text(plan, result, "en")

        if plan.operation is QueryOperation.FIND:
            if not result.entities:
                return "not_found", "No matching entities were found."
            if len(result.entities) == 1:
                name = result.entities[0].name or result.entities[0].entity_id
                return "ok", f"Found {name}."
            return "ok", f"Found {len(result.entities)} matching entities."

        if plan.operation is QueryOperation.FILTER:
            return "ok", f"Found {len(result.entities)} matching entities."

        if plan.operation is QueryOperation.AGGREGATE:
            assert plan.aggregate_function is not None
            assert plan.aggregate_field is not None
            kind = plan.kind or "entity"
            if plan.aggregate_function is AggregateFunction.AVERAGE:
                return (
                    "ok",
                    f"The average {kind} {plan.aggregate_field} is {result.value}.",
                )
            if plan.aggregate_function is AggregateFunction.SUM:
                return (
                    "ok",
                    f"The total {kind} {plan.aggregate_field} is {result.value}.",
                )

            function = (
                "maximum"
                if plan.aggregate_function is AggregateFunction.MAX
                else "minimum"
            )
            if len(result.entities) == 1:
                entity = result.entities[0]
                name = entity.name or entity.entity_id
                return (
                    "ok",
                    f"{name} has the {function} {plan.aggregate_field}: "
                    f"{result.value}.",
                )
            return (
                "ok",
                f"The {function} {kind} {plan.aggregate_field} is {result.value}.",
            )

        raise ValueError(f"Unsupported query operation: {plan.operation}")

    @staticmethod
    def _diagnostic_zh(message: str) -> str:
        if message.startswith("Property-based level:"):
            value = message.split("'", 2)[1]
            return f"按属性 Reference Level = {value} 筛选；这不是 IfcBuildingStorey 空间包含关系。"
        if message.startswith("Spatial containment:"):
            value = message.split("'", 2)[1]
            return f"按 IfcBuildingStorey 的实际空间包含关系筛选：{value}。"
        match = re.fullmatch(r"Showing (\d+) of (\d+) scalar properties; quantities first\.", message)
        if match:
            return f"共 {match[2]} 个属性，展示其中 {match[1]} 个，优先展示 Quantity。"
        return "部分数据说明请在开发模式查看。"

    def _chinese_text(self, plan: QueryPlan, result: QueryResult) -> tuple[str, str]:
        kinds = {"wall": "面墙", "door": "扇门", "window": "扇窗", "storey": "层楼", "space": "个房间", "beam": "根梁", "column": "根柱", "slab": "块楼板", "footing": "个基础", "pile": "根桩"}
        if plan.requested_property is not None:
            entity = result.entities[0]
            name = entity.name or entity.global_id or "该对象"
            if plan.requested_property == "properties":
                return "ok", f"已列出 {name} 的 {len(result.properties)} 个属性。"
            prop = result.properties[0]
            field = {"length": "长度", "width": "宽度", "height": "高度", "area": "面积", "volume": "体积"}.get(plan.requested_property, prop.path)
            return "ok", f"{name} 的{field}为 {prop.value} {prop.unit or '（单位不可用）'}。"
        if plan.operation is QueryOperation.COUNT:
            return "ok", f"{'符合条件的对象' if plan.filters else '这个建筑'}共有 {result.value} {kinds.get(plan.kind, '个对象')}。"
        if plan.operation is QueryOperation.OVERVIEW:
            labels = {
                "storey": "层楼", "space": "个房间", "door": "扇门",
                "window": "扇窗", "wall": "面墙", "beam": "根梁",
                "column": "根柱", "slab": "块楼板", "footing": "个基础",
                "pile": "根桩",
            }
            summary = "、".join(
                f"{count} {labels[kind]}"
                for kind, count in result.overview_counts.items()
            )
            return "ok", f"项目概览：{summary}。"
        if plan.operation is QueryOperation.LOCATION:
            return "ok", self._location_text(plan, result, "zh")
        if plan.operation in (QueryOperation.FIND, QueryOperation.FILTER):
            if not result.entities:
                return "not_found", "没有找到对应的 BIM 对象。"
            if len(result.entities) == 1:
                entity = result.entities[0]
                return "ok", f"已找到 {entity.name or entity.global_id or '对应对象'}。"
            return "ok", f"共找到 {len(result.entities)} 个符合条件的对象。"
        if plan.operation is QueryOperation.AGGREGATE:
            function = {
                AggregateFunction.AVERAGE: "平均值",
                AggregateFunction.MAX: "最大值",
                AggregateFunction.MIN: "最小值",
                AggregateFunction.SUM: "总和",
            }[plan.aggregate_function]
            field = {
                "area": "面积", "length": "长度", "width": "宽度",
                "height": "高度", "volume": "体积",
            }.get(plan.aggregate_field, plan.aggregate_field)
            return "ok", f"{field} 的{function}为 {result.value}。"
        raise ValueError(f"Unsupported query operation: {plan.operation}")

    @staticmethod
    def _location_text(plan: QueryPlan, result: QueryResult, locale: str) -> str:
        groups: dict[tuple[str, str], int] = {}
        for location in result.locations.values():
            key = (location.source, location.level)
            groups[key] = groups.get(key, 0) + 1
        kind = plan.kind or "entity"
        if locale == "zh":
            labels = {"slab": "楼板", "door": "门", "window": "窗", "wall": "墙", "beam": "梁", "column": "柱", "footing": "基础", "pile": "桩", "space": "房间"}
            parts = [
                (
                    f"{count} 个{labels.get(kind, '对象')}按 IfcBuildingStorey 空间包含关系位于 {level}"
                    if source == "spatial_containment"
                    else f"{count} 个{labels.get(kind, '对象')}的属性 Reference Level 为 {level}（不是 IfcBuildingStorey 空间包含关系）"
                )
                for (source, level), count in sorted(groups.items())
            ]
            return "；".join(parts) + "。"
        parts = [
            (
                f"{count} {kind}(s) are spatially contained in IfcBuildingStorey '{level}'"
                if source == "spatial_containment"
                else f"{count} {kind}(s) have property-based Reference Level '{level}' (not IfcBuildingStorey containment)"
            )
            for (source, level), count in sorted(groups.items())
        ]
        return "; ".join(parts) + "."
