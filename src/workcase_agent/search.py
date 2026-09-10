"""search_cases: 한국어 질의로 유사 업무 사례 Top-K 하이브리드 검색.

하이브리드 = 의미 기반 벡터 검색(multilingual-e5 + FAISS)
            + 키워드 기반 BM25 검색을 정규화해 가중 결합.
- 벡터: 동의어·의미가 달라도 잡음 (예: "로그인 안 됨" ↔ "인증 실패")
- BM25: 정확한 키워드·약어·시스템명("TLS", "SSH", "VPN")에 강함
- case_id 기준 원본 사례 전체 필드 반환 (절차/결재선/문서/도구 등)
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-base"
CASES = Path("data/processed/insurance_it_cases.jsonl")
IDX_FILE = Path("indexes/workcases.faiss")
META_FILE = Path("indexes/metadata.jsonl")

# 하이브리드 가중치 (벡터가 이미 강하므로 벡터에 더 무게)
VECTOR_WEIGHT = 0.6
BM25_WEIGHT = 0.4


def _tokenize(text: str):
    """간단 한국어/영숫자 토큰화. 한글·영문·숫자 연속을 토큰으로."""
    return re.findall(r"[가-힣]+|[a-zA-Z0-9]+", text.lower())


def _minmax(vals):
    """점수 리스트를 0~1 로 min-max 정규화."""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return [0.0 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def _is_case(rec: dict) -> bool:
    """사례 레코드 여부. contacts 등 비사례 레코드를 제외한다."""
    return rec.get("record_type") != "contacts" and "search_text" in rec


@lru_cache(maxsize=1)
def _load():
    # 사례 레코드만 사용 (contacts 등 비사례 레코드는 벡터 인덱스와 순서를 맞추기 위해 제외)
    cases = [c for c in (json.loads(l) for l in
                         CASES.read_text(encoding="utf-8").splitlines())
             if _is_case(c)]
    meta = [json.loads(l) for l in META_FILE.read_text(encoding="utf-8").splitlines()]
    index = faiss.read_index(str(IDX_FILE))
    model = SentenceTransformer(MODEL_NAME)
    # BM25 는 사례 search_text 를 토큰화해 구축 (벡터 인덱스와 동일한 순서)
    bm25 = BM25Okapi([_tokenize(c["search_text"]) for c in cases])
    return cases, meta, index, model, bm25


@lru_cache(maxsize=1)
def load_contacts() -> dict:
    """담당자 디렉터리(record_type=contacts) 반환. 없으면 빈 dict.

    '관련 사례를 찾지 못했을 때' 채팅 에이전트가 담당 팀·연락처를 안내하는 데 쓴다.
    """
    for line in CASES.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("record_type") == "contacts":
            return rec.get("contacts", {})
    return {}


def search_cases(query: str, top_k: int = 5,
                 category: Optional[str] = None,
                 status: Optional[str] = None):
    """한국어 질의로 유사 사례 하이브리드 검색. category/status 필터 옵션.

    벡터 cosine 점수와 BM25 점수를 각각 0~1 정규화 후 가중 합산해
    최종 순위를 결정한다. 모든 사례에 대해 점수를 계산해 결합한다.
    """
    cases, meta, index, model, bm25 = _load()
    n = len(cases)

    # 1) 벡터 점수: 전체 사례에 대해 코사인 유사도 (row 순서로 정렬)
    q = model.encode(["query: " + query], convert_to_numpy=True,
                     normalize_embeddings=True).astype("float32")
    v_scores, v_idxs = index.search(q, n)
    vec_by_row = [0.0] * n
    for s, i in zip(v_scores[0], v_idxs[0]):
        if i >= 0:
            vec_by_row[i] = float(s)

    # 2) BM25 점수: 전체 사례에 대해
    bm_by_row = list(bm25.get_scores(_tokenize(query)))

    # 3) 각각 0~1 정규화 후 가중 합산
    vec_n = _minmax(vec_by_row)
    bm_n = _minmax(bm_by_row)
    combined = [
        (VECTOR_WEIGHT * vec_n[i] + BM25_WEIGHT * bm_n[i], i)
        for i in range(n)
    ]
    combined.sort(reverse=True)

    results = []
    for hybrid_score, i in combined:
        c = cases[i]
        if category and c["category"] != category:
            continue
        if status and c["status"] != status:
            continue
        results.append({
            "case_id": c["case_id"],
            "score": round(float(hybrid_score), 4),
            "vector_score": round(vec_by_row[i], 4),
            "bm25_norm": round(bm_n[i], 4),
            "category": c["category"],
            "title": c["title"],
            "status": c["status"],
            "situation": c["situation"],
            "required_documents": c["required_documents"],
            "missing_document": c.get("missing_document"),
            "approval_route": c["approval_route"],
            "required_tools": c["required_tools"],
            "pre_checks": c["pre_checks"],
            "process_steps": c["process_steps"],
            "cautions": c["cautions"],
            "outcome": c["outcome"],
        })
        if len(results) >= top_k:
            break
    return results


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "운영 DB 조회 계정이 필요한데 뭘 해야 해?"
    res = search_cases(q, top_k=5)
    print(f"질의: {q}\n")
    for r in res:
        print(f"[{r['score']}] {r['case_id']} ({r['category']}/{r['status']}) {r['title']}")
        print(f"    결재선: {' → '.join(r['approval_route'])}")
        print(f"    필요문서: {', '.join(r['required_documents'])}"
              + (f" (누락: {r['missing_document']})" if r['missing_document'] else ""))
        print(f"    도구: {', '.join(r['required_tools'])}")
        print()
