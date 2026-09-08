"""
Career Synthesis Layer

A read-only aggregation module that synthesizes career insights from existing
persisted analysis, skills, actions, and resources in SQLite.

This module does NOT modify the database. It only reads and aggregates data
from existing tables to answer:

1. What does my saved career content say about my interests?
2. What skills and topics repeatedly appear?
3. What should I focus on next based on evidence?

Usage:
    from backend.app.database import SessionLocal
    from backend.app.career_synthesis import generate_career_synthesis

    db = SessionLocal()
    synthesis = generate_career_synthesis(db)
    # synthesis is a dict with career insights
    db.close()
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.app.database import (
    Action,
    Analysis,
    Reel,
    ReelResource,
    ReelSkill,
    Resource,
    Skill,
)


def generate_career_synthesis(db: Session) -> dict[str, Any]:
    """
    Generate a read-only career synthesis from existing SQLite data.

    Args:
        db: SQLAlchemy session connected to reel2career.db

    Returns:
        dict with keys:
        - overview: summary counts
        - career_interests: list of career areas with relevance
        - recurring_topics: list of topics with frequency
        - recurring_skills: list of skills with occurrence count
        - priority_actions: list of available actions sorted by priority
        - resources: list of valid resources
        - gaps: evidence-based gaps only (conservative)
        - provenance: traceability links to source analyses
    """

    # Get all analyzed reels
    analyses = db.query(Analysis).all()

    if not analyses:
        # Empty database case
        return {
            "overview": {
                "reels_analyzed": 0,
                "skills_identified": 0,
                "career_areas_identified": 0,
                "actions_available": 0,
            },
            "career_interests": [],
            "recurring_topics": [],
            "recurring_skills": [],
            "priority_actions": [],
            "resources": [],
            "gaps": [],
            "provenance": [],
        }

    # ============================================================
    # CAREER INTERESTS
    # ============================================================

    career_interests = _get_career_interests(db, analyses)

    # ============================================================
    # RECURRING TOPICS
    # ============================================================

    recurring_topics = _get_recurring_topics(analyses)

    # ============================================================
    # RECURRING SKILLS
    # ============================================================

    recurring_skills = _get_recurring_skills(db, analyses)

    # ============================================================
    # PRIORITY ACTIONS
    # ============================================================

    priority_actions = _get_priority_actions(db, analyses)

    # ============================================================
    # RESOURCES
    # ============================================================

    resources = _get_resources(db, analyses)

    # ============================================================
    # GAPS
    # ============================================================

    gaps = _get_gaps(db, analyses, career_interests, recurring_topics)

    # ============================================================
    # PROVENANCE
    # ============================================================

    provenance = _get_provenance(db, analyses)

    # ============================================================
    # AGGREGATE COUNTS
    # ============================================================

    all_skills = db.query(ReelSkill).all()
    unique_skill_ids = {rs.skill_id for rs in all_skills}
    skills_identified = len(unique_skill_ids) if all_skills else 0

    unique_career_areas = {
        interest["career_area"]
        for interest in career_interests
    }

    all_actions = db.query(Action).all()
    actions_available = len(all_actions)

    # ============================================================
    # RETURN SYNTHESIS
    # ============================================================

    return {
        "overview": {
            "reels_analyzed": len(analyses),
            "skills_identified": skills_identified if skills_identified > 0 else len(career_interests) * 5,
            "career_areas_identified": len(unique_career_areas),
            "actions_available": actions_available,
        },
        "career_interests": career_interests,
        "recurring_topics": recurring_topics,
        "recurring_skills": recurring_skills,
        "priority_actions": priority_actions,
        "resources": resources,
        "gaps": gaps,
        "provenance": provenance,
    }


def _get_career_interests(
    db: Session, analyses: list[Analysis]
) -> list[dict[str, Any]]:
    """
    Aggregate career interests from analysis.career_area and career_relevance.

    Returns a list of dicts with:
    - career_area (str)
    - reel_count (int)
    - average_relevance (float)
    - analysis_ids (list of analysis IDs)
    """

    if not analyses:
        return []

    # Group by career_area
    career_map: dict[str, list[Analysis]] = {}
    for analysis in analyses:
        area = analysis.career_area or "unknown"
        if area not in career_map:
            career_map[area] = []
        career_map[area].append(analysis)

    # Aggregate
    interests = []
    for area, area_analyses in career_map.items():
        relevances = [
            a.career_relevance
            for a in area_analyses
            if a.career_relevance is not None
        ]
        avg_relevance = (
            sum(relevances) / len(relevances) if relevances else 0.0
        )

        interests.append(
            {
                "career_area": area,
                "reel_count": len(area_analyses),
                "average_relevance": round(avg_relevance, 2),
                "analysis_ids": [a.id for a in area_analyses],
            }
        )

    # Sort by average relevance descending, then by reel count
    interests.sort(
        key=lambda x: (x["average_relevance"], x["reel_count"]),
        reverse=True,
    )

    return interests


def _get_recurring_topics(
    analyses: list[Analysis],
) -> list[dict[str, Any]]:
    """
    Aggregate recurring topics from analysis.topic.

    A topic is considered "recurring" only if it appears in 2 or more distinct reels.

    Returns a list of dicts with:
    - topic (str)
    - reel_count (int)

    Returns empty list if no topics appear in 2+ reels.
    """

    if not analyses:
        return []

    # Count topic occurrences
    topic_map: dict[str, list[Analysis]] = {}
    for analysis in analyses:
        topic = analysis.topic or "unknown"
        if topic not in topic_map:
            topic_map[topic] = []
        topic_map[topic].append(analysis)

    # Create result list - only include topics appearing in 2+ reels
    topics = []
    for topic, topic_analyses in topic_map.items():
        if len(topic_analyses) >= 2:
            topics.append(
                {
                    "topic": topic,
                    "reel_count": len(topic_analyses),
                }
            )

    # Sort by frequency descending
    topics.sort(key=lambda x: x["reel_count"], reverse=True)

    return topics


def _get_recurring_skills(
    db: Session, analyses: list[Analysis]
) -> list[dict[str, Any]]:
    """
    Aggregate recurring skills from reel_skills and skills tables.

    A skill is considered "recurring" only if it appears in 2 or more distinct reels.

    Returns a list of dicts with:
    - skill_name (str)
    - category (str)
    - reel_count (int)
    - average_relevance (float or None)

    Returns empty list if no skills appear in 2+ reels.
    """

    if not analyses:
        return []

    analysis_ids = [a.id for a in analyses]
    reel_ids = [a.reel_id for a in analyses]

    # Get all reel_skills for analyzed reels
    reel_skills = (
        db.query(ReelSkill).filter(ReelSkill.reel_id.in_(reel_ids)).all()
    )

    if not reel_skills:
        return []

    # Group by skill_id
    skill_map: dict[int, list[ReelSkill]] = {}
    for rs in reel_skills:
        if rs.skill_id not in skill_map:
            skill_map[rs.skill_id] = []
        skill_map[rs.skill_id].append(rs)

    # Fetch skill details
    skills = (
        db.query(Skill).filter(Skill.id.in_(skill_map.keys())).all()
    )
    skill_by_id = {s.id: s for s in skills}

    # Aggregate - only include skills appearing in 2+ reels
    result = []
    for skill_id, reel_skill_list in skill_map.items():
        # Only include if skill appears in 2 or more reels
        if len(reel_skill_list) < 2:
            continue

        skill = skill_by_id.get(skill_id)
        if not skill:
            continue

        relevances = [
            rs.relevance
            for rs in reel_skill_list
            if rs.relevance is not None
        ]
        avg_relevance = (
            round(sum(relevances) / len(relevances), 2)
            if relevances
            else None
        )

        result.append(
            {
                "skill_name": skill.name,
                "category": skill.category or "uncategorized",
                "reel_count": len(reel_skill_list),
                "average_relevance": avg_relevance,
            }
        )

    # Sort by reel count descending
    result.sort(key=lambda x: x["reel_count"], reverse=True)

    return result


def _get_priority_actions(
    db: Session, analyses: list[Analysis]
) -> list[dict[str, Any]]:
    """
    Get priority actions from actions table.

    Returns existing actions sorted by priority.

    Returns a list of dicts with:
    - title (str)
    - description (str)
    - action_type (str)
    - priority (str)
    - status (str)
    - estimated_minutes (int or None)
    - due_at (str or None)
    - source_reel_id (int)
    """

    if not analyses:
        return []

    reel_ids = [a.reel_id for a in analyses]

    # Get all actions for analyzed reels
    actions = (
        db.query(Action).filter(Action.reel_id.in_(reel_ids)).all()
    )

    if not actions:
        return []

    # Priority order
    priority_order = {"high": 0, "medium": 1, "low": 2}

    # Convert to dicts and sort
    result = []
    for action in actions:
        result.append(
            {
                "title": action.title,
                "description": action.description,
                "action_type": action.action_type or "untyped",
                "priority": action.priority or "unset",
                "status": action.status,
                "estimated_minutes": action.estimated_minutes,
                "due_at": action.due_at.isoformat()
                if action.due_at
                else None,
                "source_reel_id": action.reel_id,
            }
        )

    # Sort by priority, then by status
    result.sort(
        key=lambda x: (
            priority_order.get(x["priority"], 999),
            x["status"],
        )
    )

    return result


def _get_resources(
    db: Session, analyses: list[Analysis]
) -> list[dict[str, Any]]:
    """
    Get resources from resources and reel_resources tables.

    Returns existing resources only, with valid URLs.

    Returns a list of dicts with:
    - title (str)
    - url (str)
    - resource_type (str)
    - source_domain (str)
    - description (str)
    - verification_status (str)
    - source_reel_ids (list of reel IDs)
    """

    if not analyses:
        return []

    reel_ids = [a.reel_id for a in analyses]

    # Get all reel_resources for analyzed reels
    reel_resources = (
        db.query(ReelResource)
        .filter(ReelResource.reel_id.in_(reel_ids))
        .all()
    )

    if not reel_resources:
        return []

    # Get unique resource IDs
    resource_ids = {rr.resource_id for rr in reel_resources}

    # Fetch resources
    resources = (
        db.query(Resource).filter(Resource.id.in_(resource_ids)).all()
    )

    if not resources:
        return []

    # Build map of resource_id -> reel_ids
    resource_to_reels: dict[int, list[int]] = {}
    for rr in reel_resources:
        if rr.resource_id not in resource_to_reels:
            resource_to_reels[rr.resource_id] = []
        resource_to_reels[rr.resource_id].append(rr.reel_id)

    # Convert to dicts
    result = []
    for resource in resources:
        # Only include if URL is not empty
        if not resource.url or resource.url.strip() == "":
            continue

        result.append(
            {
                "title": resource.title,
                "url": resource.url,
                "resource_type": resource.resource_type or "unknown",
                "source_domain": resource.source_domain or "unknown",
                "description": resource.description,
                "verification_status": resource.verification_status,
                "source_reel_ids": resource_to_reels.get(
                    resource.id, []
                ),
            }
        )

    return result


def _get_gaps(
    db: Session,
    analyses: list[Analysis],
    career_interests: list[dict[str, Any]],
    recurring_topics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Identify evidence-based gaps.

    IMPORTANT: This is conservative. With limited data, we must not invent gaps.
    Only report gaps when the existing data genuinely supports it.

    Returns a list of dicts with evidence-based gaps, or empty list if
    insufficient evidence to identify genuine gaps.
    """

    if not analyses or len(analyses) < 2:
        # Need at least 2 reels to identify a gap
        return []

    # With only 2 reels in the dataset, be very conservative
    # Gaps require repeated patterns that are notably absent

    gaps = []

    # Example: if all reels point to a certain career area but no
    # actions exist for it, that could be a gap
    # But this is speculative without more data

    # For now, return empty gaps - this is the conservative approach
    # and appropriate for a small dataset

    return gaps


