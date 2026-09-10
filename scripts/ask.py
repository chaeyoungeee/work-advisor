"""workcase-agent 검색 CLI (채팅 환경 연결용).

사용:
  python scripts/ask.py "운영 DB 조회 계정이 필요한데 뭘 해야 해?"
  python scripts/ask.py "VPN 신청" --top-k 3 --json
  python scripts/ask.py "방화벽 오픈" --category "방화벽·네트워크" --status 완료

--json  : 기계가 파싱하기 좋은 JSON을 stdout으로 출력 (채팅 Agent가 근거로 사용)
기본    : 사람이 읽기 좋은 요약 출력
"""
import argparse
import json
import sys
from pathlib import Path

# src 를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workcase_agent.search import search_cases, get_contact  # noqa: E402

# 최고 사례의 원본 벡터 유사도(vector_score)가 이 값 미만이면
# '약한 매칭'으로 보고 담당자 안내를 붙인다.
# 하이브리드 score 는 min-max 정규화라 최상위가 항상 높으므로 판단에 쓰지 않는다.
# 정상 질의 vector_score ≈ 0.9+, 무관 질의 ≈ 0.78 이하.
WEAK_MATCH_THRESHOLD = 0.83


def main():
    ap = argparse.ArgumentParser(description="보험사 IT 업무 유사 사례 검색")
    ap.add_argument("query", help="한국어 업무 질의")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--category", default=None, help="카테고리 필터")
    ap.add_argument("--status", default=None, help="상태 필터 (완료/반려/보완 후 완료/진행 중)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    results = search_cases(
        args.query, top_k=args.top_k,
        category=args.category, status=args.status,
    )

    # 약한 매칭 판단: 결과가 없거나 최고 사례의 원본 벡터 유사도가 임계값 미만
    top_vec = results[0].get("vector_score", 0.0) if results else 0.0
    weak = (not results) or top_vec < WEAK_MATCH_THRESHOLD
    # 약한 매칭이면 특정 카테고리를 신뢰하기 어려우므로 1차 창구(기본)로 안내한다.
    contact = get_contact(None) if weak else None

    if args.json:
        print(json.dumps({
            "query": args.query,
            "results": results,
            "weak_match": weak,
            "contact": contact,
        }, ensure_ascii=False))
        return

    if not results:
        print("관련 사례를 찾지 못했습니다.")
        if contact:
            print(f"\n담당자 안내 → {contact.get('team','')}"
                  f" ({contact.get('contact','')})")
            print(f"  접수: {contact.get('channel','')}")
        return

    print(f"질의: {args.query}")
    print(f"검색된 유사 사례: {len(results)}건\n")
    for r in results:
        print(f"[{r['score']}] {r['case_id']}  ({r['category']} / {r['status']})")
        print(f"  제목    : {r['title']}")
        print(f"  상황    : {r['situation']}")
        print(f"  필요문서: {', '.join(r['required_documents'])}"
              + (f"  (누락: {r['missing_document']})" if r['missing_document'] else ""))
        print(f"  결재선  : {' → '.join(r['approval_route'])}")
        print(f"  설치도구: {', '.join(r['required_tools'])}")
        print(f"  사전점검: {', '.join(r['pre_checks'])}")
        print("  처리절차:")
        for i, s in enumerate(r["process_steps"], 1):
            print(f"     {i}. {s}")
        print(f"  주의    : {' / '.join(r['cautions'])}")
        print(f"  결과    : {r['outcome']}")
        print()

    if weak and contact:
        print("⚠ 유사도가 낮습니다. 아래 담당자에게 문의하세요.")
        print(f"  담당 → {contact.get('team','')} ({contact.get('contact','')})")
        print(f"  접수 : {contact.get('channel','')}")


if __name__ == "__main__":
    main()
