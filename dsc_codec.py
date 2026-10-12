#!/usr/bin/env python3
"""
dsc_codec.py - decompress/compress BGI/Ethornell "DSC FORMAT 1.00" files.

Scenario files extracted from BGI .arc archives are usually further
compressed with a per-file keyed Huffman+LZ77 scheme, signposted by the
16-byte magic "DSC FORMAT 1.00\\0" at the very start. That's why opening
one directly in a text editor shows the magic string followed by garbage -
the rest genuinely is compressed binary, not text.

File layout:
    0x00  16 bytes  magic "DSC FORMAT 1.00\0"
    0x10   4 bytes  key            (uint32 LE) - seeds a PRNG used to
                                     decrypt everything that follows
    0x14   4 bytes  decompressed_size (uint32 LE)
    0x18   4 bytes  symbol_count   (uint32 LE) - how many Huffman symbols
                                     the compressed stream decodes to
    0x1C   4 bytes  reserved (zero)
    0x20  512 bytes encrypted Huffman code-length table, one byte per
                     symbol (256 literal byte values + 256 back-reference
                     length codes), XOR-style "encrypted" against the PRNG
                     keystream
    0x220 ...        Huffman-coded bitstream. Each decoded symbol is either
                     a literal byte (0-255) or a back-reference token
                     (256-511 -> length 2-257) immediately followed by a
                     fixed 12-bit offset (distance back into the output,
                     minus 2) - classic LZ77 dictionary copy.

The PRNG is a simple multiplicative one seeded by `key`; the same stream
both "decrypts" the code-length table and (implicitly, via the key stored
in the header) makes each file's compressed form unique even for
identical content. Re-compressing doesn't need to reuse the original key -
any key works as long as it's the one written into the new file's header,
since decompression always reads the key back out of the file itself.
"""

import heapq
import struct
import sys
from collections import Counter

MAGIC = b"DSC FORMAT 1.00\x00"
HEADER_SIZE = 0x20
TABLE_SIZE = 512  # 256 literals + 256 length codes
DATA_OFFSET = 0x220
MAX_MATCH_LEN = 257  # 2 + 255 (255 = max 8-bit length code range)
MAX_OFFSET = 4097     # 2 + 12-bit range
OFFSET_BITS = 12


def _prng_step(key, magic_word):
    """Advance the keystream by one step; returns (new_key, output_byte)."""
    lo = 20021 * (key & 0xFFFF)
    hi = (magic_word | (key >> 16)) * 20021 + key * 346
    hi = (hi + (lo >> 16)) & 0xFFFF
    new_key = ((hi << 16) + (lo & 0xFFFF) + 1) & 0xFFFFFFFF
    return new_key, hi & 0xFF


class BitReader:
    """MSB-first bit reader over a bytes buffer."""
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.cur = data[0] if data else 0
        self.left = 8

    def bit(self):
        if self.left == 0:
            self.pos += 1
            self.cur = self.data[self.pos] if self.pos < len(self.data) else 0
            self.left = 8
        b = (self.cur >> 7) & 1
        self.cur = (self.cur << 1) & 0xFF
        self.left -= 1
        return b

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


class BitWriter:
    """MSB-first bit writer."""
    def __init__(self):
        self.out = bytearray()
        self.buf = 0
        self.nbits = 0

    def bit(self, b):
        self.buf = (self.buf << 1) | b
        self.nbits += 1
        if self.nbits == 8:
            self.out.append(self.buf)
            self.buf = 0
            self.nbits = 0

    def bits(self, value, n):
        for i in range(n - 1, -1, -1):
            self.bit((value >> i) & 1)

    def flush(self):
        if self.nbits:
            self.buf <<= (8 - self.nbits)
            self.out.append(self.buf)
            self.buf = 0
            self.nbits = 0
        return bytes(self.out)


def _huffman_tree_from_lengths(lengths):
    """Rebuild a canonical Huffman tree from an array of code lengths (one
    per symbol, 0 = unused). This walks depth-by-depth: at each depth, any
    node slots left over (unclaimed) from the previous depth get expanded
    into two child slots each, then leaf symbols at this depth claim the
    remaining slots in order. Returns a flat node list where
    node[i] = (left_child_or_symbol, right_child_or_symbol); a node is a
    leaf when left == right."""
    nodes = [(0, 0)] * 1024
    # slot_table[buf][depth] holds the list of open node indices waiting
    # to be filled at that depth; we ping-pong between two buffers as we
    # move from one depth to the next.
    slot_table = [[[] for _ in range(300)], [[] for _ in range(300)]]
    slot_table[0][1] = [0]  # the root is an open slot at depth 1
    cur = 0
    next_free_node = 1

    for depth in range(1, 256):
        nxt = 1 - cur
        open_slots = slot_table[cur][depth]
        carried = []  # newly-opened child slots for the next depth
        for parent in open_slots:
            left = next_free_node
            right = next_free_node + 1
            next_free_node += 2
            nodes[parent] = (left, right)
            carried.append(left)
            carried.append(right)

        leaf_symbols = [s for s in range(TABLE_SIZE) if lengths[s] == depth]
        # leaves claim the leading slots of this depth's newly-created
        # children; the trailing leftover slots roll forward as the open
        # slots for the next depth
        take = len(leaf_symbols)
        for sym, slot in zip(leaf_symbols, carried[:take]):
            nodes[slot] = (sym, sym)
        slot_table[nxt][depth + 1] = carried[take:]
        cur = nxt

    return nodes


def _read_code_lengths(data, key):
    magic_word = struct.unpack_from("<H", data, 0)[0] << 16
    lengths = bytearray(TABLE_SIZE)
    k = key
    for i in range(TABLE_SIZE):
        k, ks_byte = _prng_step(k, magic_word)
        lengths[i] = (data[HEADER_SIZE + i] - ks_byte) & 0xFF
    return bytes(lengths), magic_word


