"""Object-bound scalar lookup and conservative semantic property resolution."""

import re

from bim_evidence_qa.domain import BuildingEntity, PropertySource, PropertyValue, ResolutionError


SEMANTIC_FIELDS = {
    "length": ("Length",), "width": ("Width",), "height": ("Height",),
    "area": ("Area", "GrossArea", "NetArea"),
    "volume": ("NetVolume", "Volume", "GrossVolume"),
}
DISPLAY_LIMIT = 30


def resolve_object(reference: str, entities, kind: str | None = None) -> BuildingEntity:
    candidates = [e for e in entities if kind is None or e.kind == kind]
    token = " ".join(reference.casefold().split())
    exact = [e for e in candidates if token in {
        " ".join((e.name or "").casefold().split()), e.entity_id.casefold(),
        (e.global_id or "").casefold(),
    }]
    if not exact and kind:
        exact = [e for e in candidates if (e.name or "").casefold() == f"{kind} {token}"]
    if not exact:
        # Exported Revit element IDs are explicit name suffixes, not substring matches.
        exact = [e for e in candidates if e.name and e.name.rsplit(":", 1)[-1].casefold() == token]
    if not exact:
        raise ResolutionError("entity_not_found", f"Entity not found: '{reference}'.")
    if len(exact) != 1:
        raise ResolutionError("ambiguous", f"Ambiguous object '{reference}'.", tuple(e.entity_id for e in exact))
    return exact[0]


def resolve_property(entity: BuildingEntity, requested: str) -> PropertyValue:
    if requested in SEMANTIC_FIELDS:
        names = SEMANTIC_FIELDS[requested]
        candidates = [p for p in entity.properties if p.field_name in names]
        # Linear dimensions prefer exact base quantities. Volume explicitly means net volume
        # when supplied by a quantity set. Area deliberately keeps all competing sources.
        if requested != "area":
            quantities = [p for p in candidates if p.source is PropertySource.QUANTITY]
            if quantities:
                candidates = quantities
                if requested == "volume":
                    for name in names:
                        ranked = [p for p in candidates if p.field_name == name]
                        if ranked:
                            candidates = ranked
                            break
    else:
        candidates = [p for p in entity.properties if p.path == requested]
    if not candidates or (len(candidates) == 1 and candidates[0].value is None):
        raise ResolutionError("missing", f"Property '{requested}' is unavailable on '{entity.name or entity.entity_id}'.")
    if len(candidates) != 1:
        raise ResolutionError("ambiguous", f"Property '{requested}' has multiple candidates.",
                              tuple(f"{p.path} [#{p.source_id}]" for p in candidates))
    return candidates[0]


def requested_property(question: str, paths=()) -> str | None:
    # Exact paths are identifiers, never executable Python attribute expressions.
    for candidate in sorted(paths, key=lambda p: (-len(p), p)):
        if re.search(r"(?<![\w.])" + re.escape(candidate) + r"(?![\w.])", question):
            return candidate
    path = re.search(r"\b(?:Qto_[\w]+|Pset_[\w]+|Dimensions)\.[A-Za-z][\w]*\b", question)
    if path:
        return path[0]
    tokens = re.findall(r"[a-z]+", question.casefold())
    if "properties" in tokens or "property" in tokens:
        return "properties"
    found = [p for p in SEMANTIC_FIELDS if p in tokens]
    if len(found) > 1:
        raise ResolutionError("ambiguous", "Request one property at a time.", tuple(found))
    return found[0] if found else None
