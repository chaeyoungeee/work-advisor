"""PastWorkCase 생성 (MVP 2단계).

hankzhwang/issues (ZOOKEEPER split)에서
resolved/closed & 댓글>=2 이슈를 골라 전처리하고,
issues + comments를 결합해 PastWorkCase JSONL로 저장한다.

계획서 5/6장 기준 반영:
- JIRA 마크업/제어문자 정리, 공백 정규화
- 봇/짧은 자동 댓글 제거, 시간순 정렬
- search_text는 레이블(Title/Problem/.../Resolution) 결합
- outcome 불명확하면 지어내지 않고 null
"""
import json
import re
from pathlib import Path

from datasets import load_dataset

REPO = "hankzhwang/issues"
SPLIT = "jira__apache__ZOOKEEPER"
PROJECT = "ZOOKEEPER"
OUT = Path("data/processed/past_work_cases.jsonl")

MIN_COMMENTS = 2
KEEP_STATES = {"resolved", "closed"}

# 자동/무의미 댓글 패턴 (봇 알림, 상태변경만 남긴 것 등)
NOISE_PATTERNS = [
    re.compile(r"^\s*(patch|patches?) (attached|available)\.?\s*$", re.I),
    re.compile(r"^\s*attaching\s+patch\b", re.I),
    re.compile(r"^\s*(lgtm|\+1|thanks|thank you|done|ok|okay)\.?\s*$", re.I),
    re.compile(r"integrated in|jenkins|hudson build|hadoopqa|githubbot", re.I),
    re.compile(r"^\s*commit\s+[0-9a-f]{7,40}\b", re.I),
]

# resolution 을 유추할 수 있는 종결 신호 문구
RESOLVED_HINTS = re.compile(
    r"\b(fixed|resolved|committed|merged|closing|closed|done|works now|"
    r"resolving|integrated)\b",
    re.I,
)


def clean_text(s):
    if not s:
        return ""
    # JIRA 마크업 완화: {code}, {noformat}, {quote} 등 래퍼 제거(내용은 유지)
    s = re.sub(r"\{code(:[^}]*)?\}", "\n", s)
    s = re.sub(r"\{noformat\}|\{quote\}|\{panel(:[^}]*)?\}", "\n", s)
    s = re.sub(r"\{color(:[^}]*)?\}|\{color\}", "", s)
    # 링크 [text|url] -> text
    s = re.sub(r"\[([^|\]]+)\|[^\]]+\]", r"\1", s)
    # 제어문자 제거
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    # 공백/줄바꿈 정규화
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def is_noise(body):
    b = body.strip()
    if len(b) < 8:
        return True
    for p in NOISE_PATTERNS:
        if p.search(b):
            return True
    return False


def build_comment_index(comments):
    idx = {}
    for row in comments:
        iid = row["issue_id"]
        idx.setdefault(iid, []).append(row)
    # 시간순 정렬
    for iid in idx:
        idx[iid].sort(key=lambda r: r.get("created_at") or "")
    return idx


def infer_outcome(kept_comments, state):
    """마지막 종결 신호가 있는 댓글에서 outcome 후보를 유추. 없으면 None."""
    for c in reversed(kept_comments):
        if RESOLVED_HINTS.search(c["body"]):
            return c["body"][:400]
    # 종결 신호 댓글이 없으면 억지 생성하지 않음
    return None


def make_search_text(title, problem, issue_type, priority, actions, resolution):
    parts = [f"Title: {title}"]
    if problem:
        parts.append(f"Problem: {problem}")
    meta = []
    if issue_type:
        meta.append(f"Type={issue_type}")
    if priority:
        meta.append(f"Priority={priority}")
    if meta:
        parts.append("Type/Priority: " + ", ".join(meta))
    if actions:
        joined = " ".join(actions)[:1500]
        parts.append(f"Discussion and Actions: {joined}")
    if resolution:
        parts.append(f"Resolution: {resolution}")
    return "\n".join(parts)


def main():
    issues = load_dataset(REPO, "issues", split=SPLIT)
    comments = load_dataset(REPO, "comments", split=SPLIT)
    cidx = build_comment_index(comments)

    OUT.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    n_outcome = 0
    n_skip_state = 0
    n_skip_cc = 0
    with OUT.open("w", encoding="utf-8") as f:
        for row in issues:
            state = (row.get("state") or "").lower()
            if state not in KEEP_STATES:
                n_skip_state += 1
                continue
            if (row.get("comments_count") or 0) < MIN_COMMENTS:
                n_skip_cc += 1
                continue

            number = str(row["number"])
            title = clean_text(row.get("title"))
            problem = clean_text(row.get("body"))

            raw_comments = cidx.get(number, [])
            kept = []
            for c in raw_comments:
                cb = clean_text(c.get("body"))
                if not cb or is_noise(cb):
                    continue
                kept.append({"created_at": c.get("created_at"), "body": cb})

            actions = [c["body"] for c in kept]
            outcome = infer_outcome(kept, state)
            if outcome:
                n_outcome += 1

            case = {
                "case_id": f"{PROJECT}-{number}",
                "project": PROJECT,
                "issue_type": None,  # ZOOKEEPER split에는 명시 유형 없음 -> null
                "title": title,
                "problem": problem or None,
                "context": {
                    "priority": None,
                    "components": [],
                    "labels": [],
                    "status": row.get("state"),
                    "resolution": None,
                    "created_at": row.get("created_at"),
                    "resolved_at": row.get("closed_at"),
                },
                "actions": actions,
                "outcome": outcome,
                "comments": kept,
                "search_text": make_search_text(
                    title, problem, None, None, actions, outcome
                ),
                "source": {"dataset": "hankzhwang/issues", "split": SPLIT,
                           "issue_id": number},
            }
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            n_written += 1

    print("=== PastWorkCase 생성 완료 ===")
    print(f"  출력: {OUT}")
    print(f"  생성된 사례 수: {n_written}")
    print(f"  outcome(해결내용) 유추 성공: {n_outcome} ({n_outcome/max(n_written,1)*100:.1f}%)")
    print(f"  제외(상태 미종결): {n_skip_state} / (댓글<{MIN_COMMENTS}): {n_skip_cc}")


if __name__ == "__main__":
    main()
