import os
import json
import random
from datetime import datetime
import networkx as nx
from pydantic import BaseModel, Field

def markdown_list(title: str, items: list[str]) -> str:
    if not items:
        return f"- **{title}**: -"

    return (
        f"- **{title}**\n"
        + "\n".join(f"  - {item}" for item in items)
    )

MD_ARCHIVE_DIR = "paper_qna"
def save_qna_as_markdown(paper: dict, summary:dict, keywords: dict) -> str:
    """
    논문 + QnA 대화 + 추출 키워드를 사람이 읽기 좋은 md 파일로 저장.
    """
    os.makedirs(MD_ARCHIVE_DIR, exist_ok=True)

    paper_id = paper["id"]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    filename = f"{paper_id.replace('/', '_')}.md"
    filepath = os.path.join(MD_ARCHIVE_DIR, filename)

    lines = [
        f"# {paper.get('title', paper_id)}",
        "",
        f"- **paper_id**: {paper_id}",
        f"- **github_repo**: {paper.get('github_repo', '-')}",
        f"- **project_page**: {paper.get('project_page', '-')}",
        f"- **publish**: {paper.get('published_at', '-')[:10]}",
        f"- **upvotes**: {paper.get('upvotes', '-')}",
        f"- **저장일시**: {timestamp}",
        f"- **키워드**: {', '.join(keywords.get("keywords"))}",
        "",
        "## 논문 요약",
        "",
        f"- **rating**: {summary.get('rating', '-')}",
    ]
    lines.append(markdown_list("Key Takeaways", summary.get('key_takeaways', '-')))
    lines.append(markdown_list("Application Ideas", summary.get('application_ideas', '-')))
 
    lines.extend(
        [f"- **summmary**: {summary.get('summmary', '-')}",
        "",
        "## Assumption Checker 대화 기록",
        f"{keywords.get('qna_summary', '-')}"
        "",
        ])

    content = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath

PAPER_GRAPH_PATH = "paper_graph.json"

def load_graph_from_disk(path: str = PAPER_GRAPH_PATH) -> nx.Graph:
    """디스크에 누적된 paper_graph를 로드. 파일 없으면 빈 그래프 반환."""
    if not os.path.exists(path):
        return nx.Graph()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return nx.node_link_graph(data)

def save_graph_to_disk(graph: nx.Graph, path: str = PAPER_GRAPH_PATH) -> None:
    """paper_graph를 디스크에 JSON으로 영속화."""
    data = nx.node_link_data(graph)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def update_graph(
    graph: nx.Graph, paper: dict, keywords: list[str]
) -> nx.Graph:
    """새 논문의 키워드를 누적 그래프에 병합"""
    paper_id = paper["id"]

    # paper 노드 추가
    if graph.has_node(paper_id):
        return graph
    
    graph.add_node(paper_id, type="paper", title=paper.get("title"), weight=10)

    # keyword 노드: 있으면 weight 증가, 없으면 생성
    for kw in keywords:
        if graph.has_node(kw):
            graph.nodes[kw]["weight"] += 1
        else:
            graph.add_node(kw, type="keyword", weight=1)

        # keyword - paper 엣지
        graph.add_edge(kw, paper_id, type="keyword-paper", weight=1)

    # keyword - keyword 엣지 (10개끼리 clique, 이미 있으면 weight 증가)
    for i in range(len(keywords)):
        for j in range(i + 1, len(keywords)):
            a, b = keywords[i], keywords[j]
            if graph.has_edge(a, b):
                graph.edges[a, b]["weight"] += 1
            else:
                graph.add_edge(a, b, type="keyword-keyword", weight=1)

    return graph

from networkx.algorithms.community import louvain_communities

