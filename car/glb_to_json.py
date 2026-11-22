"""Convert a .glb into a single self-contained glTF JSON file (buffer embedded as base64)."""
import json, struct, base64, sys
data = open(sys.argv[1], 'rb').read()
magic, version, length = struct.unpack_from('<4sII', data, 0)
assert magic == b'glTF' and version == 2
off, js, binc = 12, None, None
while off < length:
    clen, ctype = struct.unpack_from('<I4s', data, off); off += 8
    chunk = data[off:off + clen]; off += clen
    if ctype == b'JSON': js = json.loads(chunk.decode('utf-8'))
    elif ctype == b'BIN\x00': binc = chunk
js['buffers'][0]['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(binc).decode('ascii')
json.dump(js, open(sys.argv[2], 'w'), separators=(',', ':'))
print('ok', len(binc), 'bytes binary')
