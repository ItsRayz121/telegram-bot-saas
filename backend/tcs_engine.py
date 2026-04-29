"""
Telegizer Community Score (TCS) — channel authenticity scoring engine.

Score: 0–100. Grade: A (80+) B (65+) C (50+) D (35+) F (<35)

Signals (weights):
  view_rate       30 pts  — avg_views / member_count. Low reach = fake members.
  engagement_rate 35 pts  — reactions / views. Near-zero = bot reactions.
  consistency     20 pts  — coefficient of variation of per-post views. Spiky = purchased.
  forward_rate    15 pts  — forwards / views. Real content gets shared.
"""
from datetime import datetime
import math


def _clamp(val, lo=0.0, hi=1.0):
    return max(lo, min(hi, val))


def _grade(score: int) -> str:
    if score >= 80: return "A"
    if score >= 65: return "B"
    if score >= 50: return "C"
    if score >= 35: return "D"
    return "F"


def _score_view_rate(avg_views: float, member_count: int) -> dict:
    """What fraction of subscribers actually see posts."""
    if not member_count:
        return {"score": 0, "max": 30, "value": 0, "label": "View Rate", "note": "No member data"}

    rate = avg_views / member_count
    # Thresholds: >0.40 full, 0.20–0.40 good, 0.08–0.20 moderate, 0.03–0.08 low, <0.03 very low
    if rate >= 0.40:
        pts = 30
    elif rate >= 0.20:
        pts = int(20 + (rate - 0.20) / 0.20 * 10)
    elif rate >= 0.08:
        pts = int(10 + (rate - 0.08) / 0.12 * 10)
    elif rate >= 0.03:
        pts = int(3 + (rate - 0.03) / 0.05 * 7)
    else:
        pts = int(rate / 0.03 * 3)

    return {
        "score": pts,
        "max": 30,
        "value": round(rate * 100, 1),
        "unit": "%",
        "label": "View Rate",
        "note": _view_rate_note(rate),
    }


def _view_rate_note(rate: float) -> str:
    if rate >= 0.40: return "Excellent reach — most subscribers see posts"
    if rate >= 0.20: return "Good reach for this channel size"
    if rate >= 0.08: return "Average reach — some inactive followers"
    if rate >= 0.03: return "Low reach — possible inactive or fake members"
    return "Very low reach — high bot/inactive member risk"


def _score_engagement(engagement_rate_pct: float) -> dict:
    """Reactions / views as a percentage."""
    rate = engagement_rate_pct  # already a percentage
    if rate >= 3.0:
        pts = 35
    elif rate >= 1.5:
        pts = int(28 + (rate - 1.5) / 1.5 * 7)
    elif rate >= 0.5:
        pts = int(18 + (rate - 0.5) / 1.0 * 10)
    elif rate >= 0.1:
        pts = int(6 + (rate - 0.1) / 0.4 * 12)
    else:
        pts = int(rate / 0.1 * 6)

    return {
        "score": pts,
        "max": 35,
        "value": round(rate, 2),
        "unit": "%",
        "label": "Engagement Rate",
        "note": _engagement_note(rate),
    }


def _engagement_note(rate: float) -> str:
    if rate >= 3.0: return "Highly engaged audience — very authentic"
    if rate >= 1.5: return "Strong engagement — healthy community"
    if rate >= 0.5: return "Average engagement for Telegram channels"
    if rate >= 0.1: return "Low engagement — possible bot reactions"
    return "Near-zero engagement — likely inflated subscriber count"


