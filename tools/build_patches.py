#!/usr/bin/env python3
"""Generate patch data locally from legally supplied originals and the tested mod.

No game files are checked into this repository. The SWF delta operates on the
uncompressed SWF, so no complete replacement game interface is distributed.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import zlib

FILES = [
    ("AoW3_Debug.exe", "raw", "233584a414e16f624a5531b10e1491896e4b17a074e585364fec7d11c692d763"),
    ("Content/Title/Interface/HUD_CombatResults.swf", "swf", "3e995765ee8553788b5046dc7c62634fdbfc409f3d5956edaf5cb06f12b34bd6"),
    ("Content/Title/Interface/HUD_FloatingHeroBackground.swf", "swf", "6877437e5ed348925629d801f35e808c4b84480a44a149df5d15189887163479"),
    ("Content/Title/Interface/HUD_NameChanger.swf", "swf", "2ef9d6e385f90a2f10c4f21919f115acedfe7498c76867834c6698d4f937d6a3"),
    ("AoW3.exe", "raw", "9fd625d451ae534cf877b7850c614677f4d2d6209741bf85035e79f081a796d4"),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data, encoding):
    if encoding == "raw":
        return data
    if data[:3] == b"CWS":
        dec = zlib.decompressobj()
        body = dec.decompress(data[8:]) + dec.flush()
        if not dec.eof or dec.unused_data or dec.unconsumed_tail:
            raise ValueError("Invalid SWF zlib stream")
        data = b"F" + data[1:8] + body
    if data[:3] != b"FWS" or len(data) != struct.unpack_from("<I", data, 4)[0]:
        raise ValueError("Invalid SWF length or signature")
    return data


def literal(data):
    return {"Data": base64.b64encode(data).decode("ascii")}


def aligned_delta(source, target):
    """Sparse executable changes; equal runs stay at their original offsets."""
    ops, start, i = [], 0, 0
    n = min(len(source), len(target))
    while i < n:
        if source[i] != target[i]:
            i += 1
            continue
        end = i + 1
        while end < n and source[end] == target[end]:
            end += 1
        if end - i >= 16:
            if i > start:
                ops.append(literal(target[start:i]))
            ops.append({"Offset": i, "Length": end - i})
            start = end
        i = end
    if start < len(target):
        ops.append(literal(target[start:]))
    return ops


def indexed_delta(source, target):
    index = {}
    for off in range(0, len(source) - 15, 8):
        bucket = index.setdefault(source[off:off + 16], [])
        if len(bucket) < 16:
            bucket.append(off)
    ops, start, pos = [], 0, 0
    while pos < len(target):
        best_off, best_len = 0, 0
        for off in index.get(target[pos:pos + 16], ()):
            length, limit = 16, min(len(source) - off, len(target) - pos)
            while length < limit and source[off + length] == target[pos + length]:
                length += 1
            if length > best_len:
                best_off, best_len = off, length
        if best_len < 24:
            pos += 1
            continue
        if pos > start:
            ops.append(literal(target[start:pos]))
        ops.append({"Offset": best_off, "Length": best_len})
        pos += best_len
        start = pos
    if start < len(target):
        ops.append(literal(target[start:]))
    return ops


def apply_delta(source, ops):
    return b"".join(base64.b64decode(op["Data"]) if "Data" in op
                    else source[op["Offset"]:op["Offset"] + op["Length"]] for op in ops)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("originals", type=Path, help="Original flat upload directory or game folder")
    parser.add_argument("modified", type=Path, help="Tested mod game folder")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entries = []
    for name, encoding, expected in FILES:
        original = args.originals / name
        if not original.exists():
            original = args.originals / Path(name).name
        raw = original.read_bytes()
        if sha(raw) != expected:
            raise ValueError("Unrecognized original: " + name)
        raw_target = (args.modified / name).read_bytes()
        source, target = canonical(raw, encoding), canonical(raw_target, encoding)
        ops = (aligned_delta if encoding == "raw" else indexed_delta)(source, target)
        if apply_delta(source, ops) != target:
            raise AssertionError("Delta round trip failed: " + name)
        entries.append(dict(Path=name, Encoding=encoding, OriginalSha256=sha(source),
                            TargetSha256=sha(target), OriginalSize=len(source),
                            TargetSize=len(target), Operations=ops))
        inserted = sum(len(base64.b64decode(x["Data"])) for x in ops if "Data" in x)
        print("{}: {} operations, {} inserted bytes; verified".format(name, len(ops), inserted))
    manifest = dict(Format=1, Product="AoW3-Manual-Autocombat-Rename-No-Telemetry",
                    Version="0.7.2", Profile="normal-debug-28623-v072", Files=entries)
    args.output.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
    print("Wrote {} ({} bytes)".format(args.output, args.output.stat().st_size))


if __name__ == "__main__":
    main()
