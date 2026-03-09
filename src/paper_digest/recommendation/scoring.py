"""Scoring helpers for daily paper recommendations."""

from __future__ import annotations

from datetime import datetime

from paper_digest.models import PaperMetadata, RecommendationScores, ResearchProfile

SCORE_MAX = 3.0
RELEVANCE_TITLE_KEYWORD_BOOST = 0.5
RELEVANCE_ABSTRACT_KEYWORD_BOOST = 0.3
RELEVANCE_CATEGORY_MATCH_BOOST = 1.0
POPULARITY_INFLUENTIAL_CITATION_FULL_SCORE = 100

WEIGHTS_NORMAL = {
    "relevance": 0.40,
    "recency": 0.20,
    "popularity": 0.30,
    "quality": 0.10,
}
WEIGHTS_HOT = {
    "relevance": 0.35,
    "recency": 0.10,
    "popularity": 0.45,
    "quality": 0.10,
}


def calculate_relevance(
    *,
    metadata: PaperMetadata,
    profile: ResearchProfile,
) -> tuple[float, str | None, list[str]]:
    title = metadata.title.lower()
    abstract = metadata.abstract.lower()
    categories = set(metadata.categories)

    for keyword in profile.excluded_keywords:
        lowered = keyword.lower()
        if lowered in title or lowered in abstract:
            return 0.0, None, []

    best_score = 0.0
    best_domain: str | None = None
    best_keywords: list[str] = []
    for domain in profile.research_domains:
        score = 0.0
        matched_keywords: list[str] = []
        for keyword in domain.keywords:
            lowered = keyword.lower()
            if lowered in title:
                score += RELEVANCE_TITLE_KEYWORD_BOOST
                matched_keywords.append(keyword)
            elif lowered in abstract:
                score += RELEVANCE_ABSTRACT_KEYWORD_BOOST
                matched_keywords.append(keyword)
        for category in domain.arxiv_categories:
            if category in categories:
                score += RELEVANCE_CATEGORY_MATCH_BOOST
                matched_keywords.append(category)
        score += min(domain.priority, 5) * 0.05
        if score > best_score:
            best_score = score
            best_domain = domain.name
            best_keywords = matched_keywords
    return best_score, best_domain, best_keywords


def calculate_recency(published_at: datetime | None, *, now: datetime) -> float:
    if published_at is None:
        return 0.0
    if published_at.tzinfo is not None and now.tzinfo is None:
        now = now.astimezone(published_at.tzinfo)
    days = (now - published_at).days
    if days <= 30:
        return 3.0
    if days <= 90:
        return 2.0
    if days <= 180:
        return 1.0
    return 0.0


def calculate_quality(abstract: str) -> float:
    abstract_lower = abstract.lower()
    score = 0.0
    strong_innovation = [
        "state-of-the-art",
        "sota",
        "breakthrough",
        "first",
        "surpass",
        "outperform",
        "pioneering",
    ]
    weak_innovation = [
        "novel",
        "propose",
        "introduce",
        "new approach",
        "new method",
        "innovative",
    ]
    method_indicators = ["framework", "architecture", "algorithm", "mechanism", "pipeline"]
    quantitative_indicators = [
        "outperforms",
        "improves by",
        "achieves",
        "accuracy",
        "f1",
        "bleu",
        "rouge",
        "beats",
        "surpasses",
    ]
    experiment_indicators = ["experiment", "evaluation", "benchmark", "ablation", "baseline"]

    strong_count = sum(1 for item in strong_innovation if item in abstract_lower)
    weak_count = sum(1 for item in weak_innovation if item in abstract_lower)
    if strong_count >= 2:
        score += 1.0
    elif strong_count == 1:
        score += 0.7
    elif weak_count > 0:
        score += 0.3

    if any(item in abstract_lower for item in method_indicators):
        score += 0.5
    if any(item in abstract_lower for item in quantitative_indicators):
        score += 0.8
    elif any(item in abstract_lower for item in experiment_indicators):
        score += 0.4

    return min(score, SCORE_MAX)


def calculate_popularity(
    *, influential_citation_count: int, citation_count: int, is_hot_paper: bool
) -> float:
    if is_hot_paper:
        return min(
            influential_citation_count / (POPULARITY_INFLUENTIAL_CITATION_FULL_SCORE / SCORE_MAX),
            SCORE_MAX,
        )
    if citation_count >= 100:
        return 3.0
    if citation_count >= 30:
        return 2.0
    if citation_count >= 10:
        return 1.0
    return 0.0


def calculate_recommendation_score(
    *,
    relevance: float,
    recency: float,
    popularity: float,
    quality: float,
    is_hot_paper: bool,
) -> RecommendationScores:
    normalized = {
        "relevance": (relevance / SCORE_MAX) * 10,
        "recency": (recency / SCORE_MAX) * 10,
        "popularity": (popularity / SCORE_MAX) * 10,
        "quality": (quality / SCORE_MAX) * 10,
    }
    weights = WEIGHTS_HOT if is_hot_paper else WEIGHTS_NORMAL
    recommendation = round(sum(normalized[name] * weights[name] for name in weights), 2)
    return RecommendationScores(
        relevance=round(relevance, 2),
        recency=round(recency, 2),
        popularity=round(popularity, 2),
        quality=round(quality, 2),
        recommendation=recommendation,
    )
