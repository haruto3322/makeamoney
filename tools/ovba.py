"""MS-OVBA compression and MS-CFB container writer (minimal, from scratch)."""
import struct
from math import ceil, log2


# ---------------------------------------------------------------------------
# MS-OVBA 2.4.1 compression
# ---------------------------------------------------------------------------
def _copytoken_help(diff):
    bit_count = max(int(ceil(log2(diff))), 4)
    length_mask = 0xFFFF >> bit_count
    offset_mask = (~length_mask) & 0xFFFF
    maximum_length = (0xFFFF >> bit_count) + 3
    return length_mask, offset_mask, bit_count, maximum_length


def _match(data, pos, chunk_start):
    best_len, best_off = 0, 0
    _, _, _, _ = 0, 0, 0, 0
    # candidate offsets from 1 .. pos-chunk_start
    max_back = pos - chunk_start
    for cand in range(1, max_back + 1):
        start = pos - cand
        length = 0
        while pos + length < len(data) and data[start + length] == data[pos + length]:
            length += 1
            # length capped later by maximum_length
            if length >= 4118:
                break
        if length > best_len:
            best_len = length
            best_off = cand
    return best_len, best_off


def _compress_chunk(chunk):
    tokens = bytearray()
    pos = 0
    n = len(chunk)
    while pos < n:
        flag_index = len(tokens)
        tokens.append(0)
        flags = 0
        for bit in range(8):
            if pos >= n:
                break
            diff = pos  # chunk_start = 0
            if diff == 0:
                # first byte must be literal
                tokens.append(chunk[pos])
                pos += 1
                continue
            length_mask, offset_mask, bit_count, max_len = _copytoken_help(diff)
            best_len, best_off = _match(chunk, pos, 0)
            if best_len > max_len:
                best_len = max_len
            if best_off > 0 and best_len >= 3:
                temp1 = best_off - 1
                temp2 = 16 - bit_count
                temp3 = best_len - 3
                token = (temp1 << temp2) | temp3
                tokens += struct.pack('<H', token & 0xFFFF)
                flags |= (1 << bit)
                pos += best_len
            else:
                tokens.append(chunk[pos])
                pos += 1
        tokens[flag_index] = flags
    return bytes(tokens)


def compress(data):
    out = bytearray([0x01])  # SignatureByte
    i = 0
    while i < len(data):
        chunk = data[i:i + 4096]
        i += 4096
        comp = _compress_chunk(chunk)
        if len(comp) < len(chunk):
            size_field = (len(comp) - 1) & 0x0FFF
            header = 0x8000 | 0x3000 | size_field
            out += struct.pack('<H', header)
            out += comp
        else:
            raw = bytearray(chunk)
            if len(raw) < 4096:
                raw += b'\x00' * (4096 - len(raw))
            size_field = 0x0FFF
            header = 0x3000 | size_field
            out += struct.pack('<H', header)
            out += raw
    return bytes(out)


def decompress(data):
    assert data[0] == 0x01
    out = bytearray()
    i = 1
    while i < len(data):
        header = struct.unpack('<H', data[i:i + 2])[0]
        i += 2
        size = (header & 0x0FFF) + 3
        compressed = (header & 0x8000) != 0
        chunk = data[i:i + size - 2]
        i += size - 2
        if not compressed:
            out += chunk[:4096]
            continue
        cs = len(out)  # decompressed chunk start
        p = 0
        chunk_out = bytearray()
        while p < len(chunk):
            flags = chunk[p]
            p += 1
            for bit in range(8):
                if p >= len(chunk):
                    break
                if flags & (1 << bit):
                    token = struct.unpack('<H', chunk[p:p + 2])[0]
                    p += 2
                    diff = len(chunk_out)
                    _, _, bit_count, _ = _copytoken_help(diff if diff else 1)
                    length_bits = 16 - bit_count
                    length = (token & ((1 << length_bits) - 1)) + 3
                    offset = (token >> length_bits) + 1
                    start = len(chunk_out) - offset
                    for k in range(length):
                        chunk_out.append(chunk_out[start + k])
                else:
                    chunk_out.append(chunk[p])
                    p += 1
        out += chunk_out
    return bytes(out)


