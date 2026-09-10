"""임베딩 + FAISS 인덱스 구축 (보험사 IT 합성 데이터).

- multilingual-e5 로 case.search_text 임베딩 (한국어)
- L2 정규화 후 FAISS IndexFlatIP (cosine)
- 인덱스, 메타데이터(jsonl), manifest 저장
- e5 prefix: 문서 "passage: ", 질의 "query: "
"""
import json
import time
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-base"
CASES = Path("data/processed/insurance_it_cases.jsonl")
IDX_DIR = Path("indexes")
IDX_FILE = IDX_DIR / "workcases.faiss"
META_FILE = IDX_DIR / "metadata.jsonl"
MANIFEST = IDX_DIR / "manifest.json"


def _is_case(rec: dict) -> bool:
    """사례 레코드 여부. contacts 등 비사례 레코드를 제외한다."""
    return rec.get("record_type") != "contacts" and "search_text" in rec


def main():
    all_recs = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines()]
    cases = [c for c in all_recs if _is_case(c)]
    skipped = len(all_recs) - len(cases)
    print(f"[load] cases: {len(cases)} (비사례 레코드 {skipped}건 제외)")

    print(f"[model] loading {MODEL_NAME} ...")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    print(f"[model] loaded in {time.time()-t0:.1f}s, dim={dim}")

    docs = ["passage: " + c["search_text"] for c in cases]
    print("[embed] encoding documents ...")
    t0 = time.time()
    emb = model.encode(
        docs, batch_size=32, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    ).astype("float32")
    print(f"[embed] done in {time.time()-t0:.1f}s, shape={emb.shape}")

    index = faiss.IndexFlatIP(dim)
    index.add(emb)
    IDX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(IDX_FILE))

    # 메타데이터: 벡터 순서 == 라인 순서
    with META_FILE.open("w", encoding="utf-8") as f:
        for i, c in enumerate(cases):
            f.write(json.dumps({
                "row": i,
                "case_id": c["case_id"],
                "category": c["category"],
                "title": c["title"],
                "status": c["status"],
            }, ensure_ascii=False) + "\n")

    MANIFEST.write_text(json.dumps({
        "model": MODEL_NAME,
        "dim": dim,
        "num_vectors": int(index.ntotal),
        "metric": "inner_product (cosine, L2-normalized)",
        "doc_prefix": "passage: ",
        "query_prefix": "query: ",
        "source_cases": str(CASES),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 인덱스 구축 완료 ===")
    print(f"  {IDX_FILE} (vectors={index.ntotal}, dim={dim})")
    print(f"  {META_FILE}")
    print(f"  {MANIFEST}")


if __name__ == "__main__":
    main()
