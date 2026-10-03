"""Generate small, game-free interoperability fixtures with Python's zlib."""
import base64
import importlib.util
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patch_builder", ROOT / "tools/build_patches.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def swf(body):
    canonical = b"FWS\x09" + struct.pack("<I", len(body) + 8) + body
    return b"C" + canonical[1:8] + zlib.compress(body)


originals = [bytes(range(256)) * 4]
targets = [originals[0][:18] + b"patched" + originals[0][25:] + b"extension"]
for i in range(3):
    body = bytes(range(256)) * (i + 2)
    originals.append(swf(body))
    targets.append(swf(body[:80] + b"synthetic unit rename and battle preview" + body[110:] + bytes([i])))
originals.append(b"synthetic normal executable\0" + bytes(range(256)) * 3)
targets.append(originals[-1][:43] + b"NORMAL" + originals[-1][49:] + b"normal payload")
assert len(originals) == len(b.FILES)
files = []
for (path, encoding, _), original, target in zip(b.FILES, originals, targets):
    source, dest = b.canonical(original, encoding), b.canonical(target, encoding)
    ops = (b.aligned_delta if encoding == "raw" else b.indexed_delta)(source, dest)
    assert b.apply_delta(source, ops) == dest
    files.append(dict(Path=path, Encoding=encoding, OriginalSha256=b.sha(source), TargetSha256=b.sha(dest),
                      OriginalSize=len(source), TargetSize=len(dest), Operations=ops))
fixture = dict(Patch=dict(Format=1, Product="synthetic-installer-test", Profile="fixture-v1", Version="test", Files=files),
               Originals=[base64.b64encode(x).decode() for x in originals],
               Targets=[base64.b64encode(x).decode() for x in targets])
(ROOT / "tests/fixture.json").write_text(json.dumps(fixture, separators=(",", ":")) + "\n")
