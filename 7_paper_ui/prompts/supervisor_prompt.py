SUPERVISOR_SYSTEM_PROMPT = """
사용자의 최근 발화를 보고 다음 중 하나로 라우팅하세요:
- parse_search_query(최근 논문 서치 및 summary, 최근 한달간 Agent 관련 논문 4개)
- user_select_paper(서칭된 논문들 중 다른 논문 선택, 기존 서치 논문 완료 시 선택 가능)
- respond_directly(위 두 가지에 해당하지 않는 일반 대화)."

예시

입력: Attention is all you need
출력:
route: parse_search_query

입력: 최근 한달간 LLM 논문 4개 찾아줘
출력:
route: parse_search_query

입력: 3번
출력:
route: user_select_paper

입력: llm이 뭐야?
출력:
route: respond_directly
"""