"""Deterministic candidate sheets from IFC identities, never answers or geometry."""
from dataclasses import dataclass
import re

from bim_evidence_qa.application import ApplicationQueryResult
from bim_evidence_qa.domain import BuildingDataset
from bim_evidence_qa.parsers.pdf import DrawingDocument


@dataclass(frozen=True, slots=True)
class SearchTerm:
    text: str
    source: str
    weight: int
    entity_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DrawingEvidence:
    document: str
    page_number: int
    sheet_title: str | None
    matched_terms: tuple[SearchTerm, ...]
    score: int
    reason: str
    drawing_number: str | None = None


@dataclass(frozen=True, slots=True)
class DrawingRetrieval:
    candidates: tuple[DrawingEvidence, ...]
    reason: str

    @property
    def best(self):
        if not self.candidates or (len(self.candidates) > 1 and self.candidates[0].score == self.candidates[1].score):
            return None
        return self.candidates[0]


def evidence_terms(outcome: ApplicationQueryResult, dataset: BuildingDataset) -> tuple[SearchTerm, ...]:
    terms = {}
    def add(text, source, weight, entity_id=None):
        if text is None or not str(text).strip():
            return
        text = " ".join(str(text).split())
        key = (text, source)
        prior = terms.get(key)
        ids = tuple(sorted(set((prior.entity_ids if prior else ()) + ((entity_id,) if entity_id else ()))))
        terms[key] = SearchTerm(text, source, weight, ids)
    for entity in outcome.result.entities:
        if entity.name and len(entity.name) >= 5:
            add(entity.name, "object name", 14, entity.entity_id)
            suffix = entity.name.rsplit(":", 1)[-1]
            if re.fullmatch(r"\d{5,}", suffix):
                add(suffix, "exported element number", 12, entity.entity_id)
        if entity.kind in {"door", "window", "space"}:
            for prop in entity.properties:
                if prop.field_name in {"Mark", "Number"} and not prop.inherited:
                    add(prop.value, "instance mark", 8, entity.entity_id)
                elif prop.field_name == "Type Mark":
                    add(prop.value, "type mark (shared)", 4, entity.entity_id)
        if entity.kind == "storey":
            add(entity.name, "storey label", 2, entity.entity_id)
    for condition in outcome.plan.filters:
        if condition.field == "container_id":
            storey = next((e for e in dataset.entities if e.entity_id == condition.value and e.kind == "storey"), None)
            if storey:
                add(storey.name, "spatial scope", 3)
        elif condition.field == "Constraints.Reference Level":
            add(condition.value, "property-based Reference Level", 3)
    return tuple(terms.values())


def retrieve_drawings(outcome: ApplicationQueryResult, dataset: BuildingDataset,
                      documents: tuple[DrawingDocument, ...]) -> DrawingRetrieval:
    terms = evidence_terms(outcome, dataset)
    candidates = []
    for document in documents:
        for page in document.pages:
            text = " ".join(page.text.split()).casefold()
            lines = [line.strip().casefold() for line in page.text.splitlines()]
            plan_sheet = bool(re.search(r"\bplans?\b", page.sheet_title or "", re.I))
            matches = []
            for term in terms:
                token = term.text.casefold()
                pattern = r"(?<![\w.-])" + re.escape(token) + r"(?![\w.-])"
                if not re.search(pattern, text):
                    continue
                if term.source == "exported element number" and not re.search(
                    r"\(\s*" + re.escape(token) + r"\s*\)|\b(?:element|id|mark|number)\s*[:#=]?\s*" + re.escape(token) + r"\b", text
                ):
                    continue
                if term.source in {"instance mark", "type mark (shared)"}:
                    if not plan_sheet or token not in lines:
                        continue
                    if term.source == "instance mark" and len(token) < 3:
                        continue
                    if term.source == "type mark (shared)" and (len(token) < 2 or lines.count(token) < 3):
                        continue
                if term.source in {"spatial scope", "property-based Reference Level", "storey label"} and not plan_sheet:
                    continue
                matches.append(term)
            if not matches:
                continue
            # Shared labels identify a related plan sheet, never an individual object.
            score = sum(t.weight for t in matches) + (2 if plan_sheet else 0)
            if score < 5:
                continue
            reasons = [f"{t.source}: {t.text}" for t in matches]
            reason = "; ".join(reasons) + ". Candidate sheet only; this does not verify the IFC numeric answer or locate geometry."
            candidates.append(DrawingEvidence(document.file_name, page.page_number, page.sheet_title,
                                              tuple(matches), score, reason, page.drawing_number))
    candidates.sort(key=lambda c: (-c.score, c.document, c.page_number))
    result = DrawingRetrieval(tuple(candidates), "No reliable drawing evidence found.")
    if result.best:
        return DrawingRetrieval(result.candidates, result.best.reason)
    if candidates:
        return DrawingRetrieval(result.candidates, "No reliable drawing evidence found. Equal-score candidates require manual review.")
    return result