# ---------------------------------------------------------------------------
# MS-CFB compound file writer
# ---------------------------------------------------------------------------
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD


class Entry:
    def __init__(self, name, etype):
        self.name = name
        self.type = etype  # 1 storage, 2 stream, 5 root
        self.color = 1     # black
        self.left = FREESECT
        self.right = FREESECT
        self.child = FREESECT
        self.clsid = b'\x00' * 16
        self.start = 0
        self.size = 0
        self.data = b''
        self.children = []  # build-time only


def _cmp_name(a, b):
    if len(a) != len(b):
        return len(a) - len(b)
    au = a.upper()
    bu = b.upper()
    if au < bu:
        return -1
    if au > bu:
        return 1
    return 0


def _build_bst(names_entries):
    """names_entries: list of Entry. Return root index into entries after
    assigning left/right. Balanced BST from sorted list."""
    ordered = sorted(names_entries, key=_CmpKey)

    def build(lo, hi):
        if lo > hi:
            return None
        mid = (lo + hi) // 2
        node = ordered[mid]
        node._l = build(lo, mid - 1)
        node._r = build(mid + 1, hi)
        return node

    root = build(0, len(ordered) - 1)
    return root


import functools


@functools.total_ordering
class _CmpKey:
    def __init__(self, entry):
        self.e = entry

    def __eq__(self, other):
        return _cmp_name(self.e.name, other.e.name) == 0

    def __lt__(self, other):
        return _cmp_name(self.e.name, other.e.name) < 0


