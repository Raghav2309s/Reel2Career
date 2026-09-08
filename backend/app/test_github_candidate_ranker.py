from backend.app.github_candidate_ranker import rank_github_candidates
from backend.app.github_discovery import GitHubHint
from backend.app.resource_verifier import GitHubRepositoryCandidate


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


# ---------------------------------------------------------
# CrewAI OCR corruption
# ---------------------------------------------------------

hints = [
    GitHubHint(
        owner="crewAllnc",
        repository_fragment="crewAl-examples",
    )
]

candidates = [
    candidate("crewAIInc", "crewAI-examples"),
    candidate("iam-veeramalla", "crewAI-examples"),
    candidate("kno2gether", "crewai-examples"),
]

evidence = """
2. Multi-agent pipeline Reference:
https:/github.com/crewAllnc/crewAl-examples
Official CrewAl example collection.
"""

ranked = rank_github_candidates(
    "crewAI-examples",
    hints,
    candidates,
    evidence_text=evidence,
)

print("=" * 90)
print("CREWAI TEST")

for index, item in enumerate(ranked, start=1):
    print(
        f"{index}. "
        f"{item.score:7.2f}  "
        f"{item.candidate.owner}/"
        f"{item.candidate.repository}  "
        f"{item.signals}"
    )

assert ranked[0].candidate.owner == "crewAIInc"
assert ranked[0].candidate.repository == "crewAI-examples"


# ---------------------------------------------------------
# Proctoring OCR corruption
# ---------------------------------------------------------

proctor_candidates = [
    candidate("vardanagarwal", "Proctoring-AI"),
    candidate("someone-else", "Proctoring-AI"),
]

proctor_evidence = """
13. Real-time proctoring/attention detection
Reference: https:/github.com/vardanagarwal/Proctoring-Al
Eye tracking, mouth-open detection, head pose, and person-counting.
"""

proctor_ranked = rank_github_candidates(
    "Proctoring-AI",
    [
        GitHubHint(
            owner="vardanagarwal",
            repository_fragment="Proctoring-Al",
        )
    ],
    proctor_candidates,
    evidence_text=proctor_evidence,
)

print("\n" + "=" * 90)
print("PROCTORING TEST")

for index, item in enumerate(proctor_ranked, start=1):
    print(
        f"{index}. "
        f"{item.score:7.2f}  "
        f"{item.candidate.owner}/"
        f"{item.candidate.repository}  "
        f"{item.signals}"
    )

assert proctor_ranked[0].candidate.owner == "vardanagarwal"
assert proctor_ranked[0].candidate.repository == "Proctoring-AI"


# ---------------------------------------------------------
# Idempotent payment gateway — damaged repository OCR
# ---------------------------------------------------------

payment_candidates = [
    candidate("faiza788", "idempotent-payment-gateway"),
    candidate("manasvi0209", "idempotent-payment-gateway"),
    candidate("Omenn6", "idempotent-payment-gateway"),
    candidate("rahulbitsgoa", "idempotent-payment-gateway"),
    candidate("Xprofess0r", "Idempotent-Payment-Gateway"),
    candidate("zgabrieloliveira", "idempotent-payment-gateway"),
]

payment_evidence = """
6. Non-toy payments backend Reference:
https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
Solves the double-charge/race-condition problem with idempotency
keys + DB locking.
"""

payment_ranked = rank_github_candidates(
    "idempotent-payment-gateway",
    [],
    payment_candidates,
    evidence_text=payment_evidence,
)

print("\n" + "=" * 90)
print("PAYMENT GATEWAY TEST")

for index, item in enumerate(payment_ranked, start=1):
    print(
        f"{index}. "
        f"{item.score:7.2f}  "
        f"{item.candidate.owner}/"
        f"{item.candidate.repository}  "
        f"{item.signals}"
    )

assert payment_ranked[0].candidate.owner == "zgabrieloliveira"
assert payment_ranked[0].candidate.repository == "idempotent-payment-gateway"


print("\nALL CANDIDATE RANKING TESTS PASSED")