"""사례 ID로 전체 상세 조회.

사용:
  python scripts/show_case.py SYN-IT-DBA-0232
  python scripts/show_case.py SYN-IT-DBA-0232 --json
"""
import argparse
import json
from pathlib import Path

CASES = Path(__file__).resolve().parents[1] / "data/processed/insurance_it_cases.jsonl"


def load_case(case_id):
    for line in CASES.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj["case_id"].lower() == case_id.lower():
            return obj
    return None


def main():
    ap = argparse.ArgumentParser(description="사례 상세 조회")
    ap.add_argument("case_id", help="예: SYN-IT-DBA-0232")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    c = load_case(args.case_id)
    if c is None:
        print(f"[없음] 사례 ID '{args.case_id}' 를 찾을 수 없습니다.")
        return

    if args.json:
        print(json.dumps(c, ensure_ascii=False, indent=2))
        return

    def line(label, val):
        print(f"  {label:<12}: {val}")

    print(f"=== {c['case_id']} : {c['title']} ===")
    line("카테고리", c["category"])
    line("요청유형", c["request_type"])
    line("상태", c["status"])
    line("대상시스템", f"{c['target_system']} ({c['environment']} 환경)")
    line("긴급도", c["urgency"])
    line("신청자", c["requester_role"])
    print()
    print(f"  [상황]\n    {c['situation']}")
    print()
    docs = ", ".join(c["required_documents"])
    if c.get("missing_document"):
        docs += f"  (누락: {c['missing_document']})"
    line("필요문서", docs)
    line("결재선", " → ".join(c["approval_route"]))
    line("설치도구", ", ".join(c["required_tools"]))
    line("사전점검", ", ".join(c["pre_checks"]))
    print()
    print("  [처리 절차]")
    for i, s in enumerate(c["process_steps"], 1):
        print(f"    {i}. {s}")
    print()
    print("  [주의 사항]")
    for x in c["cautions"]:
        print(f"    - {x}")
    print()
    line("결과", c["outcome"])
    line("기간", f"{c.get('started_at')} ~ {c.get('completed_at')}")


if __name__ == "__main__":
    main()
