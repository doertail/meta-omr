import os
import google.generativeai as genai
import pandas as pd
import json
import time
import importlib
from dotenv import load_dotenv

# 1. 설정 (.env에서 API 키 로드)
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# 2. 모델 설정
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={
        "temperature": 0.1,
        "response_mime_type": "application/json"
    },
    system_instruction="""
    너는 대한민국 고등학교 수능 및 모의고사 문제 분류 전문가다.
    입력된 시험지 PDF를 보고, 각 문항 번호에 맞춰 '대분류', '소분류', '정답'을 판단해라.
    출력은 반드시 JSON 형식의 리스트로 내놔야 한다.
    정답은 PDF에 명시된 답안지를 참고해라.
    예시: [{"번호": 1, "대분류": "화법", "소분류": "발표 전략", "정답": "3"}, ...]
    """
)

def analyze_exam_paper(pdf_path, classification_rules):
    """PDF 직접 업로드 방식으로 시험지 분석"""
    print(f"📄 분석 시작: {pdf_path}")
    start_time = time.time()

    # 해설 PDF 경로 찾기 (문제 -> 해설로 변환)
    solution_path = pdf_path.replace('문제', '해설')

    # PDF 파일 업로드
    print(f"  📤 PDF 업로드 중...")
    problem_file = genai.upload_file(pdf_path)

    solution_file = None
    if os.path.exists(solution_path):
        print(f"  ✓ 해설 파일 발견: {os.path.basename(solution_path)}")
        solution_file = genai.upload_file(solution_path)
    else:
        print(f"  ⚠ 해설 파일 없음 (문제만 분석)")

    # 프롬프트 구성
    prompt = f"""
    첨부된 PDF 파일들을 분석해라.
    첫 번째 PDF는 시험지 문제, 두 번째 PDF는 해설이다.

    다음 [분류 기준표]를 엄격히 준수하여 1번부터 45번(또는 마지막 문제)까지 분류해라.

    [분류 기준표]
    {classification_rules}
    """

    try:
        # API 호출 (PDF 파일들과 프롬프트 함께 전송)
        if solution_file:
            response = model.generate_content([prompt, problem_file, solution_file])
        else:
            response = model.generate_content([prompt, problem_file])

        # 처리 시간 계산
        elapsed_time = time.time() - start_time

        # 사용량 출력
        total_tokens = 0
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            total_tokens = usage.total_token_count
            print(f"  📊 토큰 사용량: 입력={usage.prompt_token_count}, 출력={usage.candidates_token_count}, 총={usage.total_token_count}")

        print(f"  ⏱️  처리 시간: {elapsed_time:.1f}초")

        # JSON 파싱
        result_json = json.loads(response.text)

        # 결과에 파일명 추가
        for item in result_json:
            item['파일명'] = os.path.basename(pdf_path)

        # 업로드된 파일 정리
        genai.delete_file(problem_file.name)
        if solution_file:
            genai.delete_file(solution_file.name)

        return result_json, elapsed_time, total_tokens

    except Exception as e:
        print(f"❌ 에러 발생 ({pdf_path}): {e}")
        # 에러 발생 시에도 업로드된 파일 정리 시도
        try:
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
        # 해당 과목 폴더인지 확인
        if f"/{subject}" in root:
            for f in files:
                if f.endswith('.pdf') and '문제' in f:
                    pdf_files.append(os.path.join(root, f))

    # 이미 처리된 파일 제외
    pdf_files_to_process = [p for p in pdf_files if os.path.basename(p) not in processed_files]

    print(f"총 {len(pdf_files)}개 중 {len(pdf_files_to_process)}개 처리 예정 (이미 처리: {len(processed_files)}개)\n")

    if not pdf_files_to_process:
        print("✅ 모든 파일이 이미 처리되었습니다.")
        return

    for path in pdf_files_to_process:
        results, elapsed_time, tokens = analyze_exam_paper(path, classification_rules)
        all_results.extend(results)
        total_time += elapsed_time
        total_tokens += tokens
        file_count += 1

        # 매 파일 처리 후 저장 (중간 저장)
        df = pd.DataFrame(all_results)
        cols = ['파일명', '번호', '대분류', '소분류', '정답']
        df = df[cols]
        df.to_excel(output_path, index=False)

        print(f"  💾 중간 저장 완료 ({file_count}/{len(pdf_files_to_process)})")
        print()
        time.sleep(2)  # API Rate Limit 고려

    # 5. 최종 저장 완료 메시지
    print(f"✅ 최종 저장 완료: {output_path}\n")

    # 6. 통계 출력
    if file_count > 0:
        avg_time = total_time / file_count
        avg_tokens = total_tokens / file_count

        print("=" * 60)
        print("📈 처리 통계 요약")
        print("=" * 60)
        print(f"처리된 파일 수: {file_count}개")
        print(f"총 처리 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
        print(f"평균 처리 시간: {avg_time:.1f}초/개")
        print(f"총 토큰 사용량: {total_tokens:,} 토큰")
        print(f"평균 토큰 사용량: {avg_tokens:,.0f} 토큰/개")

if __name__ == "__main__":
    main()
