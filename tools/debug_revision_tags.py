from __future__ import annotations

import sys
from pathlib import Path


def _iter_nodes(root):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for attr in ("children", "content_children"):
            kids = getattr(n, attr, None)
            if kids:
                stack.extend(reversed(list(kids)))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from aspose.note._internal.onestore.object_space import (  # noqa: WPS433
        parse_object_spaces_with_resolved_ids,
        parse_object_spaces_with_revisions,
    )
    from aspose.note._internal.onestore.header import Header  # noqa: WPS433
    from aspose.note._internal.onestore.io import BinaryReader  # noqa: WPS433
    from aspose.note._internal.onestore.parse_context import ParseContext  # noqa: WPS433
    from aspose.note._internal.onestore.txn_log import parse_transaction_log  # noqa: WPS433

    from aspose.note._internal.ms_one.compact_id import resolve_compact_id_array  # noqa: WPS433
    from aspose.note._internal.ms_one.entities.parsers import ParseState, parse_node  # noqa: WPS433
    from aspose.note._internal.ms_one.entities.structure import EmbeddedFile, PageSeries, Section  # noqa: WPS433
    from aspose.note._internal.ms_one.property_access import get_oid_array  # noqa: WPS433
    from aspose.note._internal.ms_one.reader import (  # noqa: WPS433
        _build_effective_object_index_for_object_space,
        _extract_pages_from_page_object_space,
        _pick_root_object_space,
    )
    from aspose.note._internal.ms_one.spec_ids import PID_CHILD_GRAPH_SPACE_ELEMENT_NODES  # noqa: WPS433

    if len(sys.argv) < 2:
        print("Usage: python tools/debug_revision_tags.py <file.one>")
        raise SystemExit(2)

    p = Path(sys.argv[1])
    data = p.read_bytes()

    ctx = ParseContext(strict=True, file_size=len(data))
    step10 = parse_object_spaces_with_revisions(data, ctx=ctx)
    step11 = parse_object_spaces_with_resolved_ids(data, ctx=ctx)

    os_index = _pick_root_object_space(step10, step11)
    step10_os = step10.object_spaces[os_index]
    step11_os = step11.object_spaces[os_index]

    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    idx, gid_table, roots = _build_effective_object_index_for_object_space(
        data,
        step10_os=step10_os,
        step11_os=step11_os,
        last_count_by_list_id=last_count_by_list_id,
        ctx=ctx,
    )

    # Find the Section node among roots.
    section_oid = None
    for _, oid in roots:
        rec = idx.get(oid)
        if rec is not None and rec.jcid is not None and int(rec.jcid.index) == 0x10:  # SectionNode
            section_oid = oid
            break
    if section_oid is None:
        section_oid = roots[0][1]

    state = ParseState(index=idx, gid_table=gid_table, ctx=ctx, file_data_store_index={})
    section = parse_node(section_oid, state)
    if not isinstance(section, Section):
        raise RuntimeError("Root is not Section")

    page_series = [c for c in section.children if isinstance(c, PageSeries)]
    print("PageSeries count:", len(page_series))
    if not page_series:
        return

    ps = page_series[0]
    graph_ids = get_oid_array(ps.raw_properties, PID_CHILD_GRAPH_SPACE_ELEMENT_NODES)
    resolved_gosids = resolve_compact_id_array(graph_ids, gid_table, ctx=ctx) if graph_ids else ()
    print("Page object spaces:", len(resolved_gosids))

    gosid_to_os_index = {os.gosid: i for i, os in enumerate(step10.object_spaces)}

    for gosid in resolved_gosids:
        os_i = gosid_to_os_index.get(gosid)
        print("\n== Page OS", gosid, "index", os_i)
        s10 = step10.object_spaces[os_i]
        s11 = step11.object_spaces[os_i]
        print(" revisions:", len(s10.revisions))
        print(" role_assignments:", len(getattr(s10, "role_assignments", ())))
        for pair, rid in getattr(s10, "role_assignments", ()):
            print("  pair", pair, "->", rid)

        for ri in range(len(s10.revisions)):
            pages = _extract_pages_from_page_object_space(
                data=data,
                step10_os=s10,
                step11_os=s11,
                last_count_by_list_id=last_count_by_list_id,
                ctx=ctx,
                file_data_store_index={},
                rev_index=ri,
            )
            labels = set()
            for pg in pages:
                for n in _iter_nodes(pg):
                    if isinstance(n, EmbeddedFile) and n.tags:
                        labels |= {t.label for t in n.tags if t.label}
            if labels:
                print("  rev", ri, "labels", sorted(labels))


if __name__ == "__main__":
    main()