class CFB:
    def __init__(self):
        self.root = Entry('Root Entry', 5)

    def add_stream(self, storage_path, name, data):
        parent = self._ensure_storage(storage_path)
        e = Entry(name, 2)
        e.data = data
        e.size = len(data)
        parent.children.append(e)
        return e

    def add_storage(self, storage_path):
        return self._ensure_storage(storage_path)

    def _ensure_storage(self, path):
        if path in ('', '/', None):
            return self.root
        cur = self.root
        for part in path.strip('/').split('/'):
            found = None
            for c in cur.children:
                if c.name == part and c.type == 1:
                    found = c
                    break
            if not found:
                found = Entry(part, 1)
                cur.children.append(found)
            cur = found
        return cur

    def _flatten(self):
        """Assign directory ids and build sibling BSTs. Returns list of entries
        in id order (root first)."""
        entries = [self.root]

        def assign(entry):
            # set child pointer via BST of its children
            if entry.children:
                root_child = _build_bst(entry.children)
                entry.child = None  # placeholder -> set id later
                entry._child_node = root_child
            else:
                entry._child_node = None
            for c in entry.children:
                entries.append(c)
            for c in entry.children:
                assign(c)

        assign(self.root)
        # assign ids
        for idx, e in enumerate(entries):
            e._id = idx
        # now resolve left/right/child ids
        for e in entries:
            node = getattr(e, '_child_node', None)
            e.child = node._id if node is not None else FREESECT
            if hasattr(e, '_l'):
                pass
        for e in entries:
            for c in e.children:
                c.left = c._l._id if getattr(c, '_l', None) is not None else FREESECT
                c.right = c._r._id if getattr(c, '_r', None) is not None else FREESECT
        return entries

    def write(self):
        SECTOR = 512
        MINISECTOR = 64
        MINICUTOFF = 4096
        entries = self._flatten()

        # 1. Separate streams into mini vs regular; build mini stream + minifat
        mini_stream = bytearray()
        minifat = []  # list of next-pointers (per mini sector)
        for e in entries:
            if e.type == 2:
                if e.size < MINICUTOFF and e.size > 0:
                    start = len(mini_stream) // MINISECTOR
                    d = e.data
                    nsec = (len(d) + MINISECTOR - 1) // MINISECTOR
                    padded = d + b'\x00' * (nsec * MINISECTOR - len(d))
                    mini_stream += padded
                    for k in range(nsec):
                        if k < nsec - 1:
                            minifat.append(len(minifat) + 1)
                        else:
                            minifat.append(ENDOFCHAIN)
                    e.start = start
                elif e.size == 0:
                    e.start = ENDOFCHAIN
                    e.size = 0
                # regular streams handled later
        # pad mini_stream to full sectors (512)
        # regular data sectors: assign for large streams + minifat container? No,
        # mini stream itself is stored as a regular chained stream owned by root.

        # 2. Layout of regular sectors:
        # We need: FAT sectors, directory stream, minifat stream, mini stream
        # container, and each large stream.
        # Build a list of "objects" needing regular sectors: directory, minifat,
        # ministream, large streams. Then compute FAT.

        # Directory stream bytes
        def dir_entry_bytes(e):
            nm = e.name.encode('utf-16-le')
            nm += b'\x00\x00'  # null term
            if len(nm) > 64:
                raise ValueError('name too long: ' + e.name)
            name_len = len(nm)
            nm = nm + b'\x00' * (64 - len(nm))
            b = bytearray()
            b += nm
            b += struct.pack('<H', name_len)
            b += struct.pack('<B', e.type)
            b += struct.pack('<B', e.color)
            b += struct.pack('<I', e.left & 0xFFFFFFFF)
            b += struct.pack('<I', e.right & 0xFFFFFFFF)
            b += struct.pack('<I', e.child & 0xFFFFFFFF)
            b += e.clsid
            b += struct.pack('<I', 0)  # state bits
            b += struct.pack('<Q', 0)  # ctime
            b += struct.pack('<Q', 0)  # mtime
            b += struct.pack('<I', e.start & 0xFFFFFFFF)
            b += struct.pack('<Q', e.size)
            assert len(b) == 128
            return bytes(b)

        # placeholder; root start/size set after mini stream sizing
        # Root entry: start = first sector of mini stream container, size = len(mini_stream)
        self.root.size = len(mini_stream)

        # We must lay out regular sectors and know start sectors before writing
        # directory (since dir contains start sectors). Do a two-pass.

        # Regular chained objects in order: [directory][minifat][ministream][large streams...]
        # Compute sizes in sectors.
        def nsectors(nbytes):
            return (nbytes + SECTOR - 1) // SECTOR if nbytes > 0 else 0

        # minifat bytes
        minifat_bytes = b''.join(struct.pack('<I', x & 0xFFFFFFFF) for x in minifat)
        # pad minifat to sector
        if minifat_bytes:
            pad = nsectors(len(minifat_bytes)) * SECTOR - len(minifat_bytes)
            minifat_bytes += b'\xff' * pad  # free-fill

        # mini stream padded to sector multiple
        mini_padded = bytes(mini_stream)
        if mini_padded:
            pad = nsectors(len(mini_padded)) * SECTOR - len(mini_padded)
            mini_padded += b'\x00' * pad

        # large streams
        large = [e for e in entries if e.type == 2 and e.size >= MINICUTOFF]

        # directory bytes: 4 entries per sector
        dir_count = len(entries)
        dir_sectors = (dir_count + 3) // 4

        # Assign sectors sequentially; FAT sectors interleaved requires iterative
        # solve because number of FAT sectors depends on total sectors.
        # Data sectors (non-FAT): directory + minifat + ministream + large streams
        data_sectors = dir_sectors + nsectors(len(minifat_bytes)) + nsectors(len(mini_padded))
        for e in large:
            data_sectors += nsectors(e.size)

        # iterate to find fat_sectors count
        fat_sectors = 1
        while True:
            total = data_sectors + fat_sectors
            need = (total + 127) // 128  # 128 FAT entries per sector
            if need <= fat_sectors:
                break
            fat_sectors = need

        total_sectors = data_sectors + fat_sectors

        # Assign sector numbers. Layout: FAT sectors first, then data sectors.
        fat_start = 0
        data_start = fat_sectors
        # positions
        cur = data_start
        dir_first = cur
        cur += dir_sectors
        minifat_first = cur if minifat_bytes else ENDOFCHAIN
        cur += nsectors(len(minifat_bytes))
        mini_first = cur if mini_padded else ENDOFCHAIN
        cur += nsectors(len(mini_padded))
        # large stream starts
        for e in large:
            e.start = cur
            cur += nsectors(e.size)

        # root start = mini_first
        self.root.start = mini_first if mini_padded else ENDOFCHAIN

        # Build FAT
        fat = [FREESECT] * total_sectors
        # FAT sectors mark themselves
        for s in range(fat_start, fat_start + fat_sectors):
            fat[s] = FATSECT

        def chain(first, count):
            for k in range(count):
                s = first + k
                if k < count - 1:
                    fat[s] = first + k + 1
                else:
                    fat[s] = ENDOFCHAIN

        chain(dir_first, dir_sectors)
        if minifat_bytes:
            chain(minifat_first, nsectors(len(minifat_bytes)))
        if mini_padded:
            chain(mini_first, nsectors(len(mini_padded)))
        for e in large:
            chain(e.start, nsectors(e.size))

        # directory bytes now (start sectors known)
        dir_bytes = bytearray()
        for e in entries:
            dir_bytes += dir_entry_bytes(e)
        # pad directory to sector; fill extra entries as free (type 0, name empty)
        pad_entries = dir_sectors * 4 - dir_count
        for _ in range(pad_entries):
            fe = Entry('', 0)
            fe.left = FREESECT
            fe.right = FREESECT
            fe.child = FREESECT
            fe.start = 0
            fe.size = 0
            fe.color = 0
            dir_bytes += dir_entry_bytes(fe)

        # FAT bytes
        fat_bytes = b''.join(struct.pack('<I', x & 0xFFFFFFFF) for x in fat)
        pad = fat_sectors * 128 - len(fat)
        fat_bytes += struct.pack('<I', FREESECT) * pad

        # DIFAT (header holds up to 109). We have few FAT sectors.
        difat = [FREESECT] * 109
        for k in range(fat_sectors):
            difat[k] = fat_start + k

        # Header
        header = bytearray()
        header += b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'  # signature
        header += b'\x00' * 16  # CLSID
        header += struct.pack('<H', 0x003E)  # minor version
        header += struct.pack('<H', 0x0003)  # major version (3 -> 512 sector)
        header += struct.pack('<H', 0xFFFE)  # byte order
        header += struct.pack('<H', 9)       # sector shift (512)
        header += struct.pack('<H', 6)       # mini sector shift (64)
        header += b'\x00' * 6                # reserved
        header += struct.pack('<I', 0)       # num dir sectors (0 for v3)
        header += struct.pack('<I', fat_sectors)
        header += struct.pack('<I', dir_first)
        header += struct.pack('<I', 0)       # transaction
        header += struct.pack('<I', MINICUTOFF)
        header += struct.pack('<I', minifat_first if minifat_bytes else ENDOFCHAIN)
        header += struct.pack('<I', nsectors(len(minifat_bytes)))
        header += struct.pack('<I', ENDOFCHAIN)  # first DIFAT sector
        header += struct.pack('<I', 0)           # num DIFAT sectors
        for d in difat:
            header += struct.pack('<I', d & 0xFFFFFFFF)
        assert len(header) == 512

        # Assemble sectors
        out = bytearray()
        out += header
        # FAT sectors
        out += fat_bytes
        # directory
        out += dir_bytes
        if len(dir_bytes) % SECTOR:
            out += b'\x00' * (SECTOR - len(dir_bytes) % SECTOR)
        # minifat
        out += minifat_bytes
        # ministream
        out += mini_padded
        # large streams
        for e in large:
            d = e.data
            out += d
            if len(d) % SECTOR:
                out += b'\x00' * (SECTOR - len(d) % SECTOR)

        return bytes(out)
