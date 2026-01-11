from __future__ import annotations

from onestore.common_types import CompactID, ExtendedGUID
from onestore.header import Header
from onestore.io import BinaryReader
from onestore.file_node_types import DEFAULT_CONTEXT_GCTXID
from onestore.file_data import parse_file_data_store_index
from onestore.object_space import parse_object_spaces_with_resolved_ids, parse_object_spaces_with_revisions
from onestore.parse_context import ParseContext
from onestore.txn_log import parse_transaction_log

from .compact_id import EffectiveGidTable
from .errors import MSOneFormatError
from .object_index import ObjectIndex, ObjectRecord, apply_object_groups
from .property_access import get_oid_array
from .spec_ids import (
    JCID_PAGE_MANIFEST_NODE_INDEX,
    JCID_PAGE_NODE_INDEX,
    JCID_SECTION_NODE_INDEX,
    PID_CHILD_GRAPH_SPACE_ELEMENT_NODES,
)
from .entities.parsers import ParseState, parse_node
from .entities.base import BaseNode
from .entities.structure import Page, PageManifest, PageSeries, RichText, Section
from typing import cast


def _pick_default_revision_index(step10_os) -> int:
    """Pick the revision that represents the default (current) view for an object space."""

    if not step10_os.revisions:
        raise MSOneFormatError("No revisions found in object space")

    rev_index = len(step10_os.revisions) - 1
    target_rid: ExtendedGUID | None = None
    for pair, rid in getattr(step10_os, "role_assignments", ()):
        if pair.gctxid == DEFAULT_CONTEXT_GCTXID and int(pair.revision_role) == 1:
            target_rid = rid
            break

    if target_rid is not None:
        for i, rev in enumerate(step10_os.revisions):
            if rev.rid == target_rid:
                rev_index = i
                break

    return rev_index


def _build_dependency_chain_indices(step10_os, start_index: int) -> list[int]:
    """Return revision indices from oldest to newest for the dependency chain ending at start_index."""

    chain: list[int] = []
    cur = start_index
    seen: set[int] = set()
    while 0 <= cur < len(step10_os.revisions) and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        dep = step10_os.revisions[cur].rid_dependent
        if dep.is_zero():
            break
        dep_index = None
        for j, r in enumerate(step10_os.revisions):
            if r.rid == dep:
                dep_index = j
                break
        if dep_index is None:
            break
        cur = dep_index

    chain.reverse()
    return chain


def _iter_entity_nodes(root: object):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for attr in ("children", "content_children"):
            kids = getattr(n, attr, None)
            if kids:
                stack.extend(reversed(list(kids)))


def _page_text_signature(page: Page) -> str:
    texts: list[str] = []
    for n in _iter_entity_nodes(page):
        if isinstance(n, RichText) and n.text is not None:
            t = n.text.strip()
            if t:
                texts.append(t)
    return "\n".join(texts)


def _pick_root_object_space(step10, step11):
    # Prefer the root object space.
    root = step10.root_gosid
    for i, os in enumerate(step10.object_spaces):
        if os.gosid == root:
            return i
    # Fallback: first.
    return 0


def _build_effective_root_objects(
    step10_os,
    step11_os,
    rev_index: int,
) -> tuple[tuple[int, ExtendedGUID], ...]:
    """Some files omit root refs in later dependent revisions; inherit from dependencies."""

    visited: set[int] = set()
    i = rev_index
    while 0 <= i < len(step11_os.revisions):
        if i in visited:
            break
        visited.add(i)

        roots = step11_os.revisions[i].resolved_root_objects
        if roots:
            return roots

        dep = step10_os.revisions[i].rid_dependent
        if dep.is_zero():
            break

        # Find dependency by rid (same order in step10 and step11).
        dep_index = None
        for j, r in enumerate(step10_os.revisions):
            if r.rid == dep:
                dep_index = j
                break
        if dep_index is None:
            break
        i = dep_index

    return ()


