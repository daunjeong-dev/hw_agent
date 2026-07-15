SELECT_PROMPT = f"""
사용자의 응답을 분석하여 다음 정보를 추출하세요.

규칙
- 논문 번호를 선택하면 action="select"입니다.
- 선택한 번호를 selected_num에 저장합니다.
- "종료", "그만", "끝", "quit", "exit"이면 action="quit"입니다.
- 종료인 경우 selected_num은 1입니다.
- 번호가 명확하지 않으면 selected_num=1입니다.
- 의도가 명확하지 않으면 action="quit"입니다.

예시

입력: 3
action="select"
selected_num=3

입력: 2번 보여줘
action="select"
selected_num=2

입력: 첫 번째
action="select"
selected_num=1

입력: 종료
action="quit"
selected_num=1

입력: 그만
action="quit"
selected_num=1
"""