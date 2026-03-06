import pandas as pd
import os
import glob

def analyze_excels(target_dir):
    excel_files = glob.glob(os.path.join(target_dir, "분류결과_*.xlsx"))
    report = []

    for file in excel_files:
        filename = os.path.basename(file)
        try:
            # 분류결과 시트 읽기
            df = pd.read_excel(file) # 기본 시트 읽기
            
            # 1. 불확실 항목 확인
            if '불확실' in df.columns:
                uncertain = df[df['불확실'] == True]
                for _, row in uncertain.iterrows():
                    report.append(f"[{filename}] {row['파일명']} {row['번호']}번: 불확실 (사유: {row.get('불확실_사유', '없음')})")

            # 2. 정답 형식 확인 (1-5 사이 숫자)
            if '정답' in df.columns:
                # None 값 처리 후 문자열 변환
                invalid_ans = df[~df['정답'].fillna('').astype(str).str.contains('^[1-5](\.0)?$', regex=True)]
                for _, row in invalid_ans.iterrows():
                    report.append(f"[{filename}] {row['파일명']} {row['번호']}번: 정답 형식 오류 ({row['정답']})")

            # 3. 정답 검증 불일치 확인
            if '검증_비고' in df.columns:
                mismatch = df[df['검증_비고'] == '불일치']
                for _, row in mismatch.iterrows():
                    report.append(f"[{filename}] {row['파일명']} {row['번호']}번: 정답 불일치 (엑셀:{row['정답']}, 추출:{row.get('검증_추출정답', 'N/A')})")
            
            # 4. 소분류 빈값 확인
            if '소분류' in df.columns:
                empty_sub = df[df['소분류'].isna() | (df['소분류'] == '')]
                for _, row in empty_sub.iterrows():
                    report.append(f"[{filename}] {row['파일명']} {row['번호']}번: 소분류 누락")

        except Exception as e:
            report.append(f"[{filename}] 파일 읽기 오류: {str(e)}")

    return report

if __name__ == "__main__":
    target_folder = "./고등 모의고사 기출"
    results = analyze_excels(target_folder)
    if results:
        for r in results:
            print(r)
    else:
        print("모든 파일이 정상입니다.")