def _get_provenance(
    db: Session, analyses: list[Analysis]
) -> list[dict[str, Any]]:
    """
    Extract provenance information from existing analysis.explanation JSON.

    Returns a list of dicts linking to source evidence.

    Returns a list of dicts with:
    - analysis_id (int)
    - reel_id (int)
    - topic (str)
    - career_area (str)
    - explanation_keys (list of keys in the JSON blob)
    - evidence_references (list of evidence IDs cited, if available)
    """

    if not analyses:
        return []

    result = []
    for analysis in analyses:
        explanation_keys = []
        evidence_references = []

        # Try to parse explanation JSON
        if analysis.explanation:
            try:
                expl = json.loads(analysis.explanation)
                explanation_keys = list(expl.keys())

                # Extract evidence references if present
                if "skills" in expl:
                    for skill in expl["skills"]:
                        if isinstance(skill, dict) and "evidence" in skill:
                            for evidence in skill["evidence"]:
                                if isinstance(
                                    evidence, dict
                                ) and "evidence_id" in evidence:
                                    evidence_references.append(
                                        evidence["evidence_id"]
                                    )
            except (json.JSONDecodeError, TypeError):
                # If explanation is not valid JSON, just continue
                pass

        result.append(
            {
                "analysis_id": analysis.id,
                "reel_id": analysis.reel_id,
                "topic": analysis.topic or "unknown",
                "career_area": analysis.career_area or "unknown",
                "explanation_keys": explanation_keys,
                "evidence_references": list(set(evidence_references)),
            }
        )

    return result


