"""search_cases: 한국어 질의로 보험사 IT 유사 사례 Top-K 검색.

- multilingual-e5 로 질의 임베딩 ("query: " prefix)
- FAISS IndexFlatIP (cosine) 검색
- case_id 기준 원본 사례 전체 필드 반환 (절차/결재선/문서/도구 등)
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import faiss
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-base"
CASES = Path("data/processed/insurance_it_cases.jsonl")
IDX_FILE = Path("indexes/workcases.faiss")
META_FILE = Path("indexes/metadata.jsonl")


@lru_cache(maxsize=1)
def _load():
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines()]
    meta = [json.loads(l) for l in META_FILE.read_text(encoding="utf-8").splitlines()]
    index = faiss.read_index(str(IDX_FILE))
    model = SentenceTransformer(MODEL_NAME)
    return cases, meta, index, model


def search_cases(query: str, top_k: int = 5,
                 category: Optional[str] = None,
                 status: Optional[str] = None):
    """한국어 질의로 유사 사례 검색. category/status 필터 옵션."""
    cases, meta, index, model = _load()
    q = model.encode(["query: " + query], convert_to_numpy=True,
                     normalize_embeddings=True).astype("float32")
    # 필터가 있으면 넉넉히 뽑아서 후처리
    k = top_k if not (category or status) else min(len(cases), top_k * 6)
    scores, idxs = index.search(q, k)

    results = []
    for score, i in zip(scores[0], idxs[0]):
        if i < 0:
            continue
        c = cases[i]
        if category and c["category"] != category:
            continue
        if status and c["status"] != status:
            continue
        results.append({
            "case_id": c["case_id"],
            "score": round(float(score), 4),
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
