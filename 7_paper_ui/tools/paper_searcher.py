from datetime import datetime, timedelta, date
from typing import Callable, Optional
import math
import requests

# ---- 수집/스코어링 관련 상수 ----
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
DAILY_PAPERS_PAGE_LIMIT = 50  # daily_papers 응답 페이지당 최대 개수
MIN_UPVOTES = 100  # 이 값 미만인 논문은 후보에서 제외
MIN_CANDIDATES_NUM = 50

# ---- 2. 수집 (결정적 로직, LLM 없음) ----
def fetch_from_huggingface(
    topic: str,
    start_date: str,
    end_date: str,
    count: int,
    on_progress: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    topic_lower = topic.lower()
    first = date.fromisoformat(start_date)
    current = date.fromisoformat(end_date)

    candidates = []
    max_num = max(MIN_CANDIDATES_NUM, count*10)
    while current > first or len(candidates)<=count:
        if on_progress:
            on_progress(f"{current.isoformat()} 검색 중... (후보 {len(candidates)}개)")
        response = requests.get(
            HF_DAILY_PAPERS_URL,
            params={"date": current.isoformat(), "limit": DAILY_PAPERS_PAGE_LIMIT},
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 400:
                # HF가 아직 발행하지 않은/허용하지 않는 날짜 (예: 오늘) -> 이 날짜만 건너뜀
                current -= timedelta(days=1)
                continue
            raise
        for item in response.json():
            paper = item["paper"]
            upvotes = paper.get("upvotes") or 0
            if upvotes < MIN_UPVOTES:
                break
            haystack = (paper["title"] + paper["summary"]).lower()
            if topic_lower not in haystack:
                continue
            candidates.append({
                "id": paper.get("id",""),
                "title": paper.get("title","-"),
                "summary": paper.get("summary","-"),
                "upvotes": upvotes,
                "github_stars": paper.get("githubStars") or 0,
                "github_repo": paper.get("githubRepo"),
                "published_at": paper.get("publishedAt",current),
                "project_page": paper.get("projectPage","-"),
                "ai_keywords": paper.get("ai_keywords",[]),
            })
        current -= timedelta(days=1)
        if len(candidates) > max_num:
            break

    return candidates

SCORE_WEIGHT_VOTES = 0.45
SCORE_WEIGHT_GITHUB_STARS = 0.35
SCORE_WEIGHT_RECENCY = 0.2

def score_and_sort(papers: list[dict]) -> list[dict]:
    if not papers:
        return []

    def normalize(values: list[float]) -> list[float]:
        low, high = min(values), max(values)
        if high == low:
            return [1.0 for _ in values]
        return [(v - low) / (high - low) for v in values]

    vote_scores = normalize([math.log1p(p["upvotes"]) for p in papers])
    star_scores = normalize([math.log1p(p["github_stars"]) for p in papers])
    published_ts = [
        datetime.fromisoformat(p["published_at"]).timestamp() for p in papers
    ]
    recency_scores = normalize(published_ts)

    scored = []
    for paper, vote_score, star_score, recency_score in zip(
        papers, vote_scores, star_scores, recency_scores
    ):
        score = (
            SCORE_WEIGHT_VOTES * vote_score
            + SCORE_WEIGHT_GITHUB_STARS * star_score
            + SCORE_WEIGHT_RECENCY * recency_score
        )
        scored.append({**paper, "score": score})

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored

def fetch_title_from_huggingface(topic: str, start_date: str, end_date: str, count: int) -> list[dict]:
    pass
