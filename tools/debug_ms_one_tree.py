from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ms_one.reader import parse_section_file  # noqa: E402
from ms_one.object_index import ObjectIndex, ObjectRecord, apply_object_groups  # noqa: E402
from ms_one.compact_id import EffectiveGidTable  # noqa: E402

from onestore.header import Header  # noqa: E402
from onestore.io import BinaryReader  # noqa: E402
from onestore.object_space import parse_object_spaces_with_revisions, parse_object_spaces_with_resolved_ids  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402
from onestore.txn_log import parse_transaction_log  # noqa: E402


def main() -> None:
    data = (ROOT / "SimpleTable.one").read_bytes()

    # Rebuild index like reader does (for debugging).
    ctx = ParseContext(strict=True, file_size=len(data))
    step10 = parse_object_spaces_with_revisions(data, ctx=ctx)
    step11 = parse_object_spaces_with_resolved_ids(data, ctx=ctx)
    os_index = 0
    step10_os = step10.object_spaces[os_index]
    step11_os = step11.object_spaces[os_index]
    rev_index = len(step10_os.revisions) - 1

    header = Header.parse(BinaryReader(data), ctx=ctx)
    last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx=ctx)

    objects: dict[object, ObjectRecord] = {}
    chain: list[int] = []
    cur = rev_index
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

    for i in chain:
        r10 = step10_os.revisions[i]
        r11 = step11_os.revisions[i]
        if r10.manifest is None:
            continue
        table_i = EffectiveGidTable.from_sorted_items(r11.effective_gid_table)
        apply_object_groups(
            objects,  # type: ignore[arg-type]
            data,
            r10.manifest.object_groups,
            effective_gid_table=table_i,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )
    idx = ObjectIndex(objects_by_oid=objects)  # type: ignore[arg-type]
    print("ObjectIndex size:", len(idx.objects_by_oid))
    for oid, rec in list(idx.objects_by_oid.items()):
        print(" idx", oid, "jcid=", None if rec.jcid is None else int(rec.jcid.index), "props=", None if rec.properties is None else rec.properties.c_properties)

    for oid, rec in list(idx.objects_by_oid.items()):
        if rec.jcid is not None and int(rec.jcid.index) == 0x30 and rec.properties is not None:
            print("PageMetaData props for", oid)
            for p in rec.properties.properties:
                v = p.value
                if isinstance(v, tuple):
                    # Print short tuple content for debugging (ObjectIDs/ObjectSpaceIDs, etc.)
                    head = ", ".join(repr(x) for x in v[:5])
                    more = "..." if len(v) > 5 else ""
                    vinfo = f"tuple(len={len(v)}: {head}{more})"
                elif isinstance(v, (bytes, bytearray, memoryview)):
                    vinfo = f"bytes(len={len(v)})"
                else:
                    vinfo = repr(v)
                print(f" pid=0x{int(p.prid.raw):08X} type=0x{int(p.prid.prop_type):02X} value={vinfo}")

    section = parse_section_file(data, strict=True)

    print("Section:", type(section).__name__, "display=", getattr(section, "display_name", None))
    kids = getattr(section, "children", None) or []
    print("Section children:", len(kids))

    for i, ch in enumerate(kids[:20]):
        print(" child", i, type(ch).__name__, "title=", getattr(ch, "title", None), "display=", getattr(ch, "display_name", None))
        gkids = getattr(ch, "children", None) or []
        print("  grandchildren types:", [type(k).__name__ for k in gkids[:20]])
        for j, g in enumerate(gkids[:10]):
            print("   grandchild", j, type(g).__name__, "oid=", getattr(g, "oid", None))
            rec = idx.get(getattr(g, "oid", None))
            print("    in index:", rec is not None, "jcid=", None if rec is None or rec.jcid is None else int(rec.jcid.index))
            if rec is not None and rec.properties is not None:
                for p in rec.properties.properties:
                    if int(p.prid.prop_type) in (0x08, 0x09):
                        v = p.value
                        if isinstance(v, tuple):
                            vinfo = f"tuple(len={len(v)})"
                        else:
                            vinfo = type(v).__name__
                        print(f"     ref-prop pid=0x{int(p.prid.raw):08X} type=0x{int(p.prid.prop_type):02X} value={vinfo}")

        ps = getattr(ch, "raw_properties", None)
        if ps is not None and i == 0:
            print("  raw_properties count:", len(ps.properties))
            for p in ps.properties[:25]:
                v = p.value
                if isinstance(v, tuple):
                    head = ", ".join(repr(x) for x in v[:5])
                    more = "..." if len(v) > 5 else ""
                    vinfo = f"tuple(len={len(v)}: {head}{more})"
                else:
                    vinfo = type(v).__name__
                print(f"   pid=0x{int(p.prid.raw):08X} type=0x{int(p.prid.prop_type):02X} value={vinfo}")


if __name__ == "__main__":
    main()