def _score_consistency(view_list: list) -> dict:
    """Coefficient of variation (std/mean) of post views. Lower = more consistent."""
    if len(view_list) < 3:
        return {
            "score": 10,  # neutral when not enough data
            "max": 20,
            "value": None,
            "label": "Post Consistency",
            "note": "Need at least 3 posts to score consistency",
        }

    mean = sum(view_list) / len(view_list)
    if mean == 0:
        return {"score": 0, "max": 20, "value": None, "label": "Post Consistency", "note": "No views recorded"}

    variance = sum((v - mean) ** 2 for v in view_list) / len(view_list)
    cv = math.sqrt(variance) / mean  # coefficient of variation

    # cv < 0.3 = very consistent = great; cv > 1.5 = very spiky = suspicious
    if cv <= 0.3:
        pts = 20
    elif cv <= 0.6:
        pts = int(15 + (0.6 - cv) / 0.3 * 5)
    elif cv <= 1.0:
        pts = int(8 + (1.0 - cv) / 0.4 * 7)
    elif cv <= 1.5:
        pts = int(2 + (1.5 - cv) / 0.5 * 6)
    else:
        pts = 0

    return {
        "score": max(0, pts),
        "max": 20,
        "value": round(cv, 2),
        "label": "Post Consistency",
        "note": _consistency_note(cv),
    }


def _consistency_note(cv: float) -> str:
    if cv <= 0.3: return "Very consistent views — organic audience"
    if cv <= 0.6: return "Consistent performance across posts"
    if cv <= 1.0: return "Some variance — normal for most channels"
    if cv <= 1.5: return "High variance — possible view purchases on select posts"
    return "Very spiky view counts — strong indicator of purchased views"


def _score_forward_rate(avg_forwards: float, avg_views: float) -> dict:
    """Forwards / views. Real content gets shared."""
    if not avg_views:
        return {"score": 5, "max": 15, "value": 0, "label": "Forward Rate", "note": "No view data"}

    rate = avg_forwards / avg_views
    if rate >= 0.05:
        pts = 15
    elif rate >= 0.02:
        pts = int(10 + (rate - 0.02) / 0.03 * 5)
    elif rate >= 0.005:
        pts = int(4 + (rate - 0.005) / 0.015 * 6)
    else:
        pts = int(rate / 0.005 * 4)

    return {
        "score": max(0, pts),
        "max": 15,
        "value": round(rate * 100, 2),
        "unit": "%",
        "label": "Forward Rate",
        "note": _forward_note(rate),
    }


def _forward_note(rate: float) -> str:
    if rate >= 0.05: return "High share rate — content resonates strongly"
    if rate >= 0.02: return "Good share rate — valuable content"
    if rate >= 0.005: return "Low share rate — typical for niche channels"
    return "Very low share rate — possible bot audience"


def compute_tcs(channel, posts: list) -> dict:
    """
    Compute TCS for a Channel object.
    Returns dict with score, grade, breakdown, recommendations.
    """
    view_list = [p.views for p in posts if p.views > 0]

    s_view = _score_view_rate(channel.avg_views or 0, channel.member_count or 0)
    s_eng = _score_engagement(channel.engagement_rate or 0)
    s_cons = _score_consistency(view_list)
    s_fwd = _score_forward_rate(channel.avg_forwards or 0, channel.avg_views or 0)

    total = s_view["score"] + s_eng["score"] + s_cons["score"] + s_fwd["score"]
    total = max(0, min(100, total))
    grade = _grade(total)

    breakdown = [s_view, s_eng, s_cons, s_fwd]
    recommendations = _build_recommendations(s_view, s_eng, s_cons, s_fwd, len(posts))

    return {
        "score": total,
        "grade": grade,
        "breakdown": breakdown,
        "recommendations": recommendations,
        "posts_analyzed": len(view_list),
        "computed_at": datetime.utcnow().isoformat(),
    }


def _build_recommendations(s_view, s_eng, s_cons, s_fwd, post_count: int) -> list:
    recs = []
    if post_count < 5:
        recs.append("Publish at least 5 posts so TCS has enough data to score accurately.")
    if s_view["score"] < 10:
        recs.append("View rate is very low. Consider cleaning inactive subscribers or improving post timing.")
    if s_eng["score"] < 10:
        recs.append("Engagement is near zero. Encourage reactions by adding polls and questions to posts.")
    if s_cons.get("value") and s_cons["value"] > 1.2:
        recs.append("View counts are very spiky. Avoid purchased view services — they flag your channel as inauthentic.")
    if s_fwd["score"] < 5:
        recs.append("Posts are rarely forwarded. Focus on shareable, high-value content.")
    if not recs:
        recs.append("Your channel looks authentic. Keep publishing consistent, engaging content.")
    return recs
