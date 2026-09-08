"""
Tests for the career synthesis module.

Uses an in-memory SQLite database to ensure isolated, repeatable tests
without modifying the live database.
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.career_synthesis import (
    generate_career_synthesis,
    _get_career_interests,
    _get_recurring_topics,
    _get_recurring_skills,
    _get_priority_actions,
    _get_resources,
    _get_gaps,
    _get_provenance,
)
from backend.app.database import (
    Action,
    Analysis,
    Base,
    Reel,
    ReelResource,
    ReelSkill,
    Resource,
    Skill,
)


@pytest.fixture
def test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestEmptyDatabase:
    """Test synthesis with empty database."""

    def test_empty_database_returns_zeros(self, test_db):
        """Empty database should return zero counts and empty lists."""
        result = generate_career_synthesis(test_db)

        assert result["overview"]["reels_analyzed"] == 0
        assert result["overview"]["skills_identified"] == 0
        assert result["overview"]["career_areas_identified"] == 0
        assert result["overview"]["actions_available"] == 0

        assert result["career_interests"] == []
        assert result["recurring_topics"] == []
        assert result["recurring_skills"] == []
        assert result["priority_actions"] == []
        assert result["resources"] == []
        assert result["gaps"] == []
        assert result["provenance"] == []


class TestSingleReel:
    """Test synthesis with one analyzed reel."""

    def test_single_reel_analysis(self, test_db):
        """One reel should produce counts of 1 and appropriate data."""
        # Create a reel
        reel = Reel(
            instagram_id="test_123",
            caption="Test reel",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create an analysis
        provenance = {
            "career_relevance_reason": "Test reason",
            "skills": [],
            "actions": [],
            "resources": [],
        }
        analysis = Analysis(
            reel_id=reel.id,
            summary="Test summary",
            topic="Test Topic",
            career_area="Software Engineering",
            career_relevance=0.85,
            difficulty="intermediate",
            priority="high",
            explanation=json.dumps(provenance),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert result["overview"]["reels_analyzed"] == 1
        assert result["overview"]["career_areas_identified"] == 1
        assert result["overview"]["actions_available"] == 0

        assert len(result["career_interests"]) == 1
        assert result["career_interests"][0]["career_area"] == "Software Engineering"
        assert result["career_interests"][0]["average_relevance"] == 0.85
        assert result["career_interests"][0]["reel_count"] == 1

        # With only 1 reel, topics are NOT recurring (need 2+ reels to recur)
        assert len(result["recurring_topics"]) == 0


class TestRecurringSkills:
    """Test identification of recurring skills across multiple reels."""

    def test_skill_appears_multiple_times(self, test_db):
        """Skill appearing in multiple reels should be counted correctly."""
        # Create two reels
        reel1 = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        reel2 = Reel(
            instagram_id="reel2",
            caption="Reel 2",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([reel1, reel2])
        test_db.commit()

        # Create analyses
        analysis1 = Analysis(
            reel_id=reel1.id,
            summary="Summary 1",
            topic="Topic 1",
            career_area="Security",
            career_relevance=0.9,
            explanation=json.dumps({"skills": []}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        analysis2 = Analysis(
            reel_id=reel2.id,
            summary="Summary 2",
            topic="Topic 2",
            career_area="Security",
            career_relevance=0.85,
            explanation=json.dumps({"skills": []}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([analysis1, analysis2])
        test_db.commit()

        # Create a shared skill
        skill = Skill(
            name="Data Flow Auditing",
            category="security",
            description="Test skill",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(skill)
        test_db.commit()

        # Link skill to both reels
        reel_skill1 = ReelSkill(
            reel_id=reel1.id,
            skill_id=skill.id,
            relevance=0.9,
        )
        reel_skill2 = ReelSkill(
            reel_id=reel2.id,
            skill_id=skill.id,
            relevance=0.85,
        )
        test_db.add_all([reel_skill1, reel_skill2])
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["recurring_skills"]) >= 1
        # Find the Data Flow Auditing skill
        skill_result = next(
            (s for s in result["recurring_skills"]
             if s["skill_name"] == "Data Flow Auditing"),
            None
        )
        assert skill_result is not None
        assert skill_result["reel_count"] == 2
        # Average of 0.9 and 0.85 is 0.875, rounded to 0.88
        assert skill_result["average_relevance"] == 0.88

    def test_single_reel_skills_excluded_from_recurring(self, test_db):
        """Skills appearing in only 1 reel should NOT be in recurring_skills."""
        # Create one reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Security",
            career_relevance=0.9,
            explanation=json.dumps({"skills": []}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        # Create a skill
        skill = Skill(
            name="Single Reel Skill",
            category="security",
            description="Test skill",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(skill)
        test_db.commit()

        # Link skill to only this reel
        reel_skill = ReelSkill(
            reel_id=reel.id,
            skill_id=skill.id,
            relevance=0.9,
        )
        test_db.add(reel_skill)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        # The skill should NOT appear in recurring_skills
        skill_result = next(
            (s for s in result["recurring_skills"]
             if s["skill_name"] == "Single Reel Skill"),
            None
        )
        assert skill_result is None, "Single-reel skills should not be recurring"


class TestRecurringCareerArea:
    """Test identification of recurring career areas."""

    def test_career_area_repeated(self, test_db):
        """Repeated career area should aggregate correctly."""
        # Create two reels
        reel1 = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        reel2 = Reel(
            instagram_id="reel2",
            caption="Reel 2",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([reel1, reel2])
        test_db.commit()

        # Both analyses have same career area
        analysis1 = Analysis(
            reel_id=reel1.id,
            summary="Summary 1",
            topic="Topic 1",
            career_area="Cybersecurity",
            career_relevance=0.95,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        analysis2 = Analysis(
            reel_id=reel2.id,
            summary="Summary 2",
            topic="Topic 2",
            career_area="Cybersecurity",
            career_relevance=0.80,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([analysis1, analysis2])
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["career_interests"]) == 1
        assert result["career_interests"][0]["career_area"] == "Cybersecurity"
        assert result["career_interests"][0]["reel_count"] == 2
        # Average of 0.95 and 0.80 is 0.875, rounded to 0.88
        assert result["career_interests"][0]["average_relevance"] == 0.88


class TestRecurringTopic:
    """Test identification of recurring topics."""

    def test_topic_repeated(self, test_db):
        """Repeated topic should aggregate correctly."""
        # Create two reels
        reel1 = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        reel2 = Reel(
            instagram_id="reel2",
            caption="Reel 2",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([reel1, reel2])
        test_db.commit()

        # Both analyses have same topic
        analysis1 = Analysis(
            reel_id=reel1.id,
            summary="Summary 1",
            topic="API Security",
            career_area="Security",
            career_relevance=0.9,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        analysis2 = Analysis(
            reel_id=reel2.id,
            summary="Summary 2",
            topic="API Security",
            career_area="Security",
            career_relevance=0.85,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add_all([analysis1, analysis2])
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["recurring_topics"]) == 1
        assert result["recurring_topics"][0]["topic"] == "API Security"
        assert result["recurring_topics"][0]["reel_count"] == 2

    def test_single_reel_topics_excluded_from_recurring(self, test_db):
        """Topics appearing in only 1 reel should NOT be in recurring_topics."""
        # Create one reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis with a unique topic
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Unique Topic Only In This Reel",
            career_area="Security",
            career_relevance=0.9,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        # The topic should NOT appear in recurring_topics
        topic_result = next(
            (t for t in result["recurring_topics"]
             if t["topic"] == "Unique Topic Only In This Reel"),
            None
        )
        assert topic_result is None, "Single-reel topics should not be recurring"


class TestActionPriorityOrdering:
    """Test that actions are ordered correctly by priority."""

    def test_actions_sorted_by_priority(self, test_db):
        """Actions should be sorted: high -> medium -> low."""
        # Create a reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Career",
            career_relevance=0.5,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        # Create actions with different priorities
        action_low = Action(
            reel_id=reel.id,
            title="Low Priority Action",
            priority="low",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        action_high = Action(
            reel_id=reel.id,
            title="High Priority Action",
            priority="high",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        action_medium = Action(
            reel_id=reel.id,
            title="Medium Priority Action",
            priority="medium",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add_all([action_low, action_high, action_medium])
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["priority_actions"]) == 3
        # Check order: high, medium, low
        assert result["priority_actions"][0]["priority"] == "high"
        assert result["priority_actions"][1]["priority"] == "medium"
        assert result["priority_actions"][2]["priority"] == "low"


class TestResourceAggregation:
    """Test that resources are aggregated and exposed correctly."""

    def test_resources_with_valid_urls(self, test_db):
        """Only resources with valid URLs should be returned."""
        # Create a reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Career",
            career_relevance=0.5,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        # Create resources
        resource = Resource(
            title="GitHub Security Guide",
            url="https://github.com/bearer/bearer",
            resource_type="repository",
            source_domain="github.com",
            description="Security auditing tool",
            verification_status="unverified",
            created_at=datetime.now(timezone.utc),
        )
        test_db.add(resource)
        test_db.commit()

        # Link resource to reel
        reel_resource = ReelResource(
            reel_id=reel.id,
            resource_id=resource.id,
        )
        test_db.add(reel_resource)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["resources"]) == 1
        assert result["resources"][0]["title"] == "GitHub Security Guide"
        assert result["resources"][0]["url"] == "https://github.com/bearer/bearer"
        assert result["resources"][0]["source_domain"] == "github.com"


class TestGapsConservative:
    """Test that gaps are not fabricated with insufficient evidence."""

    def test_no_gaps_with_small_dataset(self, test_db):
        """With only 1-2 reels, gaps should not be fabricated."""
        # Create one reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Career",
            career_relevance=0.5,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        # With only 1 reel, gaps should be empty
        assert result["gaps"] == []


class TestProvenancePreservation:
    """Test that provenance links are preserved."""

    def test_provenance_links_preserved(self, test_db):
        """Provenance should preserve analysis and evidence references."""
        # Create a reel
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        # Create analysis with provenance
        provenance = {
            "career_relevance_reason": "Test",
            "skills": [
                {
                    "name": "Test Skill",
                    "evidence": [
                        {"evidence_id": 1, "quote": "Test quote"},
                        {"evidence_id": 2, "quote": "Another quote"},
                    ]
                }
            ],
            "validation": {"all_grounded": True}
        }
        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Career",
            career_relevance=0.5,
            explanation=json.dumps(provenance),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        result = generate_career_synthesis(test_db)

        assert len(result["provenance"]) == 1
        prov = result["provenance"][0]
        assert prov["analysis_id"] == analysis.id
        assert prov["reel_id"] == reel.id
        assert "career_relevance_reason" in prov["explanation_keys"]
        assert "skills" in prov["explanation_keys"]
        assert "validation" in prov["explanation_keys"]
        # Evidence references should include 1 and 2
        assert set(prov["evidence_references"]) == {1, 2}


class TestReadOnlyBehavior:
    """Test that synthesis does not write to database."""

    def test_no_writes_to_database(self, test_db):
        """Synthesis should not insert, update, or delete records."""
        # Create initial data
        reel = Reel(
            instagram_id="reel1",
            caption="Reel 1",
            synced_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(reel)
        test_db.commit()

        analysis = Analysis(
            reel_id=reel.id,
            summary="Summary",
            topic="Topic",
            career_area="Career",
            career_relevance=0.5,
            explanation=json.dumps({}),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(analysis)
        test_db.commit()

        # Count initial rows
        initial_reel_count = test_db.query(Reel).count()
        initial_analysis_count = test_db.query(Analysis).count()

        # Generate synthesis
        generate_career_synthesis(test_db)

        # Verify counts are unchanged
        assert test_db.query(Reel).count() == initial_reel_count
        assert test_db.query(Analysis).count() == initial_analysis_count


class TestComplexScenario:
    """Test a realistic scenario with multiple reels, skills, and actions."""

    def test_complex_dataset(self, test_db):
        """Test synthesis with a realistic dataset."""
        # Create 3 reels
        reels = []
        for i in range(3):
            reel = Reel(
                instagram_id=f"reel{i}",
                caption=f"Reel {i}",
                synced_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            test_db.add(reel)
            reels.append(reel)
        test_db.commit()

        # Create analyses
        analyses = []
        topics = ["Security", "Career Development", "Security"]
        areas = ["Cybersecurity", "Career Development", "Cybersecurity"]

        for i, reel in enumerate(reels):
            analysis = Analysis(
                reel_id=reel.id,
                summary=f"Summary {i}",
                topic=topics[i],
                career_area=areas[i],
                career_relevance=0.7 + (i * 0.1),
                explanation=json.dumps({"skills": []}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            test_db.add(analysis)
            analyses.append(analysis)
        test_db.commit()

        # Create skills
        skill_names = ["Security Awareness", "Interview Prep", "Data Auditing"]
        skills = []
        for name in skill_names:
            skill = Skill(
                name=name,
                category="security",
                description=f"Description of {name}",
                created_at=datetime.now(timezone.utc),
            )
            test_db.add(skill)
            skills.append(skill)
        test_db.commit()

        # Link skills to reels
        for i, reel in enumerate(reels):
            for j, skill in enumerate(skills):
                if j % (i + 1) == 0:  # Varied patterns
                    reel_skill = ReelSkill(
                        reel_id=reel.id,
                        skill_id=skill.id,
                        relevance=0.8 + (i * 0.05),
                    )
                    test_db.add(reel_skill)
        test_db.commit()

        # Create actions
        for i, reel in enumerate(reels):
            action = Action(
                reel_id=reel.id,
                title=f"Action {i}",
                priority="high" if i == 0 else "medium",
                status="pending",
                estimated_minutes=30 * (i + 1),
                created_at=datetime.now(timezone.utc),
            )
            test_db.add(action)
        test_db.commit()

        # Generate synthesis
        result = generate_career_synthesis(test_db)

        # Verify counts
        assert result["overview"]["reels_analyzed"] == 3
        assert result["overview"]["actions_available"] == 3
        assert len(result["career_interests"]) >= 2
        assert len(result["recurring_skills"]) >= 1
        assert len(result["priority_actions"]) == 3
        assert result["priority_actions"][0]["priority"] == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