def classify_papers(graph: nx.Graph) -> dict:
    # keyword-keyword 엣지만 있는 서브그래프로 커뮤니티 탐지
    keyword_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "keyword"]
    keyword_subgraph = graph.subgraph(keyword_nodes)
    communities = louvain_communities(keyword_subgraph, weight="weight")

    keyword_to_cluster = {}
    for cluster_id, community in enumerate(communities):
        for kw in community:
            keyword_to_cluster[kw] = cluster_id

    # 논문별로 연결된 키워드들의 클러스터 중 다수결로 분류
    paper_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "paper"]
    paper_classification = {}
    for paper_id in paper_nodes:
        connected_keywords = [n for n in graph.neighbors(paper_id) if n in keyword_to_cluster]
        if connected_keywords:
            clusters = [keyword_to_cluster[kw] for kw in connected_keywords]
            paper_classification[paper_id] = max(set(clusters), key=clusters.count)

    return paper_classification

from pyvis.network import Network

TOP_N_KEYWORDS = 15

def visualize_graph(graph: nx.Graph, output_path="graph_rag.html"):
    # 1. weight 기준 상위 N개 키워드만 선별
    keyword_nodes = [
        (n, attrs) for n, attrs in graph.nodes(data=True) if attrs.get("type") == "keyword"
    ]
    random.shuffle(keyword_nodes)
    top_keywords = sorted(keyword_nodes, key=lambda x: x[1].get("weight", 0), reverse=True)[:TOP_N_KEYWORDS]
    top_keyword_ids = {n for n, _ in top_keywords}

    # 2. 상위 키워드에 연결된 paper 노드만 같이 살림
    paper_nodes_connected = set()
    for kw in top_keyword_ids:
        for neighbor in graph.neighbors(kw):
            if graph.nodes[neighbor].get("type") == "paper":
                paper_nodes_connected.add(neighbor)

    visible_nodes = top_keyword_ids | paper_nodes_connected
    subgraph = graph.subgraph(visible_nodes)

    # 3. 시각화
    net = Network(height="700px", width="100%", notebook=False)
    for node, attrs in subgraph.nodes(data=True):
        size = 10 + attrs.get("weight", 1) * 3
        color = "#4C9AFF" if attrs.get("type") == "keyword" else "#FF8B00"
        net.add_node(node, label=str(node), size=size, color=color, title=str(attrs))

    for u, v, attrs in subgraph.edges(data=True):
        net.add_edge(u, v, value=attrs.get("weight", 1))

    net.show(output_path, notebook=False)
    
def visualize_with_clusters(
    graph: nx.Graph, keyword_to_cluster: dict, output_path="graph_rag.html"
):
    cluster_colors = ["#FF6B6B", "#4ECDC4", "#FFE66D", "#A78BFA", "#38BDF8"]

    # 1. weight 기준 상위 30개 키워드만 선별
    keyword_nodes = [
        (n, attrs) for n, attrs in graph.nodes(data=True) if attrs.get("type") == "keyword"
    ]
    top_keywords = sorted(keyword_nodes, key=lambda x: x[1].get("weight", 0), reverse=True)[:TOP_N_KEYWORDS]
    top_keyword_ids = {n for n, _ in top_keywords}

    # 2. 상위 키워드 + 거기 연결된 paper 노드만 서브그래프로 추출
    paper_nodes_connected = set()
    for kw in top_keyword_ids:
        for neighbor in graph.neighbors(kw):
            if graph.nodes[neighbor].get("type") == "paper":
                paper_nodes_connected.add(neighbor)

    visible_nodes = top_keyword_ids | paper_nodes_connected
    subgraph = graph.subgraph(visible_nodes)

    # 3. 시각화
    net = Network(height="700px", width="100%", notebook=False)
    for node, attrs in subgraph.nodes(data=True):
        size = 10 + attrs.get("weight", 1) * 3
        if attrs.get("type") == "keyword":
            cluster_id = keyword_to_cluster.get(node, 0)
            color = cluster_colors[cluster_id % len(cluster_colors)]
        else:
            color = "#888888"
        net.add_node(node, label=str(node), size=size, color=color, title=str(attrs))

    for u, v, attrs in subgraph.edges(data=True):
        net.add_edge(u, v, value=attrs.get("weight", 1))

    net.show(output_path, notebook=False)
