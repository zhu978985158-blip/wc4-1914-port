"""Lossless v1 -> v3 army-record expansion for the one authorized scene.

Format evidence: BtlAnalyzer.Analysis and Translator.Conversion in the
downloaded map editor assembly, checked against local target conquest files.
This deliberately rejects unsupported/extended scenes instead of truncating.
No APK or original input is overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sections(data):
    if not __debug__:
        raise RuntimeError("Format checks require Python without -O")
    h = struct.unpack_from('<32I', data)
    if h[0] not in (1, 2, 3):
        raise ValueError('Unsupported BTL version')
    specs = [
        ('header', 1, 128), ('countries', h[6], 300),
        ('terrain', h[22] if h[1] == 0 else 0, 16),
        ('provinces', h[22], 2), ('owners', h[22], 1),
        ('cities', h[7], 32), ('armies', h[8], 48 if h[0] == 1 else 64),
        ('pitfalls', h[26], 12), ('schemes', h[9], 16),
        ('weather', h[11], 16), ('events', h[10], 44),
        ('reinforcements', h[15], 80 if h[0] == 1 else 104),
        ('air_raids', h[16], 20), ('placements', h[17] + h[18], 8),
        ('capitals', h[19], 4), ('strategies', h[28], 16),
        ('air_support', h[31], 16),
    ]
    offset = 0
    result = {}
    for name, count, stride in specs:
        result[name] = dict(offset=offset, count=count, stride=stride)
        offset += count * stride
    if offset != len(data):
        raise ValueError(f'Unparsed or truncated data: predicted {offset}, actual {len(data)}')
    return h, result


def convert(data):
    h, table = sections(data)
    if h[0] != 1 or h[1] != 2 or h[15] != 0:
        raise ValueError('This converter only supports source scene31 without reinforcements')
    army = table['armies']
    start = army['offset']
    end = start + army['count'] * army['stride']
    # Army2 conversion preserves the 48 original bytes and initializes all
    # 16 new bytes (including ribbons) to zero. No statistics are changed.
    records = [data[o:o + 48] + bytes(16) for o in range(start, end, 48)]
    result = bytearray(data[:start] + b''.join(records) + data[end:])
    struct.pack_into('<I', result, 0, 3)
    h3, table3 = sections(result)
    # A reversible conversion is necessary evidence against accidental loss.
    restored = bytearray(result[:start])
    restored[:4] = data[:4]
    for i in range(army['count']):
        record = result[start + i * 64:start + (i + 1) * 64]
        assert record[48:] == bytes(16)
        restored.extend(record[:48])
    restored.extend(result[start + army['count'] * 64:])
    assert bytes(restored) == data
    return bytes(result), table, table3


def main():
    parser = argparse.ArgumentParser(description="Convert the supported scene-31 BTL v1 army layout to v3; no APK installation.")
    parser.add_argument("source", type=Path, help="Source APK containing assets/stage/conquest31.btl")
    parser.add_argument("output", type=Path, help="New standalone BTL output; must not already exist")
    args = parser.parse_args()
    report_path = args.output.with_name(args.output.name + ".audit.json")
    if args.source.resolve() == args.output.resolve() or args.output.exists() or report_path.exists():
        parser.error("Output/report must be new paths, separate from the source APK")
    with zipfile.ZipFile(args.source) as archive:
        source = archive.read("assets/stage/conquest31.btl")
    result, before, after = convert(source)
    audit = {
        "status": "STRUCTURAL_CONVERSION_ONLY_RUNTIME_UNVERIFIED",
        "source_bytes": len(source), "output_bytes": len(result),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "output_sha256": hashlib.sha256(result).hexdigest(),
        "roundtrip_exact": True, "source_sections": before, "target_sections": after,
        "unchanged": "All source bytes except header version; per-army 16-byte zero extension",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(result)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in audit.items() if "sections" not in k}, ensure_ascii=False))


if __name__ == "__main__":
    main()
