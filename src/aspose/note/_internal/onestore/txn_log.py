from __future__ import annotations

from dataclasses import dataclass

from .chunk_refs import FileChunkReference64x32
from .errors import OneStoreFormatError
from .header import Header
from .io import BinaryReader
from .parse_context import ParseContext


@dataclass(frozen=True, slots=True)
class TransactionEntry:
    src_id: int
    value: int
    offset: int

    @property
    def is_sentinel(self) -> bool:
        return self.src_id == 0x00000001


@dataclass(frozen=True, slots=True)
class TransactionLogFragment:
    fcr: FileChunkReference64x32
    entries: tuple[TransactionEntry, ...]
    next_fragment: FileChunkReference64x32

    @classmethod
    def parse(
        cls,
        reader: BinaryReader,
        fcr: FileChunkReference64x32,
        *,
        ctx: ParseContext | None = None,
    ) -> "TransactionLogFragment":
        if ctx is None:
            ctx = ParseContext(strict=True)

        if reader.bounds.start != 0:
            raise OneStoreFormatError(
                "TransactionLogFragment must be parsed from file start",
                offset=reader.bounds.start,
            )

        file_size = reader.bounds.end
        if ctx.file_size is None:
            ctx.file_size = file_size
        else:
            file_size = ctx.file_size

        fcr.validate_in_file(file_size)

        if fcr.cb < 12:
            raise OneStoreFormatError("TransactionLogFragment too small", offset=fcr.stp)

        # The spec defines: sizeTable (N * 8 bytes) + nextFragment (12 bytes).
        # In practice, the referenced chunk size can include trailing padding bytes.
        padding = (fcr.cb - 12) % 8
        size_table_size = fcr.cb - 12 - padding
        if size_table_size < 0 or (size_table_size % 8) != 0:
            raise OneStoreFormatError(
                "TransactionLogFragment sizeTable length is not a multiple of TransactionEntry size",
                offset=fcr.stp,
            )

        r = reader.view(fcr.stp, fcr.cb)

        entries: list[TransactionEntry] = []
        while r.tell_relative() < size_table_size:
            entry_off = r.tell()
            src_id = r.read_u32()
            value = r.read_u32()
            entries.append(TransactionEntry(src_id=src_id, value=value, offset=entry_off))

        # nextFragment is immediately after sizeTable.
        if r.tell_relative() != size_table_size:
            raise OneStoreFormatError("TransactionLogFragment sizeTable parse mismatch", offset=r.tell())

        next_fragment = FileChunkReference64x32.parse(r)

        # Ignore any trailing padding bytes.
        if r.remaining() != padding:
            raise OneStoreFormatError("TransactionLogFragment padding size mismatch", offset=r.tell())
        if padding:
            r.skip(padding)

        return cls(fcr=fcr, entries=tuple(entries), next_fragment=next_fragment)


def parse_transaction_log(
    reader: BinaryReader,
    header: Header,
    ctx: ParseContext | None = None,
) -> dict[int, int]:
    """Parse the Transaction Log (2.3.3) and return last committed counts.

    Returns:
        last_count_by_list_id: mapping FileNodeListID (srcID) -> last committed count.

    Parsing rules:
    - The stream is split into transactions by sentinel entries (srcID == 1).
    - Only the first header.c_transactions_in_log transactions are applied.
    - Once the required number of transactions is reached, nextFragment MUST be ignored.

    Any out-of-bounds reads raise OneStoreFormatError with an absolute offset.
    """

    if ctx is None:
        ctx = ParseContext(strict=True)

    if header.c_transactions_in_log == 0:
        raise OneStoreFormatError("cTransactionsInLog MUST NOT be 0", offset=96)

    if reader.bounds.start != 0:
        raise OneStoreFormatError("TransactionLog must be parsed from file start", offset=reader.bounds.start)

    file_size = reader.bounds.end
    if ctx.file_size is None:
        ctx.file_size = file_size
    else:
        file_size = ctx.file_size

    # Ensure initial reference is within file (Header.parse already enforces this, but keep local guard).
    header.fcr_transaction_log.validate_in_file(file_size)

    txn_limit = int(header.c_transactions_in_log)
    committed_txns = 0

    last_count_by_list_id: dict[int, int] = {}
    pending_updates: dict[int, int] = {}

    current_fcr = header.fcr_transaction_log

    while True:
        frag = TransactionLogFragment.parse(reader, current_fcr, ctx=ctx)

        for entry in frag.entries:
            if entry.is_sentinel:
                if committed_txns < txn_limit:
                    last_count_by_list_id.update(pending_updates)
                pending_updates = {}
                committed_txns += 1

                if committed_txns >= txn_limit:
                    # Reached the required number of transactions: MUST ignore nextFragment.
                    return last_count_by_list_id
                continue

            # Non-sentinel entry: srcID is FileNodeListID.
            if entry.value == 0:
                # Spec says non-sentinel entries MUST add >=1 FileNode, but real files may contain
                # no-op updates. Keep parsing deterministic; warn and ignore.
                ctx.warn("TransactionEntrySwitch is 0 for non-sentinel entry; ignoring", offset=entry.offset)
                continue

            if committed_txns < txn_limit:
                pending_updates[entry.src_id] = entry.value

        if committed_txns >= txn_limit:
            return last_count_by_list_id

        # Follow chain.
        if frag.next_fragment.is_zero() or frag.next_fragment.is_nil() or frag.next_fragment.cb == 0:
            break

        # Only validate and follow nextFragment if we still need more transactions.
        frag.next_fragment.validate_in_file(file_size)
        current_fcr = frag.next_fragment

    # If the log ends without a final sentinel, pending updates are not committed.
    return last_count_by_list_id
