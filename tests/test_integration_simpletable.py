import re
import sys
import unittest
import uuid
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onestore.chunk_refs import FileChunkReference32, FileChunkReference64x32, parse_filenode_chunk_reference  # noqa: E402
from onestore.common_types import ExtendedGUID, StringInStorageBuffer  # noqa: E402
from onestore.crc import crc32_rfc3309  # noqa: E402
from onestore.errors import OneStoreFormatError  # noqa: E402
from onestore.header import GUID_FILE_FORMAT, GUID_FILE_TYPE_ONE, Header  # noqa: E402
from onestore.io import BinaryReader  # noqa: E402
from onestore.object_space import parse_object_spaces_summary  # noqa: E402
from onestore.object_space import parse_object_spaces_with_revisions  # noqa: E402
from onestore.object_space import parse_object_spaces_with_resolved_ids  # noqa: E402
from onestore.object_data import parse_object_space_object_prop_set_from_ref  # noqa: E402
from onestore.file_data import (  # noqa: E402
    get_file_data_by_reference,
    parse_file_data_store_index,
    parse_file_data_store_object_from_ref,
)
from onestore.hashed_chunk_list import (  # noqa: E402
    parse_hashed_chunk_list_entries,
)
from onestore.summary import build_simpletable_summary  # noqa: E402
from onestore.parse_context import ParseContext  # noqa: E402
from onestore.txn_log import TransactionLogFragment  # noqa: E402
from onestore.txn_log import parse_transaction_log  # noqa: E402
from onestore.file_node_list import (  # noqa: E402
    parse_file_node_list,
    parse_file_node_list_nodes,
    parse_file_node_list_typed_nodes,
)
from onestore.file_node_types import (  # noqa: E402
    ObjectGroupListReferenceFND,
    ObjectGroupStartFND,
    ObjectDeclaration2LargeRefCountFND,
    ObjectDeclaration2RefCountFND,
    ReadOnlyObjectDeclaration2LargeRefCountFND,
    ReadOnlyObjectDeclaration2RefCountFND,
    RootObjectReference3FND,
    ObjectSpaceManifestListReferenceFND,
    ObjectSpaceManifestListStartFND,
    ObjectSpaceManifestRootFND,
    RevisionManifestListReferenceFND,
    RevisionManifestListStartFND,
    build_root_file_node_list_manifests,
)


def _simpletable_path() -> Path | None:
    p = ROOT / "testfiles" / "SimpleTable.one"
    return p if p.exists() else None


class TestIntegrationSimpleTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.simpletable = _simpletable_path()
        if cls.simpletable is None:
            raise unittest.SkipTest("SimpleTable.one not found")
        cls.data = cls.simpletable.read_bytes()

    def test_file_sanity(self) -> None:
        self.assertGreater(len(self.data), 1024)

    def test_crc32_whole_file_matches_known_vector(self) -> None:
        # Regression guard: if the fixture changes, this will change.
        self.assertEqual(crc32_rfc3309(self.data), 0x77B62BD6)

    def test_parse_header_and_basic_invariants(self) -> None:
        r = BinaryReader(self.data)
        header = Header.parse(r)

        self.assertEqual(header.file_format_uuid, GUID_FILE_FORMAT)
        self.assertEqual(header.file_type_uuid, GUID_FILE_TYPE_ONE)
        self.assertNotEqual(header.c_transactions_in_log, 0)
        self.assertEqual(header.grf_debug_log_flags, 0)

        self.assertFalse(header.fcr_transaction_log.is_zero())
        self.assertFalse(header.fcr_transaction_log.is_nil())
        self.assertFalse(header.fcr_file_node_list_root.is_zero())
        self.assertFalse(header.fcr_file_node_list_root.is_nil())

        # Bounds are enforced during parsing, but keep explicit guards in the test.
        self.assertLessEqual(header.fcr_transaction_log.stp + header.fcr_transaction_log.cb, len(self.data))
        self.assertLessEqual(
            header.fcr_file_node_list_root.stp + header.fcr_file_node_list_root.cb,
            len(self.data),
        )

    def test_parse_transaction_log_and_basic_invariants(self) -> None:
        r = BinaryReader(self.data)
        header = Header.parse(r)

        last_count_by_list_id = parse_transaction_log(BinaryReader(self.data), header)

        # Basic invariants only: avoid brittle fixture-specific expectations.
        self.assertIsInstance(last_count_by_list_id, dict)
        self.assertGreater(len(last_count_by_list_id), 0)
        for k, v in last_count_by_list_id.items():
            self.assertIsInstance(k, int)
            self.assertIsInstance(v, int)
            self.assertGreater(k, 0)
            self.assertGreater(v, 0)
            self.assertNotEqual(k, 1)

    def test_transaction_log_is_deterministic(self) -> None:
        header = Header.parse(BinaryReader(self.data))

        ctx1 = ParseContext(strict=True)
        ctx2 = ParseContext(strict=True)

        out1 = parse_transaction_log(BinaryReader(self.data), header, ctx1)
        out2 = parse_transaction_log(BinaryReader(self.data), header, ctx2)

        self.assertEqual(out1, out2)
        self.assertEqual(ctx1.file_size, len(self.data))
        self.assertEqual(ctx2.file_size, len(self.data))

    def test_transaction_log_fragment_chain_has_enough_commits(self) -> None:
        header = Header.parse(BinaryReader(self.data))
        file_size = len(self.data)

        # Walk the fragment chain defensively: bounded steps + loop detection.
        visited_stp: set[int] = set()
        sentinels = 0

        current = header.fcr_transaction_log
        for _ in range(2048):
            # Protect against cyclic references.
            if current.stp in visited_stp:
                raise AssertionError("Transaction log fragment chain contains a loop")
            visited_stp.add(current.stp)

            frag = TransactionLogFragment.parse(
                BinaryReader(self.data),
                current,
                ctx=ParseContext(strict=True, file_size=file_size),
            )
            sentinels += sum(1 for e in frag.entries if e.is_sentinel)

            # Stop at end of chain.
            if frag.next_fragment.is_zero() or frag.next_fragment.is_nil() or frag.next_fragment.cb == 0:
                break
            frag.next_fragment.validate_in_file(file_size)
            current = frag.next_fragment
        else:
            raise AssertionError("Transaction log fragment chain is unexpectedly long")

        # The file should contain at least the committed number of transaction sentinels.
        self.assertGreaterEqual(sentinels, header.c_transactions_in_log)

    def test_parse_root_file_node_list_basic_invariants(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data))
        ctx = ParseContext(strict=True, file_size=file_size)
        last_count_by_list_id = parse_transaction_log(BinaryReader(data), header, ctx)

        root_list = parse_file_node_list(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )

        self.assertGreaterEqual(root_list.list_id, 0x10)
        self.assertGreater(root_list.node_count, 0)
        self.assertGreaterEqual(len(root_list.fragments), 1)

        # Determinism: structure-only equality.
        root_list2 = parse_file_node_list(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )
        self.assertEqual(root_list.list_id, root_list2.list_id)
        self.assertEqual(root_list.node_count, root_list2.node_count)
        self.assertEqual(
            [(f.header.list_id, f.header.fragment_sequence, f.fcr.stp, f.fcr.cb) for f in root_list.fragments],
            [(f.header.list_id, f.header.fragment_sequence, f.fcr.stp, f.fcr.cb) for f in root_list2.fragments],
        )

    def test_parse_root_file_node_list_nodes_basic_invariants(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data))
        last_count_by_list_id = parse_transaction_log(
            BinaryReader(data),
            header,
            ParseContext(strict=True, file_size=file_size),
        )

        # Parse as typed nodes.
        ctx = ParseContext(strict=True, file_size=file_size)
        out = parse_file_node_list_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        self.assertGreaterEqual(out.list.list_id, 0x10)
        self.assertGreater(out.list.node_count, 0)
        self.assertEqual(len(out.nodes), out.list.node_count)

        # Basic invariants: sizes and bounds.
        for n in out.nodes:
            self.assertGreaterEqual(n.header.size, 4)
            self.assertLessEqual(n.header.offset + n.header.size, file_size)
            if n.header.base_type in (1, 2):
                self.assertIsNotNone(n.chunk_ref)
            elif n.header.base_type == 0:
                self.assertIsNone(n.chunk_ref)

        # Determinism: parsing twice yields same structure and same headers sequence.
        out2 = parse_file_node_list_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )

        self.assertEqual(out.list.list_id, out2.list.list_id)
        self.assertEqual(out.list.node_count, out2.list.node_count)
        self.assertEqual(
            [(n.header.file_node_id, n.header.size, n.header.base_type) for n in out.nodes],
            [(n.header.file_node_id, n.header.size, n.header.base_type) for n in out2.nodes],
        )

    def test_parse_root_file_node_list_typed_nodes_and_manifest_invariants(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data))
        last_count_by_list_id = parse_transaction_log(
            BinaryReader(data),
            header,
            ParseContext(strict=True, file_size=file_size),
        )

        ctx = ParseContext(strict=True, file_size=file_size)
        out = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ctx,
        )

        self.assertEqual(len(out.nodes), out.list.node_count)
        self.assertGreaterEqual(out.list.node_count, 1)

        # Root list MUST contain only allowed root list types (Step 8).
        for tn in out.nodes:
            self.assertIn(tn.node.header.file_node_id, (0x004, 0x008, 0x090))
            # If the fixture gains 0x090 later, the parser should handle it.
            if tn.node.header.file_node_id == 0x004:
                self.assertIsInstance(tn.typed, ObjectSpaceManifestRootFND)
            if tn.node.header.file_node_id == 0x008:
                self.assertIsInstance(tn.typed, ObjectSpaceManifestListReferenceFND)

        # MUST: root gosid must match one of object space refs.
        manifests = build_root_file_node_list_manifests(out.nodes, ctx=ctx)
        self.assertTrue(
            any(r.gosid == manifests.root.gosid_root for r in manifests.object_space_refs),
        )

        # Determinism: typed parse is stable.
        out2 = parse_file_node_list_typed_nodes(
            BinaryReader(data),
            header.fcr_file_node_list_root,
            last_count_by_list_id=last_count_by_list_id,
            ctx=ParseContext(strict=True, file_size=file_size),
        )
        self.assertEqual(
            [(tn.node.header.file_node_id, type(tn.typed).__name__ if tn.typed else None) for tn in out.nodes],
            [(tn.node.header.file_node_id, type(tn.typed).__name__ if tn.typed else None) for tn in out2.nodes],
        )

    def test_object_spaces_manifest_and_revision_list_links_end_to_end(self) -> None:
        data = self.data
        file_size = len(data)

        # End-to-end Step 9 parse should be deterministic.
        summary1 = parse_object_spaces_summary(data, ctx=ParseContext(strict=True, file_size=file_size))
        summary2 = parse_object_spaces_summary(data, ctx=ParseContext(strict=True, file_size=file_size))
        self.assertEqual(summary1, summary2)

        self.assertGreaterEqual(len(summary1.object_spaces), 1)

        # For per-object-space checks we re-parse lists and compare against the summary.
        header = Header.parse(BinaryReader(data))
        last_count_by_list_id = parse_transaction_log(
            BinaryReader(data),
            header,
            ParseContext(strict=True, file_size=file_size),
        )

        for os in summary1.object_spaces:
            # Parse object space manifest list.
            manifest_list = parse_file_node_list_typed_nodes(
                BinaryReader(data),
                FileChunkReference64x32(stp=os.manifest_list_ref.stp, cb=os.manifest_list_ref.cb),
                last_count_by_list_id=last_count_by_list_id,
                ctx=ParseContext(strict=True, file_size=file_size),
            )
            self.assertGreaterEqual(len(manifest_list.nodes), 1)
            self.assertIsInstance(manifest_list.nodes[0].typed, ObjectSpaceManifestListStartFND)
            assert isinstance(manifest_list.nodes[0].typed, ObjectSpaceManifestListStartFND)
            self.assertEqual(manifest_list.nodes[0].typed.gosid, os.gosid)

            # MUST: use the last RevisionManifestListReferenceFND in the list.
            rev_refs = [
                tn.typed.ref
                for tn in manifest_list.nodes
                if isinstance(tn.typed, RevisionManifestListReferenceFND)
            ]
            self.assertGreaterEqual(len(rev_refs), 1)
            self.assertEqual(rev_refs[-1], os.revision_manifest_list_ref)

            # Parse revision manifest list and check the start node gosid.
            rev_list = parse_file_node_list_typed_nodes(
                BinaryReader(data),
                FileChunkReference64x32(stp=os.revision_manifest_list_ref.stp, cb=os.revision_manifest_list_ref.cb),
                last_count_by_list_id=last_count_by_list_id,
                ctx=ParseContext(strict=True, file_size=file_size),
            )
            self.assertGreaterEqual(len(rev_list.nodes), 1)
            self.assertIsInstance(rev_list.nodes[0].typed, RevisionManifestListStartFND)
            assert isinstance(rev_list.nodes[0].typed, RevisionManifestListStartFND)
            self.assertEqual(rev_list.nodes[0].typed.gosid, os.gosid)

    def test_revision_manifest_list_parsing_step10_is_deterministic_and_valid(self) -> None:
        data = self.data
        file_size = len(data)

        out1 = parse_object_spaces_with_revisions(data, ctx=ParseContext(strict=True, file_size=file_size))
        out2 = parse_object_spaces_with_revisions(data, ctx=ParseContext(strict=True, file_size=file_size))
        self.assertEqual(out1, out2)

        self.assertGreaterEqual(len(out1.object_spaces), 1)

        for os in out1.object_spaces:
            # Revisions list itself is deterministic.
            self.assertIsInstance(os.revisions, tuple)

            # MUST: rid MUST NOT be zero and MUST be unique in list.
            seen: set[tuple[bytes, int]] = set()
            rid_order: list[tuple[bytes, int]] = []
            for rev in os.revisions:
                self.assertFalse(rev.rid.is_zero())
                key = (rev.rid.guid, int(rev.rid.n))
                self.assertNotIn(key, seen)
                seen.add(key)
                rid_order.append(key)

                # Dependency rule: if set, it must refer to an earlier revision in this list.
                if not rev.rid_dependent.is_zero():
                    dep_key = (rev.rid_dependent.guid, int(rev.rid_dependent.n))
                    self.assertIn(dep_key, seen)

                # Encryption marker rule: if odcsDefault indicates encrypted, marker must be present.
                if rev.odcs_default == 0x0002:
                    self.assertTrue(rev.has_encryption_marker)

                # Step 11: manifest content is present and deterministic.
                self.assertIsNotNone(rev.manifest)
                assert rev.manifest is not None

                # Root object refs are structural only; avoid fixture-specific expectations.
                self.assertIsInstance(rev.manifest.root_objects, tuple)
                for ro in rev.manifest.root_objects:
                    # SimpleTable.one is a .one file: RootObjectReference3FND is expected.
                    self.assertIsInstance(ro, RootObjectReference3FND)

                # Object group lists: if present, the referenced list should start with ObjectGroupStartFND
                # matching the ObjectGroupID.
                self.assertIsInstance(rev.manifest.object_groups, tuple)
                for grp in rev.manifest.object_groups:
                    self.assertIsInstance(grp.start_oid, ExtendedGUID)
                    self.assertEqual(grp.start_oid, grp.object_group_id)
                    self.assertIsInstance(grp.changes, tuple)

                # Global id table sequence (optional): ensure structural determinism.
                if rev.manifest.global_id_table is not None:
                    self.assertIsInstance(rev.manifest.global_id_table.ops, tuple)

                # Inline changes should normally be empty for .one; keep it non-brittle.
                self.assertIsInstance(rev.manifest.inline_changes, tuple)

            # MUST: last assignment wins for (context, role) pairs.
            # We validate internal consistency: each mapping points to an existing revision.
            for pair, rid in os.role_assignments:
                rid_key = (rid.guid, int(rid.n))
                self.assertIn(rid_key, seen)
                self.assertIsInstance(pair.revision_role, int)
                self.assertIsNotNone(pair.gctxid)

            # Determinism guard: assigned_pairs across revisions are stable and only reference declared mappings.
            mapping = {(p.gctxid.guid, int(p.gctxid.n), int(p.revision_role)): (r.guid, int(r.n)) for p, r in os.role_assignments}
            for rev in os.revisions:
                for ap in rev.assigned_pairs:
                    key = (ap.gctxid.guid, int(ap.gctxid.n), int(ap.revision_role))
                    self.assertIn(key, mapping)
                    self.assertEqual(mapping[key], (rev.rid.guid, int(rev.rid.n)))

            # Step 11 encryption consistency: if any manifest has 0x07C, all must.
            any_marker = any(r.has_encryption_marker for r in os.revisions)
            if any_marker:
                self.assertTrue(all(r.has_encryption_marker for r in os.revisions))

    def test_step11_resolved_ids_is_deterministic_and_structurally_valid(self) -> None:
        data = self.data
        file_size = len(data)

        out1 = parse_object_spaces_with_resolved_ids(data, ctx=ParseContext(strict=True, file_size=file_size))
        out2 = parse_object_spaces_with_resolved_ids(data, ctx=ParseContext(strict=True, file_size=file_size))
        self.assertEqual(out1, out2)

        self.assertGreaterEqual(len(out1.object_spaces), 1)

        for os in out1.object_spaces:
            # Revisions are deterministic and ordered as parsed.
            self.assertIsInstance(os.revisions, tuple)

            seen_rids: set[tuple[bytes, int]] = set()
            for rev in os.revisions:
                self.assertFalse(rev.rid.is_zero())
                rid_key = (rev.rid.guid, int(rev.rid.n))
                self.assertNotIn(rid_key, seen_rids)
                seen_rids.add(rid_key)

                # Dependency references must point to earlier revisions.
                if not rev.rid_dependent.is_zero():
                    dep_key = (rev.rid_dependent.guid, int(rev.rid_dependent.n))
                    self.assertIn(dep_key, seen_rids)

                # Effective table is stored deterministically (sorted by index).
                self.assertIsInstance(rev.effective_gid_table, tuple)
                last_idx = -1
                for idx, guid in rev.effective_gid_table:
                    self.assertIsInstance(idx, int)
                    self.assertGreaterEqual(idx, 0)
                    self.assertLess(idx, 0xFFFFFF)
                    self.assertGreater(idx, last_idx)
                    last_idx = idx
                    self.assertIsInstance(guid, (bytes, bytearray))
                    self.assertEqual(len(guid), 16)

                # Root objects are always resolvable to ExtendedGUID in strict mode.
                self.assertIsInstance(rev.resolved_root_objects, tuple)
                for role, oid in rev.resolved_root_objects:
                    self.assertIsInstance(role, int)
                    self.assertIsInstance(oid, ExtendedGUID)

                # If any CompactIDs were encountered in object changes, they were resolved to non-zero GUIDs.
                self.assertIsInstance(rev.resolved_change_oids, tuple)
                for oid in rev.resolved_change_oids:
                    self.assertIsInstance(oid, ExtendedGUID)
                    self.assertNotEqual(oid.guid, b"\x00" * 16)

    def test_step13_can_decode_some_object_prop_set_deterministically(self) -> None:
        data = self.data
        file_size = len(data)

        step10 = parse_object_spaces_with_revisions(data, ctx=ParseContext(strict=True, file_size=file_size))

        found = False

        for os in step10.object_spaces:
            for rev in os.revisions:
                if rev.manifest is None:
                    continue
                for grp in rev.manifest.object_groups:
                    for ch in grp.changes:
                        change = ch.change

                        ref = None
                        jcid = None

                        if isinstance(change, (ObjectDeclaration2RefCountFND, ObjectDeclaration2LargeRefCountFND)):
                            ref = change.ref
                            jcid = change.jcid
                        elif isinstance(
                            change,
                            (ReadOnlyObjectDeclaration2RefCountFND, ReadOnlyObjectDeclaration2LargeRefCountFND),
                        ):
                            ref = change.base.ref
                            jcid = change.base.jcid

                        if ref is None or jcid is None:
                            continue
                        if not jcid.is_property_set:
                            continue

                        try:
                            ps = parse_object_space_object_prop_set_from_ref(
                                data,
                                stp=int(ref.stp),
                                cb=int(ref.cb),
                                ctx=ParseContext(strict=True, file_size=file_size),
                            )
                            decoded1 = ps.decode_property_set(ctx=ParseContext(strict=True, file_size=file_size))
                            decoded2 = ps.decode_property_set(ctx=ParseContext(strict=True, file_size=file_size))
                        except OneStoreFormatError:
                            # Not all property-set JCIDs necessarily point to a decodable prop set in this step.
                            continue

                        self.assertEqual(decoded1, decoded2)
                        self.assertIsInstance(decoded1.properties, tuple)
                        found = True
                        break
                    if found:
                        break
                if found:
                    break
            if found:
                break

        self.assertTrue(found, "No decodable ObjectSpaceObjectPropSet found in fixture")

    def test_step14_file_data_store_index_and_ifndf_resolution(self) -> None:
        data = self.data
        file_size = len(data)

        idx1 = parse_file_data_store_index(data, ctx=ParseContext(strict=True, file_size=file_size))
        idx2 = parse_file_data_store_index(data, ctx=ParseContext(strict=True, file_size=file_size))
        self.assertEqual(idx1, idx2)

        if not idx1:
            raise unittest.SkipTest("No FileDataStoreListReferenceFND present in fixture")

        # Basic invariants: all refs are in-bounds and GUID keys are well-formed.
        for guid_le, ref in idx1.items():
            self.assertIsInstance(guid_le, (bytes, bytearray))
            self.assertEqual(len(guid_le), 16)
            self.assertGreater(int(ref.cb), 0)
            self.assertLessEqual(int(ref.stp) + int(ref.cb), file_size)

        # Pick one entry and ensure we can parse the FileDataStoreObject and resolve it via <ifndf>.
        guid_le, ref = next(iter(idx1.items()))
        obj = parse_file_data_store_object_from_ref(
            data,
            stp=int(ref.stp),
            cb=int(ref.cb),
            ctx=ParseContext(strict=True, file_size=file_size),
        )
        self.assertEqual(len(obj.file_data), obj.cb_length)

        guid_text = str(uuid.UUID(bytes_le=guid_le)).lower()
        reference = f"<ifndf>{{{guid_text}}}</ifndf>"
        resolved = get_file_data_by_reference(
            data,
            reference,
            ctx=ParseContext(strict=True, file_size=file_size),
            index=idx1,
        )
        self.assertEqual(resolved, obj.file_data)

    def test_step15_hashed_chunk_list_is_deterministic_and_in_bounds(self) -> None:
        data = self.data
        file_size = len(data)

        header = Header.parse(BinaryReader(data), ctx=ParseContext(strict=True, file_size=file_size))
        if header.fcr_hashed_chunk_list.is_zero() or header.fcr_hashed_chunk_list.is_nil():
            raise unittest.SkipTest("No hashed chunk list in fixture")

        entries1 = parse_hashed_chunk_list_entries(data, ctx=ParseContext(strict=True, file_size=file_size))
        entries2 = parse_hashed_chunk_list_entries(data, ctx=ParseContext(strict=True, file_size=file_size))
        self.assertEqual(entries1, entries2)

        # Basic structural invariants only.
        self.assertIsInstance(entries1, tuple)
        self.assertGreaterEqual(len(entries1), 1)

        for e in entries1:
            self.assertGreaterEqual(int(e.stp), 0)
            self.assertGreater(int(e.cb), 0)
            self.assertLessEqual(int(e.stp) + int(e.cb), file_size)
            self.assertIsInstance(e.md5, (bytes, bytearray))
            self.assertEqual(len(e.md5), 16)

        # Optional: validate MD5 for a single entry to avoid heavy work.
        _ = parse_hashed_chunk_list_entries(
            data,
            ctx=ParseContext(strict=True, file_size=file_size),
            validate_md5=True,
        )

    def test_step16_simpletable_snapshot_summary_matches(self) -> None:
        data = self.data
        file_size = len(data)
        snap_path = ROOT / "tests" / "snapshots" / "simpletable_summary.json"
        if not snap_path.exists():
            raise unittest.SkipTest("Snapshot file missing: tests/snapshots/simpletable_summary.json")

        current = build_simpletable_summary(data, ctx=ParseContext(strict=True, file_size=file_size)).data
        expected = json.loads(snap_path.read_text(encoding="utf-8"))

        self.assertEqual(current, expected)

    def test_binary_reader_view_matches_slices(self) -> None:
        r = BinaryReader(self.data)
        prefix = r.peek_bytes(64)
        self.assertEqual(prefix, self.data[:64])

        v = r.view(0, 64)
        self.assertEqual(v.read_bytes(64), self.data[:64])

        # Nested view: bytes[16:32]
        vv = r.view(0, 64).view(16, 16)
        self.assertEqual(vv.read_bytes(16), self.data[16:32])

        # Out of bounds view should fail
        with self.assertRaises(OneStoreFormatError):
            r.view(len(self.data) - 4, 16)

    def test_extended_guid_parses_from_file_bytes(self) -> None:
        # We don't assume semantic meaning; just validate parser works on real bytes.
        eg = ExtendedGUID.parse(BinaryReader(self.data).view(0, 20))
        s = eg.as_str()
        self.assertEqual(len(s), 36)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", s))

    def test_parse_filenode_chunk_reference_from_file_bytes(self) -> None:
        # Use an arbitrary offset where we can safely read 12 bytes.
        if len(self.data) < 0x200 + 12:
            raise unittest.SkipTest("Fixture too small for this probe")
        r = BinaryReader(self.data).view(0x200, 12)
        ref = parse_filenode_chunk_reference(r, stp_format=0, cb_format=0)
        self.assertIsInstance(ref.stp, int)
        self.assertIsInstance(ref.cb, int)
        self.assertEqual(r.remaining(), 0)

    def test_find_and_parse_string_in_storage_buffer_somewhere(self) -> None:
        # Heuristic scan: find a small cch so that UTF-16LE decode works strictly.
        data = self.data
        scan_limit = min(len(data) - 8, 64 * 1024)

        for off in range(0, scan_limit, 2):
            r = BinaryReader(data).view(off, scan_limit - off)
            try:
                cch = r.read_u32()
            except OneStoreFormatError:
                break

            if not (1 <= cch <= 64):
                continue

            needed = cch * 2
            if r.remaining() < needed:
                continue

            try:
                sib = StringInStorageBuffer.parse(BinaryReader(data).view(off, 4 + needed))
                decoded = sib.decode()
            except (UnicodeDecodeError, OneStoreFormatError):
                continue

            self.assertEqual(len(decoded), cch)
            return

        raise unittest.SkipTest("No decodable StringInStorageBuffer found in scan window")

    def test_find_plausible_fcr32_and_validate_bounds(self) -> None:
        # Heuristic scan: locate a pair (stp,cb) that points inside the file.
        data = self.data
        file_size = len(data)
        scan_limit = min(len(data) - 8, 256 * 1024)

        for off in range(0, scan_limit, 4):
            r = BinaryReader(data).view(off, 8)
            stp = r.read_u32()
            cb = r.read_u32()

            # Skip sentinel-ish values and require a non-empty in-file region.
            if cb == 0 or stp == 0 or stp == 0xFFFFFFFF:
                continue
            if stp + cb > file_size:
                continue

            fcr = FileChunkReference32.parse(BinaryReader(data).view(off, 8))
            fcr.validate_in_file(file_size)
            return

        raise unittest.SkipTest("No plausible FileChunkReference32 found in scan window")