def _build_effective_object_index_for_object_space(
    data: bytes | bytearray | memoryview,
    *,
    step10_os,
    step11_os,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
    rev_index: int | None = None,
) -> tuple[ObjectIndex, EffectiveGidTable, tuple[tuple[int, ExtendedGUID], ...]]:
    """Build an ObjectIndex for a single object space at its latest revision.

    Replays object group changes across the dependency chain to produce an
    effective view of objects at the last revision.
    """

    if rev_index is None:
        # Prefer the revision assigned to the default context (common for .one).
        rev_index = _pick_default_revision_index(step10_os)
    rev11 = step11_os.revisions[rev_index]
    gid_table = EffectiveGidTable.from_sorted_items(rev11.effective_gid_table)
    roots = _build_effective_root_objects(step10_os, step11_os, rev_index)

    objects: dict[ExtendedGUID, ObjectRecord] = {}

    chain = _build_dependency_chain_indices(step10_os, rev_index)

    for i in chain:
        r10 = step10_os.revisions[i]
        r11 = step11_os.revisions[i]
        if r10.manifest is None:
            continue
        table_i = EffectiveGidTable.from_sorted_items(r11.effective_gid_table)
        apply_object_groups(
            objects,
            data,
            r10.manifest.object_groups,
            effective_gid_table=table_i,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

    return ObjectIndex(objects_by_oid=objects), gid_table, roots


def _extract_pages_from_page_object_space(
    *,
    data: bytes | bytearray | memoryview,
    step10_os,
    step11_os,
    last_count_by_list_id: dict[int, int],
    ctx: ParseContext,
    file_data_store_index=None,
    rev_index: int | None = None,
) -> list[Page]:
    idx, gid_table, roots = _build_effective_object_index_for_object_space(
        data,
        step10_os=step10_os,
        step11_os=step11_os,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
        rev_index=rev_index,
    )

    state = ParseState(index=idx, gid_table=gid_table, ctx=ctx, file_data_store_index=file_data_store_index)

    # Many files do not expose PageManifest/PageNode as roots of the page object space.
    # Instead of relying on roots (which may be other container types), scan the object
    # index for the actual content-bearing nodes.
    manifest_oids: list[ExtendedGUID] = []
    page_oids: list[ExtendedGUID] = []
    for oid, rec in idx.objects_by_oid.items():
        if rec.jcid is None:
            continue
        jidx = int(rec.jcid.index)
        if jidx == JCID_PAGE_MANIFEST_NODE_INDEX:
            manifest_oids.append(oid)
        elif jidx == JCID_PAGE_NODE_INDEX:
            page_oids.append(oid)

    root_nodes: list[object] = []
    if manifest_oids:
        root_nodes = [parse_node(oid, state) for oid in manifest_oids]
    elif page_oids:
        root_nodes = [parse_node(oid, state) for oid in page_oids]
    elif roots:
        # Last resort: try parsing the first effective root.
        root_nodes = [parse_node(roots[0][1], state)]

    pages: list[Page] = []
    for root_node in root_nodes:
        if isinstance(root_node, PageManifest):
            for n in root_node.content_children:
                if isinstance(n, Page):
                    pages.append(n)
        elif isinstance(root_node, Page):
            pages.append(root_node)

    return pages


def parse_section_file(
    data: bytes | bytearray | memoryview,
    *,
    strict: bool = True,
    include_page_history: bool = False,
) -> Section:
    """Parse a .one section file into a minimal MS-ONE entity tree."""

    ctx = ParseContext(strict=bool(strict), file_size=len(data))

    # Best-effort FileDataStore index. Some fixtures violate MUST-level constraints in this area,
    # so always parse it in non-strict mode and never let it break section parsing.
    fds_ctx = ParseContext(strict=False, file_size=len(data))
    try:
        file_data_store_index = parse_file_data_store_index(data, ctx=fds_ctx)
    except Exception:
        file_data_store_index = {}

    step10 = parse_object_spaces_with_revisions(data, ctx=ctx)
    step11 = parse_object_spaces_with_resolved_ids(data, ctx=ctx)

    if not step10.object_spaces:
        raise MSOneFormatError("No object spaces found")

    os_index = _pick_root_object_space(step10, step11)
    step10_os = step10.object_spaces[os_index]
    step11_os = step11.object_spaces[os_index]

    # Needed for parsing referenced file node lists (object group lists).
    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    # Build index for the section/root object space.
    obj_index, gid_table, roots = _build_effective_object_index_for_object_space(
        data,
        step10_os=step10_os,
        step11_os=step11_os,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    # Resolve roots for the section object space.
    rev_index = len(step10_os.revisions) - 1
    roots = _build_effective_root_objects(step10_os, step11_os, rev_index) or roots
    if not roots:
        raise MSOneFormatError("No root objects found")

    # Resolve a section root: find an object with JCID SectionNode among roots.
    section_oid: ExtendedGUID | None = None
    for _, oid in roots:
        rec = obj_index.get(oid)
        if rec is not None and rec.jcid is not None and int(rec.jcid.index) == JCID_SECTION_NODE_INDEX:
            section_oid = oid
            break

    if section_oid is None:
        # Fallback: take the first root and try to parse it.
        section_oid = roots[0][1]

    state = ParseState(index=obj_index, gid_table=gid_table, ctx=ctx, file_data_store_index=file_data_store_index)
    node = parse_node(section_oid, state)

    if not isinstance(node, Section):
        raise MSOneFormatError("Root object is not a Section", oid=section_oid)

    # Upgrade PageSeries children from metadata-only pages to actual Page nodes by
    # following ChildGraphSpaceElementNodes (page object spaces) and parsing their
    # PageManifest/Page roots.
    #
    # This keeps the entity tree stable for callers, but exposes real page content
    # (outlines, tables, images, etc.) when available.
    gosid_to_os_index = {os.gosid: i for i, os in enumerate(step10.object_spaces)}

    upgraded_children: list[BaseNode] = []
    for ch in node.children:
        if not isinstance(ch, PageSeries):
            upgraded_children.append(ch)
            continue

        # ChildGraphSpaceElementNodes lives on the PageSeries node.
        if ch.raw_properties is None:
            upgraded_children.append(ch)
            continue

        graph_ids = get_oid_array(ch.raw_properties, PID_CHILD_GRAPH_SPACE_ELEMENT_NODES)
        if not graph_ids:
            upgraded_children.append(ch)
            continue

        # Resolve ObjectSpaceIDs (CompactID) to ExtendedGUID using the section GID table.
        if graph_ids and isinstance(graph_ids[0], CompactID):
            from .compact_id import resolve_compact_id_array

            resolved_gosids = resolve_compact_id_array(cast(tuple[CompactID, ...], graph_ids), gid_table, ctx=ctx)
        else:
            # Some files may already store resolved ObjectSpaceIDs.
            resolved_gosids = cast(tuple[ExtendedGUID, ...], graph_ids)

        pages: list[Page] = []
        page_space_history_by_oid: dict[ExtendedGUID, tuple[Page, ...]] = {}
        for gosid in resolved_gosids:
            os_i = gosid_to_os_index.get(gosid)
            if os_i is None:
                continue

            step10_page_os = step10.object_spaces[os_i]
            step11_page_os = step11.object_spaces[os_i]

            latest_pages = _extract_pages_from_page_object_space(
                data=data,
                step10_os=step10_page_os,
                step11_os=step11_page_os,
                last_count_by_list_id=last_count_by_list_id,
                ctx=ctx,
                file_data_store_index=file_data_store_index,
            )
            pages.extend(latest_pages)

            if include_page_history and step10_page_os.revisions:
                latest_rev_index = _pick_default_revision_index(step10_page_os)

                # Many real-world .one files do not link revisions via ridDependent.
                # For history, build snapshots across revisions in list order up to the
                # chosen default revision (inclusive), then collapse identical states.
                snapshots_by_index: list[list[Page]] = []
                for ri in range(0, latest_rev_index + 1):
                    snapshots_by_index.append(
                        _extract_pages_from_page_object_space(
                            data=data,
                            step10_os=step10_page_os,
                            step11_os=step11_page_os,
                            last_count_by_list_id=last_count_by_list_id,
                            ctx=ctx,
                            file_data_store_index=file_data_store_index,
                            rev_index=ri,
                        )
                    )

                # Collect candidate page IDs across snapshots.
                all_oids: set[ExtendedGUID] = set()
                for snap in snapshots_by_index:
                    for p in snap:
                        all_oids.add(p.oid)
                # If all snapshots are empty but we have a current page, still try
                # to attach a best-effort history to that page.
                if not all_oids and latest_pages:
                    all_oids.add(latest_pages[0].oid)

                for oid in all_oids:
                    per_rev: list[Page] = []
                    for snap in snapshots_by_index:
                        hit = next((p for p in snap if p.oid == oid), None)
                        if hit is None and len(snap) == 1:
                            hit = snap[0]
                        if hit is not None:
                            per_rev.append(hit)

                    if len(per_rev) < 2:
                        continue

                    # Collapse consecutive identical text states (oldest -> newest).
                    unique: list[Page] = []
                    last_sig: str | None = None
                    for p in per_rev:
                        sig = _page_text_signature(p)
                        if last_sig is None or sig != last_sig:
                            unique.append(p)
                            last_sig = sig

                    # Expose only past revisions (newest -> oldest), excluding current.
                    if len(unique) >= 2:
                        page_space_history_by_oid[oid] = tuple(reversed(unique[:-1]))

        if include_page_history and page_space_history_by_oid and pages:
            enriched: list[Page] = []
            for p in pages:
                hist = page_space_history_by_oid.get(p.oid, ())
                enriched.append(
                    Page(
                        oid=p.oid,
                        jcid_index=p.jcid_index,
                        raw_properties=p.raw_properties,
                        title=p.title,
                        children=p.children,
                        history=hist,
                    )
                )
            pages = enriched

        if pages:
            upgraded_children.append(
                PageSeries(
                    oid=ch.oid,
                    jcid_index=ch.jcid_index,
                    raw_properties=ch.raw_properties,
                    children=tuple(pages),
                )
            )
        else:
            upgraded_children.append(ch)

    return Section(
        oid=node.oid,
        jcid_index=node.jcid_index,
        raw_properties=node.raw_properties,
        display_name=node.display_name,
        children=tuple(upgraded_children),
    )


def parse_section_file_with_page_history(
    data: bytes | bytearray | memoryview,
    *,
    strict: bool = True,
) -> Section:
    """Parse a .one section file and populate per-page history snapshots.

    The current page state is represented by the normal entity tree. Each Page node
    may additionally have Page.history populated with newest-to-oldest previous
    revisions of that page (best-effort).
    """

    return parse_section_file(data, strict=strict, include_page_history=True)
