from datetime import date

today = date.today().isoformat()
SEARCH_PROMPT = f"""
사용자의 논문 검색 의도를 추출하고,
사용자 요청에서 논문 검색 파라미터를 추출하세요.

오늘 날짜: {today}

규칙
- 논문 제목을 직접 입력한 경우
  search_type="title"

- 주제와 기간을 입력한 경우
  search_type="query"

- 제목은 수정하지 않습니다.
- 상대 기간은 year_delta, month_delta, day_delta에 저장합니다.
- "최근 N년" → year_delta=N
- "최근 N개월" → month_delta=N
- "최근 N일" → day_delta=N
- 언급되지 않은 값은 0으로 설정합니다.
- 절대 날짜(start_date, end_date)는 계산하지 않습니다.
- 날짜 조건이 없으면 year_delta=0, month_delta=0, day_delta=14 입니다.
- 개수 조건이 없으면 count=2 입니다.

예시

입력: Attention is all you need
출력:
search_type: title
title: Attention is all you need

입력: 최근 6개월 AI Agent 논문
출력:
search_type: query
topic: Agent
year_delta: 0
month_delta: 6
day_delta: 0
count: 10

입력: 최근 일주일 Transformer 논문 20개
출력:
search_type: query
topic: Transformer
year_delta: 0
month_delta: 0
day_delta: 14
count: 20

입력: LLM 논문
출력:
search_type: query
topic: LLM
year_delta: 0
month_delta: 0
day_delta: 14
count: 2

사용자 요청:
"""