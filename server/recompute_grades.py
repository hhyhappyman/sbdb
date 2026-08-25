"""
기존에 적재된 모든 방송 행의 급지(grade)를 현재 규칙(주중/주말 요일별)으로 재계산한다.
- 주말(토·일) 기준이 추가되면서, 이미 저장된 토·일 데이터의 급지가 옛 주중 기준으로
  계산되어 있으므로 이 스크립트로 일괄 갱신한다. (주중 데이터는 규칙이 그대로라 변화 없음)

대상: apst.db(broadcasts, manual_entries), ddr1.db(broadcasts)

사용법 (server 폴더에서):
  python recompute_grades.py           # 미리보기(dry-run, 변경 안 함)
  python recompute_grades.py --apply    # 실제 반영
"""
import sqlite3
import sys

from parsers.utils import classify_grade
from config import APST_DB_PATH, DDR1_DB_PATH


def recompute(db_path: str, table: str, apply: bool) -> tuple[int, int]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            f"SELECT id, broadcast_date, broadcast_time, grade FROM {table}"
        ).fetchall()
        changed = []
        for r in rows:
            new = classify_grade(r["broadcast_time"], r["broadcast_date"])
            if new != r["grade"]:
                changed.append((new, r["id"]))
        if apply and changed:
            con.executemany(f"UPDATE {table} SET grade = ? WHERE id = ?", changed)
            con.commit()
        return len(rows), len(changed)
    finally:
        con.close()


def main(apply: bool) -> None:
    targets = [
        (APST_DB_PATH, "broadcasts",     "apst.db / broadcasts(자동송출)"),
        (APST_DB_PATH, "manual_entries", "apst.db / manual_entries(수동입력)"),
        (DDR1_DB_PATH, "broadcasts",     "ddr1.db / broadcasts(수동송출)"),
    ]
    total_changed = 0
    for db_path, table, label in targets:
        try:
            n, c = recompute(db_path, table, apply)
        except sqlite3.OperationalError as e:
            print(f"  [건너뜀] {label}: {e}")
            continue
        total_changed += c
        print(f"  {label}: 전체 {n}행 중 {'변경' if apply else '변경 예정'} {c}행")

    print("\n── 요약 ─────────────────────────────")
    if apply:
        print(f"총 {total_changed}행 급지 갱신 완료.")
    else:
        print(f"총 {total_changed}행 변경 예정. 실제 반영하려면 --apply 를 붙이세요.")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