def decompress(data):
    if data[:16] != MAGIC:
        raise ValueError("Not a 'DSC FORMAT 1.00' file")

    key, decompressed_size, symbol_count = struct.unpack_from("<III", data, 16)
    lengths, _ = _read_code_lengths(data, key)
    tree = _huffman_tree_from_lengths(lengths)

    reader = BitReader(data[DATA_OFFSET:])
    out = bytearray()
    for _ in range(symbol_count):
        node = 0
        while True:
            left, right = tree[node]
            if left == right:
                symbol = left
                break
            node = right if reader.bit() else left
        if symbol < 256:
            out.append(symbol)
        else:
            length = symbol - 256 + 2
            offset = reader.bits(OFFSET_BITS) + 2
            src = len(out) - offset
            for _ in range(length):
                out.append(out[src])
                src += 1

    if len(out) != decompressed_size:
        print(f"WARNING: decompressed {len(out)} bytes, header said {decompressed_size}",
              file=sys.stderr)
    return bytes(out)


def _lz77_tokenize(data):
    """Greedy LZ77 tokenizer matching the format's constraints (min match
    3, max match 257, max offset 4097). Returns a list of either
    ('lit', byte) or ('ref', length, offset)."""
    n = len(data)
    tokens = []
    pos = 0
    # simple hash-chain index over 3-byte prefixes for reasonable speed
    chains = {}
    while pos < n:
        best_len, best_off = 0, 0
        key3 = data[pos:pos + 3]
        if len(key3) == 3:
            candidates = chains.get(bytes(key3), [])
            for cand in reversed(candidates):
                off = pos - cand
                if off < 2:
                    continue
                if off > MAX_OFFSET:
                    break
                length = 0
                limit = min(MAX_MATCH_LEN, n - pos)
                while length < limit and data[cand + length] == data[pos + length]:
                    length += 1
                if length > best_len:
                    best_len, best_off = length, off
                    if length >= MAX_MATCH_LEN:
                        break
        if best_len >= 3:
            tokens.append(('ref', best_len, best_off))
            for i in range(best_len):
                p = pos + i
                k3 = bytes(data[p:p + 3])
                if len(k3) == 3:
                    chains.setdefault(k3, []).append(p)
            pos += best_len
        else:
            tokens.append(('lit', data[pos]))
            k3 = bytes(data[pos:pos + 3])
            if len(k3) == 3:
                chains.setdefault(k3, []).append(pos)
            pos += 1
    return tokens


def _canonical_codes(lengths):
    """Assign canonical Huffman codes given per-symbol lengths (0=unused)."""
    items = sorted((s for s in range(len(lengths)) if lengths[s]), key=lambda s: (lengths[s], s))
    codes = {}
    code, prev = 0, 0
    for sym in items:
        d = lengths[sym]
        code <<= (d - prev)
        codes[sym] = (code, d)
        code += 1
        prev = d
    return codes


def compress(data, key=None):
    if key is None:
        key = 0x00000001  # any value works; it's stored in the header and
                           # read back at decompress time, so it doesn't
                           # need to match anything
    tokens = _lz77_tokenize(data)

    symbols = []
    for t in tokens:
        symbols.append(t[1] if t[0] == 'lit' else 256 + t[1] - 2)
    freq = Counter(symbols)

    # build a Huffman tree by standard weighted-merge and derive lengths
    heap = [[w, [sym, ""]] for sym, w in freq.items()]
    heapq.heapify(heap)
    counter = 0
    if len(heap) == 1:
        # single-symbol edge case: force a 1-bit code
        heap[0][1][1] = "0"
    while len(heap) > 1:
        lo = heapq.heappop(heap)
        hi = heapq.heappop(heap)
        for pair in lo[1:]:
            pair[1] = "0" + pair[1]
        for pair in hi[1:]:
            pair[1] = "1" + pair[1]
        counter += 1
        heapq.heappush(heap, [lo[0] + hi[0], *lo[1:], *hi[1:]])

    lengths = [0] * TABLE_SIZE
    for pair in heap[0][1:]:
        sym, code = pair
        lengths[sym] = max(1, min(255, len(code)))
    codes = _canonical_codes(lengths)

    magic_word = struct.unpack("<H", MAGIC[:2])[0] << 16
    header = bytearray()
    header += MAGIC
    header += struct.pack("<III", key, len(data), len(symbols))
    header += b"\x00" * 4

    k = key
    for i in range(TABLE_SIZE):
        k, ks_byte = _prng_step(k, magic_word)
        header.append((lengths[i] + ks_byte) & 0xFF)

    writer = BitWriter()
    for t in tokens:
        if t[0] == 'lit':
            code, d = codes[t[1]]
        else:
            _, length, offset = t
            code, d = codes[256 + length - 2]
        writer.bits(code, d)
        if t[0] == 'ref':
            writer.bits(t[2] - 2, OFFSET_BITS)
    body = writer.flush()

    return bytes(header) + body


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("Usage: python3 dsc_codec.py decompress <in> <out>")
        print("       python3 dsc_codec.py compress <in> <out> [key_hex]")
        sys.exit(1)

    cmd, in_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(in_path, "rb") as f:
        data = f.read()

    if cmd == "decompress":
        result = decompress(data)
    elif cmd == "compress":
        key = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
        result = compress(data, key)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    with open(out_path, "wb") as f:
        f.write(result)
    print(f"{cmd}: {len(data)} bytes -> {len(result)} bytes, wrote {out_path}")


if __name__ == "__main__":
    main()
