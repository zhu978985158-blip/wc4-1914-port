"""Known-build APK comparison; a static pass is not a playable-mod verdict."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


def audit(base_path, candidate_path):
    with zipfile.ZipFile(base_path) as base, zipfile.ZipFile(candidate_path) as candidate:
        base_names, candidate_names = set(base.namelist()), set(candidate.namelist())
        common = sorted(base_names & candidate_names)
        changed = [name for name in common if base.read(name) != candidate.read(name)]
        added = sorted(candidate_names - base_names)
        removed = sorted(base_names - candidate_names)
        categories = Counter(
            "code" if name.endswith(".dex") or name.startswith("lib/") else
            "json" if name.endswith(".json") else
            "xml" if name.endswith(".xml") else "asset"
            for name in changed
        )
        forbidden = [name for name in changed if name in (
            "classes.dex", "classes2.dex", "lib/arm64-v8a/libworld-conqueror-4.so"
        ) or name.startswith("assets/stage/conquest") and name != "assets/stage/conquest31.btl"]
        intended_prefixes = (
            "assets/json/Conquer", "assets/json/GeneralSettings.json",
            "assets/json/SkillSettings.json", "assets/json/ArmySettings.json",
            "assets/json/CountrySettings.json", "assets/config/def_map.xml",
            "assets/config/def_motion.xml", "assets/config/def_effectsanim.xml",
            "assets/image/image_flags_hd.xml", "assets/image/image_flags_hd.webp",
        )
        unexpected = [name for name in changed if not name.startswith(intended_prefixes)
                      and name not in ("assets/maptext.xml", "assets/maptext.webp",
                                       "assets/maptextpos.xml", "META-INF/MANIFEST.MF")]
        removed_non_signature = [name for name in removed if not name.startswith("META-INF/")]
        return {
            "candidate_sha256": hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest(),
            "base_entry_count": len(base.namelist()), "candidate_entry_count": len(candidate.namelist()),
            "changed_existing_count": len(changed), "added_count": len(added), "removed_count": len(removed),
            "changed_categories": dict(categories),
            "forbidden_program_or_original_stage_changes": forbidden,
            "unexpected_changed_existing_entries": unexpected,
            "removed_non_signature_entries": removed_non_signature,
            "changed_existing": changed, "added_sample": added[:80],
            "status": "BASE_PROTECTION_FAIL" if forbidden or removed_non_signature else "BASE_PROTECTION_PASS",
            "runtime_verified": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    report = audit(args.base, args.candidate)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "BASE_PROTECTION_PASS" else 1)


if __name__ == "__main__":
    main()
