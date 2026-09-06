"""Build tiny synthetic resource-only PE images; contains no game data or code."""

import struct


def make_pe(resources=None, pe_plus=False):
    """resources: [(block_id, LANGID, {slot: str}), ...]; duplicates allowed."""
    resources = resources if resources is not None else [(1, 0x411, {1: 'Example'})]
    resource = bytearray()

    def allocate(size):
        offset = len(resource)
        resource.extend(bytes(size))
        return offset

    def directory(items):
        offset = allocate(16 + 8 * len(items))
        struct.pack_into('<HH', resource, offset + 12, 0, len(items))
        for index, (key, target) in enumerate(items):
            struct.pack_into('<II', resource, offset + 16 + 8 * index, key, target)
        return offset

    root = directory([(6, 0)])
    types = directory([(block, 0) for block, _, _ in resources])
    struct.pack_into('<I', resource, root + 20, types | 0x80000000)
    for index, (block, langid, values) in enumerate(resources):
        branch = directory([(langid, 0)])
        struct.pack_into('<I', resource, types + 20 + index * 8, branch | 0x80000000)
        leaf = allocate(16)
        struct.pack_into('<I', resource, branch + 20, leaf)
        payload = b''
        for slot in range(16):
            encoded = values.get(slot, '').encode('utf-16-le')
            payload += struct.pack('<H', len(encoded) // 2) + encoded
        payload_offset = allocate(len(payload))
        resource[payload_offset:payload_offset + len(payload)] = payload
        struct.pack_into('<IIII', resource, leaf, 0x1000 + payload_offset, len(payload), 0, 0)

    optional_size = 240 if pe_plus else 224
    image = bytearray(0x200)
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 0x3c, 0x80)
    image[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', image, 0x84, 0x8664 if pe_plus else 0x14c, 1)
    struct.pack_into('<HH', image, 0x94, optional_size, 0x2002)
    optional = 0x98
    struct.pack_into('<H', image, optional, 0x20b if pe_plus else 0x10b)
    struct.pack_into('<I', image, optional + 60, 0x200)
    directories = 112 if pe_plus else 96
    struct.pack_into('<I', image, optional + directories - 4, 16)
    struct.pack_into('<II', image, optional + directories + 16, 0x1000, len(resource))
    section = optional + optional_size
    image[section:section + 8] = b'.rsrc\0\0\0'
    struct.pack_into('<IIII', image, section + 8, len(resource), 0x1000, len(resource), 0x200)
    return bytes(image + resource)
