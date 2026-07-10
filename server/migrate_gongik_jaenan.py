"""
One-off migration: apply the new 공익재난 storage rules to existing apst.db.

New parse_apst now stores as '공익재난':
  - PRM/R/F/E ... + 공익/재난 in name   (R had SrcID K0000… → previously skipped)
  - K + 공익/재난 in '방송 종료 안내' program block

This script scans all APST files, and for every 공익재난 record:
  - if (date, time, clip_id) exists but label != '공익재난' → UPDATE to 공익재난
  - if it does not exist → INSERT
Existing PRM 공익재난 rows are left untouched.
"""

import glob
import sqlite3

from parsers.apst_parser import parse_apst
from config import APST_DB_PATH

APST_DIR = "/home/young/data/apst"

_INSERT_COLS = [
    "broadcast_date", "broadcast_time", "broadcast_hour", "clip_id",
    "item_name_raw", "item_name", "duration_sec", "program_block",
    "content_type", "content_type_label", "grade", "main_equipment",
    "internal_id", "source_file",
]


def main() -> None:
    conn = sqlite3.connect(APST_DB_PATH)
    added = updated = skipped = dur_fixed = 0

    files = sorted(glob.glob(f"{APST_DIR}/*.apst")) + sorted(glob.glob(f"{APST_DIR}/*.APST"))
    for fp in files:
        try:
            recs = parse_apst(fp)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {fp}: {e}")
            continue

        for r in recs:
            if r["content_type_label"] != "공익재난":
                continue
            row = conn.execute(
                "SELECT id, content_type_label, duration_sec FROM broadcasts "
                "WHERE broadcast_date=? AND broadcast_time=? AND clip_id=?",
                (r["broadcast_date"], r["broadcast_time"], r["clip_id"]),
            ).fetchone()

            if row is None:
                conn.execute(
                    f"INSERT INTO broadcasts ({','.join(_INSERT_COLS)}) "
                    f"VALUES ({','.join(['?'] * len(_INSERT_COLS))})",
                    tuple(r[c] for c in _INSERT_COLS),
                )
                added += 1
            elif row[1] != "공익재난":
                conn.execute(
                    "UPDATE broadcasts SET content_type_label='공익재난', "
                    "item_name=?, item_name_raw=?, duration_sec=?, content_type=? "
                    "WHERE id=?",
                    (r["item_name"], r["item_name_raw"], r["duration_sec"],
                     r["content_type"], row[0]),
                )
                updated += 1
            else:
                # 이미 공익재난: 과거 migrate-prm 때 duration_sec=0으로 저장된
                # 항목이 있어, 파일의 실제 Dur 값으로 갱신한다.
                if r["duration_sec"] and r["duration_sec"] != row[2]:
                    conn.execute(
                        "UPDATE broadcasts SET duration_sec=? WHERE id=?",
                        (r["duration_sec"], row[0]),
                    )
                    dur_fixed += 1
                skipped += 1

    conn.commit()
    total = conn.execute(
        "SELECT COUNT(*) FROM broadcasts WHERE content_type_label='공익재난'"
    ).fetchone()[0]
    conn.close()
    print(f"완료: 추가={added} 재분류={updated} 유지={skipped} 길이보정={dur_fixed} | 총 공익재난={total}")


if __name__ == "__main__":
    main()
