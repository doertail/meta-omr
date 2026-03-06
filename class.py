import os
import datetime
import google.generativeai as genai
from google.generativeai import caching
import pandas as pd
import json
import time
import importlib
from dotenv import load_dotenv
from verify_answers import extract_answers_with_pdfplumber

# 1. 설정 (.env에서 API 키 로드)
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# 2. 시스템 지침 (캐시 생성 및 일반 모델 공통 사용)
SYSTEM_INSTRUCTION = """
    너는 대한민국 고등학교 수능 및 모의고사 문제 분류 전문가다.
    입력된 시험지 PDF를 보고, 각 문항 번호에 맞춰 '대분류', '소분류', '정답', '불확실', '불확실_사유'를 판단해라.
    출력은 반드시 JSON 형식의 리스트로 내놔야 한다.
    예시: [{"번호": 1, "대분류": "화법", "소분류": "발표 전략", "정답": "3", "불확실": false, "불확실_사유": ""}, ...]

    [불확실 판단 기준]
    - 소분류를 두 가지 이상 놓고 어느 쪽인지 확신할 수 없는 경우: 불확실=true, 불확실_사유="소분류혼동"
    - 정답을 명확히 확인하지 못한 경우: 불확실=true, 불확실_사유="정답불확실"
    - 확실한 경우: 불확실=false, 불확실_사유=""

    [정답 추출 규칙 - 매우 중요]
    1. 해설지 첫 페이지 또는 마지막 페이지의 "정답" 표를 최우선으로 참조
    2. 정답 표가 없으면 각 문항 해설에서 "정답: X" 또는 "답: X" 찾기
    3. 정답은 보통 1~5 사이의 정수임 (단, 수학 과목의 주관식 문항은 0~999 사이의 자연수를 허용함)
    4. 불확실한 경우 해설 본문의 "~이다", "~가 정답" 등 확인

    [공통 주의사항]
    - 시험지에 홀수형/짝수형이 함께 있는 경우, 홀수형만 분류할 것
    - 소분류는 반드시 하나만 선택할 것. 여러 개를 나열하지 말 것
    - 수학 과목의 경우 22, 30번 등 주관식 문항의 실제 정답 숫자를 정확히 적을 것

    [필수 규칙]
    - 소분류는 반드시 아래 목록에 있는 표기를 ""그대로 복사""해서 사용할 것
    - 절대 임의로 띄어쓰기를 추가/제거하거나 표현을 바꾸지 말 것
    ❌ 잘못된 예: "토의 토론의 적절성", "화법과 대화", "글쓰기 성격"
    ✓ 올바른 예: "토의토론/적절성/전략", "화법/대화/말하기 방식", "글쓰기성격/목적/전략/예상독자"
    - 슬래시(/)도 그대로 유지할 것. 슬래시를 제거하거나 다른 기호로 바꾸지 말
    """

MAX_RETRIES = 2


def create_model(classification_rules):
    """Context Cache 생성 시도. 토큰 부족 등으로 실패하면 일반 모델로 fallback."""
    # Context Caching은 고정 버전 모델에서만 지원
    cache_model_name = "models/gemini-2.0-flash-001"
    generation_config = {
        "temperature": 0.1,
        "response_mime_type": "application/json"
    }

    try:
        cache = caching.CachedContent.create(
            model=cache_model_name,
            display_name="subject_rules_cache",
            system_instruction=SYSTEM_INSTRUCTION,
            contents=[classification_rules],
            ttl=datetime.timedelta(hours=1),
        )
        model = genai.GenerativeModel.from_cached_content(
            cached_content=cache,
            generation_config=generation_config,
        )
        print("✓ Context Cache 활성화 (비용 절감 모드)\n")
        return model, cache, True

    except Exception as e:
        print(f"⚠ Context Cache 생성 실패: {e}")
        print("  → 일반 모드로 실행합니다.\n")
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        return model, None, False


