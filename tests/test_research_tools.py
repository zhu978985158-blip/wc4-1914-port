"""Synthetic fixtures only: no game, APK assets, emulator or signing keys required."""
from pathlib import Path
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


convert = load("convert_scene31_v3")
scene = load("audit_scene31")
diff = load("audit_base_diff")
transition = load("patch_map2_transition")


def synthetic_btl(reinforcements=0):
    header = [0] * 32
    header[0], header[1] = 1, 2
    header[4], header[5], header[22] = 2, 2, 4
    header[6], header[7], header[8], header[19], header[15] = 1, 1, 2, 1, reinforcements
    armies = bytearray(2 * 48)
    struct.pack_into("<H", armies, 16, 1)
    struct.pack_into("<H", armies, 48 + 16, 2)
    return (struct.pack("<32I", *header) + bytes(300) + bytes(4 * 2) + bytes(4)
            + bytes(32) + armies + bytes(80 * reinforcements) + bytes(4))


def synthetic_elf(machine=183):
    size, first_end, second_start = 0x828000, 0x232020, 0x240000
    data = bytearray(size)
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<16sHHIQQQIHHHHHH", data, 0, ident, 3, machine, 1,
                     0, 64, 0, 0, 64, 56, 2, 64, 0, 0)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, first_end, first_end, 0x1000)
    struct.pack_into("<IIQQQQQQ", data, 120, 1, 6, second_start, second_start,
                     second_start, size - second_start, size - second_start, 0x1000)
    struct.pack_into("<I", data, 0x231fec, transition.cbz8(0x231fec, 0x232014))
    data[0x826cd8:0x826d10] = bytes(range(0x38))
    return bytes(data)


class ResearchTests(unittest.TestCase):
    def test_btl_conversion_preserves_every_army_byte(self):
        source = synthetic_btl()
        output, before, after = convert.convert(source)
        self.assertEqual(struct.unpack_from("<I", output)[0], 3)
        self.assertEqual(len(output), len(source) + 32)
        offset = before["armies"]["offset"]
        for i in range(2):
            self.assertEqual(output[offset + i * 64:offset + i * 64 + 48],
                             source[offset + i * 48:offset + (i + 1) * 48])
            self.assertEqual(output[offset + i * 64 + 48:offset + (i + 1) * 64], bytes(16))
        self.assertEqual(after["armies"]["stride"], 64)

    def test_btl_rejects_truncation_and_unsupported_reinforcements(self):
        with self.assertRaises(ValueError):
            convert.convert(synthetic_btl()[:-1])
        with self.assertRaises(ValueError):
            convert.convert(synthetic_btl(reinforcements=1))

    def test_conversion_cli_writes_new_btl_and_audit_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.apk"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("assets/stage/conquest31.btl", synthetic_btl())
            original = source.read_bytes()
            output = Path(temp) / "nested/scene31.btl"
            subprocess.run([sys.executable, str(ROOT / "tools/convert_scene31_v3.py"),
                            str(source), str(output)], check=True, capture_output=True, text=True)
            self.assertEqual(struct.unpack_from("<I", output.read_bytes())[0], 3)
            report = json.loads(output.with_name(output.name + ".audit.json").read_text())
            self.assertTrue(report["roundtrip_exact"])
            self.assertEqual(source.read_bytes(), original)

    def test_binary_output_commands_refuse_to_overwrite_input_or_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "input", Path(temp) / "existing-output"
            source.write_bytes(b"keep input")
            output.write_bytes(b"keep output")
            for name in ["convert_scene31_v3.py", "patch_map2_transition.py"]:
                for destination in [source, output]:
                    result = subprocess.run([sys.executable, str(ROOT / "tools" / name),
                                             str(source), str(destination)], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(source.read_bytes(), b"keep input")
                    self.assertEqual(output.read_bytes(), b"keep output")

    def test_scene_id_conflict_audit_writes_isolated_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            base, source = Path(temp) / "base.apk", Path(temp) / "source.apk"
            with zipfile.ZipFile(base, "w") as archive:
                archive.writestr("assets/json/GeneralSettings.json", json.dumps([{"Id": 1, "Name": "base"}]))
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("assets/json/GeneralSettings.json", json.dumps([
                    {"Id": 1, "Name": "source"}, {"Id": 2, "Name": "new"}]))
                archive.writestr("assets/stage/conquest31.btl", synthetic_btl())
            originals = (base.read_bytes(), source.read_bytes())
            output = Path(temp) / "nested/output"
            subprocess.run([sys.executable, str(ROOT / "tools/audit_scene31.py"),
                            "--base", str(base), "--source", str(source), "--output", str(output)],
                           check=True, capture_output=True, text=True)
            report = json.loads((output / "scene31.audit.json").read_text())
            self.assertEqual(report["general_remap"], {"1": 40000})
            added = json.loads((output / "GeneralSettings.append.json").read_text())
            self.assertEqual({row["Id"] for row in added}, {40000, 2})
            self.assertTrue(all(row["InShop"] == 0 for row in added))
            self.assertEqual((base.read_bytes(), source.read_bytes()), originals)

    def test_apk_diff_detects_native_program_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            base, candidate = Path(temp) / "base.apk", Path(temp) / "candidate.apk"
            for path, payload in [(base, b"base"), (candidate, b"changed")]:
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("lib/arm64-v8a/libworld-conqueror-4.so", payload)
                    archive.writestr("assets/stage/conquest1.btl", b"original stage")
            report = diff.audit(base, candidate)
            self.assertEqual(report["status"], "BASE_PROTECTION_FAIL")
            self.assertEqual(report["changed_categories"], {"code": 1})
            self.assertIn("lib/arm64-v8a/libworld-conqueror-4.so",
                          report["forbidden_program_or_original_stage_changes"])

    def test_native_patch_limits_changes_and_preserves_speed_ranges(self):
        source = synthetic_elf()
        output, report = transition.patch(source)
        allowed = {index for first, last in report["allowed_ranges"]
                   for index in range(int(first, 16), int(last, 16))}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, output))))
        for first, last in report["protected_speed_ranges"]:
            self.assertEqual(source[int(first, 16):int(last, 16)], output[int(first, 16):int(last, 16)])
        self.assertEqual(len(report["stub_disassembly"]), 9)
        self.assertFalse(report["runtime_verified"])

    def test_native_patch_rejects_short_or_wrong_architecture(self):
        with self.assertRaises(ValueError):
            transition.patch(b"not an ELF")
        with self.assertRaises(ValueError):
            transition.patch(synthetic_elf(machine=62))

    def test_optimized_execution_cannot_disable_format_checks(self):
        code = ("import sys;sys.path.insert(0," + repr(str(ROOT / "tools")) + ");"
                "import convert_scene31_v3 as m;m.sections(bytes(128))")
        result = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without -O", result.stderr)


if __name__ == "__main__":
    unittest.main()
