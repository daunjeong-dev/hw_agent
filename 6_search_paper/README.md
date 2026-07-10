# 논문 탐사 에이전트 (Paper Exploration Agent)

## 목적

AI 기술은 빠르게 변화하며 새로운 논문가 지속적으로 발표된다.  
새로운 기술이 실제로 검토할 가치가 있는지 판단하고, 핵심 내용을 이해하는 과정에는 많은 시간과 노력이 필요하다.

이 에이전트는 최근 AI 논문를 탐색하고, 질문 기반으로 논문를 깊이 이해하도록 돕는다.

---

## 핵심 기능

1. **최근 AI 논문 탐색**
   - 사용자 조건에 맞는 최신 논문 검색
   - 추천도 및 메타데이터 기반 정렬

2. **논문 분석 및 질문**
   - 논문 내용 요약
   - 사용자의 사고를 유도하는 질문 생성
   - 답변에 따라 추가 질문 및 피드백 제공

3. **내용 저장**
   - 학습 결과 저장
   - graph 형식으로 키워드 저장 (paper_graph.json)

4. ** 저장된 키워드 그래프 보기 **
   - graph_rag.html
---

## 그래프 구조

```text
START
  │
  ▼
triage
  ├──────────────► visualize_paper (Tool) ─────────────► END
  │
  ▼
parse_query
  │
  ▼
fetch_and_score
  │
  ├──────────────► summarize_paper (병렬)
  │                    │
  └────────────────────┘
           │
           ▼
user_select_paper
     │               │
     │               ▼
     │              END
     ▼
assumption_checker
           │
           ▼
save_graph_format
     │               │
     ▼               ▼
user_select_paper    END
```

---

## 노드 설명

| Node | 역할 |
|------|------|
| `triage` | 사용자의 요청을 분석하여 논문 탐색을 시작할지, 저장된 논문를 시각화할지 결정 |
| `visualize_paper` | 저장된 논문 정보를 그래프 형태로 시각화 |
| `parse_query` | 사용자의 검색 조건(주제, 기간, 개수 등)을 추출 |
| `fetch_and_score` | 조건에 맞는 논문를 검색하고 추천도를 계산 |
| `summarize_paper` | 각 논문의 핵심 내용, 추천 이유, 활용 아이디어 등을 요약 |
| `user_select_paper` | 사용자가 자세히 탐색할 논문를 선택하거나 종료 여부를 결정 |
| `assumption_checker` | 질문을 통해 논문의 문제 정의, 가정, 한계, 활용 가능성을 깊이 탐색 |
| `save_graph_format` | 탐색 결과를 그래프 형식으로 저장하고 다음 논문를 선택하거나 종료 |
---