def analyze_exam_paper(pdf_path, classification_rules, subject_name="", model=None, use_cache=False):
    """PDF 직접 업로드 방식으로 시험지 분석"""
    print(f"📄 분석 시작: {pdf_path}")

    solution_path = pdf_path.replace('문제', '해설')

    subject_hint = f"\n    [현재 과목: {subject_name}]\n    해설지에 여러 과목의 정답표가 포함된 경우, 반드시 '{subject_name}' 과목의 정답표만 참조할 것.\n" if subject_name else ""

    if use_cache:
        # 분류 기준표는 캐시에 포함되어 있으므로 프롬프트에서 생략
        prompt = f"""
    첨부된 PDF 파일들을 분석해라.
    첫 번째 PDF는 시험지 문제, 두 번째 PDF는 해설이다.
{subject_hint}
    캐시된 [분류 기준표]를 엄격히 준수하여 1번부터 45번(또는 마지막 문제)까지 분류해라.

    [다시 한번 강조]
    캐시된 분류 기준표의 소분류를 글자 그대로 복사해서 출력할 것.
    임의로 수정하거나 새로운 표현을 만들지 말 것.
    """
    else:
        prompt = f"""
    첨부된 PDF 파일들을 분석해라.
    첫 번째 PDF는 시험지 문제, 두 번째 PDF는 해설이다.
{subject_hint}
    다음 [분류 기준표]를 엄격히 준수하여 1번부터 45번(또는 마지막 문제)까지 분류해라.

    [분류 기준표]
    {classification_rules}
    [다시 한번 강조]
    위 분류 기준표의 소분류를 글자 그대로 복사해서 출력할 것.
    임의로 수정하거나 새로운 표현을 만들지 말 것.
    """

    for attempt in range(MAX_RETRIES + 1):
        start_time = time.time()
        problem_file = None
        solution_file = None
        try:
            # PDF 파일 업로드
            print(f"  📤 PDF 업로드 중...")
            problem_file = genai.upload_file(pdf_path)

            if os.path.exists(solution_path):
                print(f"  ✓ 해설 파일 발견: {os.path.basename(solution_path)}")
                solution_file = genai.upload_file(solution_path)
            else:
                print(f"  ⚠ 해설 파일 없음 (문제만 분석)")

            # API 호출
            if solution_file:
                response = model.generate_content([prompt, problem_file, solution_file])
            else:
                response = model.generate_content([prompt, problem_file])

            elapsed_time = time.time() - start_time

            # 사용량 출력
            total_tokens = 0
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                total_tokens = usage.total_token_count
                cached_tokens = getattr(usage, 'cached_content_token_count', 0)
                cache_info = f", 캐시={cached_tokens}" if cached_tokens else ""
                print(f"  📊 토큰 사용량: 입력={usage.prompt_token_count}, 출력={usage.candidates_token_count}, 총={usage.total_token_count}{cache_info}")

            print(f"  ⏱️  처리 시간: {elapsed_time:.1f}초")

            # JSON 파싱
            result_json = json.loads(response.text)

            # 결과에 파일명 추가
            for item in result_json:
                item['파일명'] = os.path.basename(pdf_path)
                item['불확실'] = bool(item.get('불확실', False))
                item['불확실_사유'] = item.get('불확실_사유', '')

            # pdfplumber로 정답 덮어쓰기
            if os.path.exists(solution_path):
                pdf_answer_map = extract_answers_with_pdfplumber(solution_path)
                if pdf_answer_map:
                    overridden = 0
                    for item in result_json:
                        candidates = pdf_answer_map.get(int(item['번호']))
                        if candidates and len(candidates) == 1:
                            item['정답'] = candidates[0]
                            if item.get('불확실_사유') == '정답불확실':
                                item['불확실_사유'] = ''
                                item['불확실'] = False
                            overridden += 1
                    print(f"  ✓ pdfplumber 정답 교체: {overridden}문항")

            # 업로드된 파일 정리
            genai.delete_file(problem_file.name)
            if solution_file:
                genai.delete_file(solution_file.name)

            return result_json, elapsed_time, total_tokens

        except json.JSONDecodeError as e:
            try:
                if problem_file:
                    genai.delete_file(problem_file.name)
                if solution_file:
                    genai.delete_file(solution_file.name)
            except:
                pass

            if attempt < MAX_RETRIES:
                print(f"  ⚠ JSON 파싱 실패, 재시도 중... ({attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(5)
            else:
                print(f"  ❌ JSON 파싱 실패 (최대 재시도 초과): {e}")
                return [], 0, 0

        except Exception as e:
            print(f"❌ 에러 발생 ({pdf_path}): {e}")
            try:
                if problem_file:
                    genai.delete_file(problem_file.name)
                if solution_file:
                    genai.delete_file(solution_file.name)
            except:
                pass
            return [], 0, 0


# 4. 실행 (폴더 내 모든 PDF 처리)
def main():
    target_folder = "./고등 모의고사 기출"

    # 과목 입력받기
    subject = input("분류할 과목을 입력하세요 (예: 국어, 수학, 영어): ").strip()
    if not subject:
        print("과목이 입력되지 않았습니다.")
        return

    # 분류 기준표 동적 로드
    try:
        rules_module = importlib.import_module(f"rules.{subject}")
        classification_rules = rules_module.CLASSIFICATION_RULES
        print(f"✓ {subject} 분류 기준표 로드 완료\n")
    except ModuleNotFoundError:
        print(f"❌ rules/{subject}.py 파일이 없습니다. 분류 기준표를 먼저 만들어주세요.")
        return

    # 모델 생성 (캐시 시도 → fallback)
    active_model, cache, use_cache = create_model(classification_rules)

    # 샘플 모드 여부
    sample_input = input("샘플 모드로 실행하시겠습니까? (y/N): ").strip().lower()
    sample_mode = sample_input == 'y'
    sample_size = 5  # 기본 5개

    if sample_mode:
        count_input = input(f"몇 개 파일을 실행할까요? (기본 {sample_size}): ").strip()
        if count_input.isdigit() and int(count_input) > 0:
            sample_size = int(count_input)
        print(f"✓ 샘플 모드: 최대 {sample_size}개 파일 실행\n")

    # 기존 결과 파일 확인 (이어하기 기능)
    output_path = os.path.join(target_folder, f"분류결과_{subject}.xlsx")
    processed_files = set()
    all_results = []

    if os.path.exists(output_path):
        existing_df = pd.read_excel(output_path)
        processed_files = set(existing_df['파일명'].unique())
        all_results = existing_df.to_dict('records')
        print(f"📂 기존 결과 파일 발견: {len(processed_files)}개 파일 이미 처리됨")

    total_time = 0
    total_tokens = 0
    file_count = 0

    # 재귀적으로 PDF 파일 탐색
    pdf_files = []
    for root, dirs, files in os.walk(target_folder):
        if os.path.basename(root) == subject:
            for f in files:
                if f.endswith('.pdf') and '문제' in f:
                    pdf_files.append(os.path.join(root, f))

    # 이미 처리된 파일 제외
    pdf_files_to_process = [p for p in pdf_files if os.path.basename(p) not in processed_files]

    # 샘플 모드: 앞에서 N개만 선택
    if sample_mode:
        pdf_files_to_process = pdf_files_to_process[:sample_size]
        print(f"총 {len(pdf_files)}개 중 샘플 {len(pdf_files_to_process)}개만 실행합니다.\n")
    else:
        print(f"총 {len(pdf_files)}개 중 {len(pdf_files_to_process)}개 처리 예정 (이미 처리: {len(processed_files)}개)\n")

    if not pdf_files_to_process:
        print("✅ 모든 파일이 이미 처리되었습니다.")
        if cache:
            cache.delete()
        return

    for path in pdf_files_to_process:
        results, elapsed_time, tokens = analyze_exam_paper(
            path, classification_rules, subject, active_model, use_cache
        )
        all_results.extend(results)
        total_time += elapsed_time
        total_tokens += tokens
        file_count += 1

        # 매 파일 처리 후 저장 (중간 저장)
        df = pd.DataFrame(all_results)
        cols = ['파일명', '번호', '대분류', '소분류', '정답', '불확실', '불확실_사유']
        df = df.reindex(columns=cols, fill_value=False)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='분류결과', index=False)
            uncertain_df = df[df['불확실'] == True]
            if not uncertain_df.empty:
                uncertain_df.to_excel(writer, sheet_name='검토필요', index=False)

        print(f"  💾 중간 저장 완료 ({file_count}/{len(pdf_files_to_process)})")
        if not uncertain_df.empty:
            print(f"  ⚠ 불확실 항목 {len(uncertain_df)}건 → '검토필요' 시트 저장")
        print()
        time.sleep(2)  # API Rate Limit 고려

    # 5. 캐시 정리
    if cache:
        try:
            cache.delete()
            print("🗑 Context Cache 정리 완료")
        except:
            pass

    # 6. 최종 저장 완료 메시지
    print(f"✅ 최종 저장 완료: {output_path}\n")

    # 7. 통계 출력
    if file_count > 0:
        avg_time = total_time / file_count
        avg_tokens = total_tokens / file_count

        total_uncertain = sum(1 for r in all_results if r.get('불확실'))

        print("=" * 60)
        print("📈 처리 통계 요약")
        print("=" * 60)
        print(f"처리된 파일 수: {file_count}개")
        print(f"총 처리 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
        print(f"평균 처리 시간: {avg_time:.1f}초/개")
        print(f"총 토큰 사용량: {total_tokens:,} 토큰")
        print(f"평균 토큰 사용량: {avg_tokens:,.0f} 토큰/개")
        print(f"불확실 항목 수: {total_uncertain}건")
        print(f"캐시 모드: {'활성화' if use_cache else '비활성화 (일반 모드)'}")

if __name__ == "__main__":
    main()
