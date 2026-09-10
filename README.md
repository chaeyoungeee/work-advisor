# workcase-agent — 보험사 IT 업무 사례 검색 Agent

과거 보험사 사내 IT 업무 사례(합성 300건)를 벡터 검색해, 신규 요청에 대한
**처리 절차 · 필요 문서 · 결재선 · 설치 프로그램 · 확인 사항**을 근거 기반으로 안내한다.

한국어 질의를 그대로 임베딩(multilingual-e5)해 FAISS 로 검색한다. 외부 LLM API 없이
로컬에서 검색이 동작하며, 답변 문장 생성은 이 저장소를 연 채팅 에이전트가 담당한다.

---

## 1. 요구 사항

- Python 3.9 이상 (개발/검증 환경: macOS, Python 3.9.6)
- 인터넷 연결 (최초 1회, 임베딩 모델 `intfloat/multilingual-e5-base` 다운로드 약 1GB)
- 디스크 여유 약 2~3GB (torch + 모델 캐시 포함)

## 2. 설치

```bash
# 저장소 폴더로 이동
cd work-advisor

# 가상환경 생성 및 활성화 (Windows: .venv\Scripts\activate)
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치 (버전 고정)
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. 인덱스 준비

저장소에 이미 만들어진 인덱스(`indexes/`)가 포함되어 있으면 이 단계는 건너뛴다.
데이터만 있고 인덱스가 없거나, 데이터를 바꿨다면 재생성한다:

```bash
# 입력: data/processed/insurance_it_cases.jsonl (300건)
# 출력: indexes/workcases.faiss, metadata.jsonl, manifest.json
python scripts/create_index.py
```

> 최초 실행 시 임베딩 모델을 내려받으며 시간이 걸린다(이후에는 캐시 사용).

## 3-1. (선택) DeepWork 스킬로 등록

DeepWork 앱에서 이 저장소를 "스킬"로 등록하면, 채팅에서 보험사 IT 업무를
물을 때 자동으로 이 검색 도구를 사용해 정해진 형식으로 답한다.

저장소 안의 `skill/` 폴더를 앱의 스킬 경로로 복사한다:

```bash
# macOS / Linux
mkdir -p ~/.deepwork/skills/work-advisor
cp -R skill/. ~/.deepwork/skills/work-advisor/
```

복사 후 `SKILL.md` 안의 `<프로젝트 루트>` 안내대로, 본인이 clone 한
저장소 경로를 사용하도록 맞춘다. (스킬은 CLI 를 호출할 때 저장소의
`scripts/ask.py` 를 그 경로로 실행한다.)

## 4. 사용법

### 4-1. 질문하기 (사람이 읽는 출력)
```bash
python scripts/ask.py "퇴직자 DB 계정 회수해야 하는데 절차 알려줘"
python scripts/ask.py "재택근무 VPN 신청 어떻게 해?" --top-k 3
```

### 4-2. 필터
```bash
python scripts/ask.py "방화벽 포트 오픈" --category "방화벽·네트워크"
python scripts/ask.py "포트 오픈" --status "반려"   # 반려 사례만
```
상태 값: `완료` / `반려` / `보완 후 완료` / `진행 중`

### 4-3. 사례 상세 보기
```bash
python scripts/show_case.py SYN-IT-DBA-0232
python scripts/show_case.py SYN-IT-DBA-0232 --json
```

### 4-4. 에이전트 연동용 JSON
```bash
python scripts/ask.py "질문" --top-k 4 --json
```

## 5. 다룰 수 있는 업무 영역 (11개)

DB 계정·권한 / 사내 계정·그룹웨어 / VPN·원격접속 / 프로그램 설치 /
서버 접근·작업 / 방화벽·네트워크 / 배포·변경관리 / 배치·인터페이스 장애 /
개인정보·데이터 추출 / 인증서·암호화키 / IT 장애·문의

## 6. 폴더 구조

```
work-advisor/
├── requirements.txt
├── data/processed/insurance_it_cases.jsonl   # 합성 사례 300건 (약 1MB)
├── indexes/                                  # FAISS 인덱스 + 메타데이터
│   ├── workcases.faiss
│   ├── metadata.jsonl
│   └── manifest.json
├── src/workcase_agent/search.py              # 검색 핵심 로직
├── scripts/
│   ├── ask.py            # 질의 → 유사 사례 검색 (메인 진입점)
│   ├── show_case.py      # 사례 ID → 상세
│   ├── create_index.py   # 인덱스 (재)생성
│   ├── prepare_cases.py  # 데이터 → 사례 변환
│   └── make_report.py    # HTML 보고서 (선택)
└── skill/                                    # DeepWork 스킬 (선택 등록)
    ├── SKILL.md
    └── references/output_format.md
```

## 7. 다른 컴퓨터로 옮길 때 체크리스트

- [ ] `data/processed/insurance_it_cases.jsonl` 포함했는가 (필수 입력)
- [ ] `indexes/` 포함했는가 — 없으면 3장으로 재생성 (약 15초)
- [ ] `requirements.txt`로 동일 버전 설치했는가
- [ ] 최초 실행 시 모델 다운로드용 인터넷 연결이 되는가
- [ ] `.venv/`는 옮기지 말 것 (OS/경로 의존적, 새로 생성)

## 8. 한계 (중요)

- 데이터는 **완전 합성(가상)** 이다. 특정 보험사의 실제 규정·시스템·결재선이 아니다.
  실제 신청서명·결재선·설치 프로그램은 사내 규정으로 최종 확인해야 한다.
- 답변 문장 생성은 채팅 에이전트가 수행한다. CLI 단독으로는 "유사 사례 검색 결과"까지 제공한다.

<!-- deepwork connection verified -->
