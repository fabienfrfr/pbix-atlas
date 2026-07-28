"""Best-effort inference of a Power Query table's column names directly from
its M step ASTs.

`pbixray` only exposes column schema for tables actually loaded into the
semantic model. Staging/bronze queries (``load = false``, or queries that
just feed other queries) have no schema there at all, even though their
column names are usually visible in the M code itself.

This module walks a query's steps *in execution order* and tracks the
column set through the handful of M functions that make it explicit:

- ``Table.TransformColumnTypes`` / ``Table.TransformColumns`` -> full list
  of column names (post-typing), used as the base schema.
- ``Table.SelectColumns`` -> explicit column subset.
- ``Table.RemoveColumns`` -> subtraction.
- ``Table.RenameColumns`` -> old -> new mapping, applied to the known set.
  Only *literal* rename pairs are honored; if the rename list is itself a
  computed value (e.g. built from another table, as with dynamic
  "correspondence table" renaming schemes), we cannot resolve it statically
  and we flag it instead of guessing.

This is intentionally conservative: it only ever reports names that are
literally present in the M code, and it says so explicitly when it can't
go further (``dynamic_rename`` flag), rather than silently returning a
stale or partial list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_TYPE_FUNCS = {"Table.TransformColumnTypes", "Table.TransformColumns"}
_RENAME_FUNCS = {"Table.RenameColumns"}
_SELECT_FUNCS = {"Table.SelectColumns"}
_REMOVE_FUNCS = {"Table.RemoveColumns"}


@dataclass
class InferredSchema:
    columns: list[str] = field(default_factory=list)
    dynamic_rename: bool = False  # an unresolvable (table-driven) rename occurred somewhere in the chain
    names_are_post_rename: bool = False  # True: `columns` were captured *after* an unresolved rename,
    # so they are NOT the source's original names - just whatever the dynamic rename produced
    # (unknowable statically). False: `columns` were captured before any such rename, i.e. as close
    # to the true source/raw names as this step chain lets us see.
    source_columns: list[str] | None = None  # only set when a *literal* (statically resolvable) rename
    # was applied to `columns`: the pre-rename name for each entry in `columns`, same order/length.
    # e.g. OData query renames "Material__DisplayMaterial" -> "Article" via a literal Table.RenameColumns:
    # columns=["Article"], source_columns=["Material__DisplayMaterial"]. None means `columns` already
    # *are* the source names (no rename happened, or - see names_are_post_rename - an unresolvable
    # rename makes the true source names unknowable, so there's nothing reliable to report here).


def _lit_str(node: dict | None) -> str | None:
    if isinstance(node, dict) and node.get("_") == "Lit":
        value = node.get("value")
        return value if isinstance(value, str) else None
    return None


def _names_from_list_expr(node: dict | None) -> list[str] | None:
    if not isinstance(node, dict) or node.get("_") != "ListExpr":
        return None
    names = []
    for item in node.get("items", []):
        v = _lit_str(item)
        if v is None:
            return None  # non-literal entry: bail out rather than partial-guess
        names.append(v)
    return names


def _names_from_pair_list_expr(node: dict | None) -> list[str] | None:
    """For `Table.TransformColumnTypes`-style lists, where each item is
    itself a `[name, type]` pair (a 2-item ListExpr), not a bare literal."""
    if not isinstance(node, dict) or node.get("_") != "ListExpr":
        return None
    names = []
    for item in node.get("items", []):
        if not isinstance(item, dict) or item.get("_") != "ListExpr" or not item.get("items"):
            return None
        v = _lit_str(item["items"][0])
        if v is None:
            return None
        names.append(v)
    return names


def _literal_rename_pairs(node: dict | None) -> dict[str, str] | None:
    """Returns {old: new} if the rename list is a literal ListExpr of
    [old, new] literal pairs, else None (e.g. built dynamically from a
    lookup table via Table.ToRows(...))."""
    if not isinstance(node, dict) or node.get("_") != "ListExpr":
        return None
    pairs: dict[str, str] = {}
    for item in node.get("items", []):
        if not isinstance(item, dict) or item.get("_") != "ListExpr":
            return None
        parts = item.get("items", [])
        if len(parts) < 2:
            return None
        old, new = _lit_str(parts[0]), _lit_str(parts[1])
        if old is None or new is None:
            return None
        pairs[old] = new
    return pairs


def _input_ref(op: dict | None) -> str | None:
    """Name of the identifier this step's operation directly transforms, if
    any - used to tell "main chain" steps (each applied to the previous
    step's result) apart from auxiliary let-bindings that happen to sit
    among them (e.g. a small lookup table built and consumed only to drive
    a later Table.RenameColumns call)."""
    if not isinstance(op, dict):
        return None
    if op.get("_") == "Invoke":
        args = op.get("args", [])
        if args and isinstance(args[0], dict) and args[0].get("_") == "Ident":
            return args[0]["name"]
        return None
    if op.get("_") in ("FieldAccess", "ItemAccess"):
        return _input_ref(op.get("target"))
    if op.get("_") == "Ident":
        return op.get("name")
    return None


def infer_schema_from_steps(steps: list[tuple[str, dict]]) -> InferredSchema:
    """`steps`: (label, operation AST) of each step, in execution order
    (Source first, final step last).

    Only steps that form the *main* sequential chain - each one transforming
    the immediately preceding accepted step's result - are used to track
    the column set. Side let-bindings that don't sit on that chain (helper
    lookup tables, intermediate values only used as an argument elsewhere)
    are read from when they're referenced (e.g. literal rename pairs) but
    never treated as if they were the table itself."""
    result = InferredSchema()
    if not steps:
        return result

    chain_head = steps[0][0]  # first step (usually "Source") always starts the chain
    unresolved_rename_seen = False
    provenance: dict[str, str] = {}  # current column name -> earliest known (source-side) name

    for label, op in steps[1:]:
        if _input_ref(op) != chain_head:
            continue  # auxiliary let-binding, not part of the main pipeline
        chain_head = label

        if not isinstance(op, dict) or op.get("_") != "Invoke":
            continue
        fname = op.get("func", {}).get("name")
        args = op.get("args", [])
        if not fname or len(args) < 2:
            continue

        if fname in _TYPE_FUNCS:
            names = _names_from_pair_list_expr(args[1])
            if names:
                first_time = not result.columns
                result.columns = names
                if first_time:
                    result.names_are_post_rename = unresolved_rename_seen
                    provenance = {} if unresolved_rename_seen else {c: c for c in names}
                else:
                    # re-listing (retyping/reordering/subsetting) already-known columns -
                    # keep whatever provenance they already had, don't treat this as a
                    # fresh source-level baseline
                    provenance = {c: provenance.get(c, c) for c in names}

        elif fname in _SELECT_FUNCS:
            names = _names_from_list_expr(args[1])
            if names:
                first_time = not result.columns
                result.columns = names
                if first_time:
                    result.names_are_post_rename = unresolved_rename_seen
                    provenance = {} if unresolved_rename_seen else {c: c for c in names}
                else:
                    provenance = {c: provenance.get(c, c) for c in names}

        elif fname in _REMOVE_FUNCS:
            names = _names_from_list_expr(args[1])
            if names and result.columns:
                result.columns = [c for c in result.columns if c not in names]
                provenance = {c: v for c, v in provenance.items() if c in result.columns}

        elif fname in _RENAME_FUNCS:
            pairs = _literal_rename_pairs(args[1])
            if pairs is None:
                result.dynamic_rename = True
                unresolved_rename_seen = True
                provenance = {}
                continue
            if result.columns:
                new_columns = [pairs.get(c, c) for c in result.columns]
                if not unresolved_rename_seen:
                    provenance = {pairs.get(c, c): provenance.get(c, c) for c in result.columns}
                result.columns = new_columns
            else:
                # first signal we get: the "old" side is the base schema
                old_names = list(pairs.keys())
                result.columns = [pairs.get(c, c) for c in old_names]
                result.names_are_post_rename = unresolved_rename_seen
                provenance = {} if unresolved_rename_seen else {pairs[c]: c for c in old_names}

    if provenance and any(provenance.get(c) != c for c in result.columns):
        result.source_columns = [provenance.get(c, c) for c in result.columns]

    return result


def extract_view_name(step_operations: list[dict]) -> str | None:
    """Detects an OData/navigation-table entity access of the shape
    `Source{[Name="EntityName", Signature="table"]}[Data]` (the standard
    Power Query pattern for picking one entity out of an `OData.Feed(...)`
    navigation table) anywhere in a query's steps, and returns that entity
    name - i.e. the real remote table/view name, as opposed to the local
    query name the report author gave it.

    Without this, a source like an OData root shows the *destination*
    query names (e.g. `CMD_ANGLE_BRZ`) with no way to tell which remote
    view each one actually reads from."""
    for op in step_operations:
        name = _entity_name_in_expr(op)
        if name:
            return name
    return None


def _entity_name_in_expr(node: dict | None) -> str | None:
    if not isinstance(node, dict):
        return None
    if node.get("_") == "FieldAccess" and node.get("field") == "Data":
        return _entity_name_in_expr(node.get("target"))
    if node.get("_") == "ItemAccess":
        index = node.get("index")
        if isinstance(index, dict) and index.get("_") == "RecordExpr":
            for key, value in index.get("fields", []):
                if key == "Name":
                    return _lit_str(value)
        return None
    return None
