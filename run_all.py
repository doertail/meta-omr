"""
모든 과목 일괄 분류 실행 스크립트
class.py를 과목별로 순서대로 subprocess 호출
"""
import subprocess
import sys
import os
import time

# 처리할 과목 목록 (원하는 과목만 남기거나 순서 변경 가능)
SUBJECTS = [
    "수학",
    "과학",
    "사회",
    "한국사",
    "물리학1",
    "물리학2",
    "화학1",
    "화학2",
    "생명과학1",
    "생명과학2",
    "지구과학1",
    "지구과학2",
    "사회문화",
    "생활과 윤리",
    "윤리와 사상",
    "정치와 법",
    "경제",
    "한국지리",
    "세계지리",
    "세계사",
    "동아시아사",
    # 이미 완료된 과목 (이어하기 지원되므로 포함해도 무방)
    "국어",
    "영어",
]


def run_subject(subject: str):
    print(f"\n{'='*60}")
    print(f"  과목: {subject}")
    print(f"{'='*60}\n")

    python = sys.executable
    script = os.path.join(os.path.dirname(__file__), "class.py")

    try:
        proc = subprocess.run(
            [python, script],
            input=subject,
            text=True,
            cwd=os.path.dirname(__file__),
        )
        return proc.returncode == 0
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"❌ {subject} 실행 오류: {e}")
        return False


def main():
    # 커맨드라인 인자로 특정 과목만 실행 가능
    # 예: python3 run_all.py 수학 물리학1
    if len(sys.argv) > 1:
        subjects = sys.argv[1:]
    else:
        subjects = SUBJECTS

    print(f"실행할 과목 ({len(subjects)}개): {', '.join(subjects)}")
    print("Ctrl+C로 중단하면 현재까지 저장된 결과는 보존됩니다.\n")

    overall_start = time.time()
    results = {}

    for subject in subjects:
        try:
            ok = run_subject(subject)
            results[subject] = "✅" if ok else "❌"
        except KeyboardInterrupt:
            print("\n\n⛔ 사용자 중단 — 현재까지의 결과는 저장되어 있습니다.")
            break
        except Exception as e:
            print(f"\n❌ {subject} 처리 중 오류: {e}")
            results[subject] = "❌"

    elapsed = time.time() - overall_start
    print(f"\n\n{'='*60}")
    print(f"  완료 요약 (총 {elapsed/60:.1f}분)")
    print(f"{'='*60}")
    for subj, status in results.items():
        print(f"  {status} {subj}")


if __name__ == "__main__":
    main()
