# meta-omr

수능/모의고사 PDF 시험지를 Gemini AI로 자동 분석해 문항별 **대분류 · 소분류 · 정답**을 추출하고 Excel로 저장하는 파이프라인.

## 구조

```
meta-omr/
├── class.py                  # 핵심 실행 파일: PDF 분석 & 분류
├── verify_answers.py         # 정답 교차 검증
├── rules/                    # 과목별 분류 기준표
│   ├── 국어.py
│   ├── 영어.py
│   ├── 수학.py
│   └── ...
└── 고등 모의고사 기출/        # PDF 입력 + Excel 출력
    ├── 2021년/
    │   └── 3월/
    │       ├── 고3/
    │       │   ├── 국어_문제.pdf
    │       │   └── 국어_해설.pdf
    │       └── ...
    └── 분류결과_{과목}.xlsx   # 자동 생성되는 결과 파일
```

> PDF 파일명 규칙: `*문제*.pdf` / `*해설*.pdf` (같은 이름에서 `문제` ↔ `해설`만 교체)

## 설치

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install google-generativeai pandas openpyxl python-dotenv
```

`.env` 파일 생성:

```
GOOGLE_API_KEY=발급받은_키
```

Google AI Studio에서 API 키 발급: https://aistudio.google.com/app/apikey

## 사용법

### 1단계: 분류 실행

```bash
python class.py
```

과목명 입력 → 해당 과목 PDF 전체 자동 처리 → `분류결과_{과목}.xlsx` 생성

- `분류결과` 시트: 전체 결과
- `검토필요` 시트: AI가 불확실하다고 판단한 항목

> 중간에 중단해도 이어하기 가능 (이미 처리된 파일은 자동 스킵)

### 2단계: 정답 검증 (선택)

```bash
python verify_answers.py
```

해설 PDF에서 정답을 재추출해 1단계 결과와 대조. 불일치 항목을 `정답검증` 시트에 저장.

## 새 과목 추가

`rules/` 폴더에 `{과목명}.py` 파일 생성 후 `CLASSIFICATION_RULES` 변수 정의:

```python
# rules/새과목.py
CLASSIFICATION_RULES = """
[대분류]
대분류명1
  - 소분류A
  - 소분류B
...
"""
```

기존 `rules/국어.py`를 참고해 동일한 형식으로 작성.

## 출력 Excel 컬럼

| 컬럼 | 설명 |
|------|------|
| 파일명 | 원본 PDF 파일명 |
| 번호 | 문항 번호 |
| 대분류 | 예: 화법, 문학, 독서 |
| 소분류 | 예: 발표 전략, 현대시 |
| 정답 | 1~5 사이 정수 (문자열) |
| 불확실 | AI가 판단 유보한 경우 `True` |
| 불확실_사유 | `소분류혼동` / `정답불확실` |

## 주의사항

- 홀수형/짝수형이 함께 있는 경우 **홀수형** 기준으로 분류
- API 호출 비용: 파일당 수천~수만 토큰 (Gemini 요금 정책 확인)
- 처리 속도: 파일당 약 20~60초 (API 응답 시간 + rate limit 대기 2초)
