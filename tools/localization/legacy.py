"""Bounded PE/RT_STRING reader. Never loads or executes DLL code; stdlib only."""

from pathlib import Path
import hashlib
import struct

from .parser import Entry, Issue, ParsedFile


class PEError(ValueError):
    """Unsupported or malformed PE resource data; no speculative recovery."""


class PEReader:
    def __init__(self, data: bytes):
        self.data = data
        if self.take(0, 2) != b'MZ':
            raise PEError('Missing DOS MZ signature')
        pe = self.unpack('<I', 0x3c)[0]
        if self.take(pe, 4) != b'PE\0\0':
            raise PEError('Missing PE signature')
        self.machine, count = self.unpack('<HH', pe + 4)
        optional_size, characteristics = self.unpack('<HH', pe + 20)
        if not characteristics & 0x2000:
            raise PEError('PE image is not marked as a DLL')
        optional = pe + 24
        self.take(optional, optional_size)
        magic = self.unpack('<H', optional)[0]
        if magic not in (0x10b, 0x20b):
            raise PEError(f'Unsupported optional header magic: {magic:#x}')
        self.pe_kind = 'PE32' if magic == 0x10b else 'PE32+'
        directory_start = 96 if magic == 0x10b else 112
        if optional_size < directory_start + 24:
            raise PEError('Optional header has no resource directory entry')
        if self.unpack('<I', optional + directory_start - 4)[0] < 3:
            raise PEError('Resource data directory is absent')
        self.resource_rva, self.resource_size = self.unpack('<II', optional + directory_start + 16)
        if not self.resource_rva or not self.resource_size:
            raise PEError('Resource data directory is empty')
        self.header_size = self.unpack('<I', optional + 60)[0]
        self.sections = []
        section_start = optional + optional_size
        self.take(section_start, count * 40)
        for index in range(count):
            offset = section_start + index * 40
            virtual_size, rva, raw_size, raw_offset = self.unpack('<IIII', offset + 8)
            self.sections.append((rva, raw_size, raw_offset))
        # Validate the declared resource range before following relative pointers.
        self.rva_offset(self.resource_rva, self.resource_size)

    def take(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise PEError(f'File bounds exceeded at offset {offset:#x}, size {size}')
        return self.data[offset:offset + size]

    def unpack(self, fmt: str, offset: int) -> tuple:
        return struct.unpack(fmt, self.take(offset, struct.calcsize(fmt)))

    def rva_offset(self, rva: int, size: int) -> int:
        candidates = []
        if rva < self.header_size and rva + size <= self.header_size:
            candidates.append(rva)
        for base, raw_size, raw_offset in self.sections:
            if base <= rva and rva + size <= base + raw_size:
                candidates.append(raw_offset + rva - base)
        if len(candidates) != 1:
            raise PEError(f'RVA {rva:#x}, size {size} has {len(candidates)} raw-file mappings')
        self.take(candidates[0], size)
        return candidates[0]

    def resource_offset(self, relative: int, size: int) -> int:
        if relative < 0 or relative + size > self.resource_size:
            raise PEError(f'Resource bounds exceeded at relative offset {relative:#x}')
        return self.rva_offset(self.resource_rva + relative, size)

    def directory(self, relative: int) -> list[tuple[int | str, int]]:
        offset = self.resource_offset(relative, 16)
        named, numbered = self.unpack('<HH', offset + 12)
        offset = self.resource_offset(relative + 16, (named + numbered) * 8)
        entries = []
        for index in range(named + numbered):
            name, target = self.unpack('<II', offset + index * 8)
            if name & 0x80000000:
                string_offset = name & 0x7fffffff
                length = self.unpack('<H', self.resource_offset(string_offset, 2))[0]
                start = self.resource_offset(string_offset + 2, length * 2)
                name = self.take(start, length * 2).decode('utf-16-le', errors='strict')
            entries.append((name, target))
        # Preserve duplicate directory entries, including multiple language leaves.
        return entries

    @staticmethod
    def branch(target: int, ancestors: tuple[int, ...]) -> int:
        if not target & 0x80000000:
            raise PEError('Expected resource directory, found data leaf')
        relative = target & 0x7fffffff
        if relative in ancestors:
            raise PEError('Cyclic resource directory')
        return relative

    def strings(self, path: str, generation: str) -> tuple[list[Entry], list[Entry], dict]:
        entries, empty = [], []
        block_count = 0
        language_ids = set()
        root = self.directory(0)
        found = False
        for resource_type, target in root:
            if resource_type != 6:  # RT_STRING; other resource types are not strings.
                continue
            found = True
            type_dir = self.branch(target, (0,))
            for block, target in self.directory(type_dir):
                if not isinstance(block, int) or not 1 <= block <= 0xffff:
                    raise PEError(f'Unsupported STRINGTABLE block identifier: {block!r}')
                block_dir = self.branch(target, (0, type_dir))
                for langid, leaf in self.directory(block_dir):
                    if not isinstance(langid, int) or not 0 <= langid <= 0xffff:
                        raise PEError(f'Unsupported resource language identifier: {langid!r}')
                    if leaf & 0x80000000:
                        raise PEError('Expected language data leaf, found extra directory level')
                    leaf_offset = self.resource_offset(leaf, 16)
                    rva, size, codepage, reserved = self.unpack('<IIII', leaf_offset)
                    offset = self.rva_offset(rva, size)
                    # STRINGTABLE payload must be within the declared resource data.
                    self.resource_offset(rva - self.resource_rva, size)
                    payload = self.take(offset, size)
                    pos = 0
                    block_count += 1
                    language_ids.add(langid)
                    for slot in range(16):
                        start = pos
                        if pos + 2 > size:
                            raise PEError(f'Truncated STRINGTABLE length at file offset {offset + pos:#x}')
                        length = struct.unpack_from('<H', payload, pos)[0]
                        pos += 2
                        if pos + length * 2 > size:
                            raise PEError(f'Truncated STRINGTABLE value at file offset {offset + pos:#x}')
                        value = payload[pos:pos + length * 2].decode('utf-16-le', errors='strict')
                        pos += length * 2
                        resource = dict(type_id=6, block_id=block, slot=slot, language_id=langid,
                                        codepage=codepage, data_entry_offset=leaf_offset,
                                        block_offset=offset, byte_offset=offset + start,
                                        length_utf16=length, zero_length=not length)
                        language = {0x411: 'jp', 0x409: 'en'}.get(langid, f'langid:{langid:#06x}')
                        entry = Entry(str((block - 1) * 16 + slot), value, path, None,
                                      generation=generation, language=language, resource=resource,
                                      value_format='utf16_resource')
                        (entries if length else empty).append(entry)
                    if pos != size:
                        raise PEError(f'Unexpected bytes after 16 STRINGTABLE slots at {offset + pos:#x}')
        if not found or not block_count:
            raise PEError('No RT_STRING language blocks found')
        return entries, empty, dict(pe_kind=self.pe_kind, machine=self.machine,
                                   resource_types=[name for name, _ in root],
                                   string_blocks=block_count, language_ids=sorted(language_ids),
                                   slots=block_count * 16)


def parse_legacy_bytes(data: bytes, path: str = '<memory>', generation: str = 'aok') -> ParsedFile:
    result = ParsedFile(path, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), format='pe_rt_string')
    try:
        entries, empty, metadata = PEReader(data).strings(path, generation)
    except (PEError, UnicodeDecodeError) as exc:
        # Atomic rejection: no partial extraction may look like a complete dataset.
        result.issues.append(Issue('pe_error', path, 0, str(exc)))
    else:
        result.entries, result.empty_slots, result.metadata = entries, empty, metadata
        result.metadata['generation'] = generation
    return result


def parse_legacy_file(path: Path, generation: str, label: str | None = None) -> ParsedFile:
    return parse_legacy_bytes(path.read_bytes(), label or path.as_posix(), generation)