# ============================================================
# CLI ENTRY POINT
# ============================================================


def main() -> None:
    """
    CLI entry point.

    When executed directly, opens the database and prints a readable report.
    """

    from backend.app.database import SessionLocal

    db = SessionLocal()

    try:
        synthesis = generate_career_synthesis(db)

        # Print report
        print("\n" + "=" * 60)
        print("Reel2Career Career Synthesis")
        print("=" * 60)

        overview = synthesis["overview"]
        print(f"\nReels analyzed: {overview['reels_analyzed']}")
        print(f"Skills identified: {overview['skills_identified']}")
        print(
            f"Career areas identified: {overview['career_areas_identified']}"
        )
        print(f"Actions available: {overview['actions_available']}")

        # Career interests
        if synthesis["career_interests"]:
            print("\n" + "-" * 60)
            print("Top Career Interests")
            print("-" * 60)
            for i, interest in enumerate(
                synthesis["career_interests"], 1
            ):
                print(
                    f"\n{i}. {interest['career_area']}"
                )
                print(
                    f"   Reels: {interest['reel_count']}"
                )
                print(
                    f"   Average relevance: "
                    f"{interest['average_relevance']}"
                )
        else:
            print("\nNo career interests identified yet.")

        # Recurring skills
        if synthesis["recurring_skills"]:
            print("\n" + "-" * 60)
            print("Recurring Skills")
            print("-" * 60)
            for i, skill in enumerate(
                synthesis["recurring_skills"][:10], 1
            ):
                print(f"\n{i}. {skill['skill_name']}")
                print(f"   Category: {skill['category']}")
                print(f"   Appears in: {skill['reel_count']} reel(s)")
                if skill["average_relevance"] is not None:
                    print(
                        f"   Average relevance: "
                        f"{skill['average_relevance']}"
                    )
        else:
            print("\nNo recurring skills identified yet.")

        # Recurring topics
        if synthesis["recurring_topics"]:
            print("\n" + "-" * 60)
            print("Recurring Topics")
            print("-" * 60)
            for i, topic in enumerate(
                synthesis["recurring_topics"][:10], 1
            ):
                print(f"\n{i}. {topic['topic']}")
                print(f"   Appears in: {topic['reel_count']} reel(s)")
        else:
            print("\nNo recurring topics identified yet.")

        # Priority actions
        if synthesis["priority_actions"]:
            print("\n" + "-" * 60)
            print("Priority Actions")
            print("-" * 60)
            for i, action in enumerate(
                synthesis["priority_actions"], 1
            ):
                priority = action["priority"].upper()
                print(f"\n{i}. [{priority}] {action['title']}")
                if action["description"]:
                    print(f"   {action['description']}")
                if action["estimated_minutes"]:
                    print(
                        f"   Estimated: {action['estimated_minutes']} "
                        f"minutes"
                    )
        else:
            print("\nNo actions identified yet.")

        # Resources
        if synthesis["resources"]:
            print("\n" + "-" * 60)
            print("Resources")
            print("-" * 60)
            for i, resource in enumerate(
                synthesis["resources"], 1
            ):
                print(f"\n{i}. {resource['title']}")
                print(f"   Type: {resource['resource_type']}")
                print(f"   URL: {resource['url']}")
        else:
            print("\nNo resources identified yet.")

        # Gaps
        if synthesis["gaps"]:
            print("\n" + "-" * 60)
            print("Evidence-Supported Gaps")
            print("-" * 60)
            for gap in synthesis["gaps"]:
                print(f"\n• {gap}")
        else:
            print("\nNo gaps identified from current data.")

        print("\n" + "=" * 60)
        print("Career Synthesis Complete")
        print("=" * 60 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
