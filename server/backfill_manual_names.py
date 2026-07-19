"""
과거 수동송출(ddr1.db)에서 소재명이 clip_id(N######) 그대로 남은 행을,
양방향 APST 조회(get_apst_name_before)로 소재명·소재종류를 보완한다.

- CML에 없던 clip_id라도, 자동편성(APST)에 (이전이든 이후든) 등장한 적이 있으면
  그 소재명으로 채운다. (신소재가 수동으로 먼저 나가고 자동은 이후에 편성되는 경우 포함)
- 소스 파일 재적재가 필요 없다. ddr1.db 행을 직접 갱신한다.

사용법 (server 폴더에서):
  python backfill_manual_names.py           # 미리보기(dry-run, 변경 안 함)
  python backfill_manual_names.py --apply    # 실제 반영
"""

import sys

from services.aggregator import get_apst_name_before
from database import get_ddr1_conn


def main(apply: bool) -> None:
    with get_ddr1_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT clip_id, broadcast_date
               FROM broadcasts
               WHERE item_name = clip_id AND clip_id LIKE 'N%'
               ORDER BY broadcast_date""",
        ).fetchall()

        total = len(rows)
        resolved = 0
        unresolved = 0
        updated_rows = 0

        for r in rows:
            clip_id = r["clip_id"]
            bdate = r["broadcast_date"]
            entry = get_apst_name_before(clip_id, bdate)
            if not entry:
                unresolved += 1
                continue
            resolved += 1
            name = entry["item_name"] or clip_id
            raw = entry["item_name_raw"] or name
            label = entry["content_type_label"] or "캠페인"
            print(f"  {bdate} {clip_id} -> {name}  [{label}]  (APST {entry['source_date']})")
            if apply:
                cur = conn.execute(
                    """UPDATE broadcasts
                       SET item_name = ?, item_name_raw = ?, content_type_label = ?
                       WHERE clip_id = ? AND broadcast_date = ? AND item_name = clip_id""",
                    (name, raw, label, clip_id, bdate),
                )
                updated_rows += cur.rowcount

        if apply:
            conn.commit()

    print("\n── 요약 ─────────────────────────────")
    print(f"대상(미해결 clip×날짜): {total}")
    print(f"해결 가능: {resolved} / 해결 불가(APST에 없음): {unresolved}")
    if apply:
        print(f"실제 갱신된 행 수: {updated_rows}")
    else:
        print("(dry-run) 실제 반영하려면 --apply 를 붙여 다시 실행하세요.")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
