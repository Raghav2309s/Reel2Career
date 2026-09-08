from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base, Resource
from backend.app.ai_extracted import get_or_create_resource


engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
db = Session()


class FakeReel:
    id = 7


class FakeItem:
    def get(self, key, default=None):
        return default


reel = FakeReel()
item = FakeItem()

canonical = Resource(
    title="fastapi/full-stack-fastapi-template",
    url="https://github.com/fastapi/full-stack-fastapi-template",
    identity_key="github:fastapi/full-stack-fastapi-template",
    resource_type="repository",
    description="",
    verification_status="unverified",
)

db.add(canonical)
db.commit()

resource = get_or_create_resource(
    db=db,
    reel=reel,
    item=item,
    title="Full Stack FastAPI Template",
    url="https://github.com/fastapi/full-stack-fastapi-template",
    identity_key="github:fastapi/full-stack-fastapi-template",
    resource_type="repository",
    source_domain="github.com",
    description="Official FastAPI template",
)

assert resource.id == canonical.id
assert resource.identity_key == "github:fastapi/full-stack-fastapi-template"
assert resource.url == "https://github.com/fastapi/full-stack-fastapi-template"

count = db.query(Resource).count()
assert count == 1

print("RESOURCE RECONCILIATION TEST PASSED")

# Regression test: item 13 must not consume item 14.
sample_evidence = """8. Terraform + chaos experiment
Reference: https:/github.com/jorgecha chaos

9. AI-assisted observability dashboard
Reference: https:/github.com/Keerthikeswaran/AI-Powered-Observability-and-Log-Analysis-System

10. ML-based intrusion detection
Reference: https:/github.com/vicky60629/Network-Intrusion-Detection-System

11. Automated vulnerability scanner
Reference: https:/github.com/rgr-001/web-vuln-scanner

12. Gesture/vision accessibility tool
Reference: https:/github.com/MaitreeVaria/Indian-Sign-Language-Detection

13. Real-time proctoring/attention detection
Reference: https:/github.com/vardanagarwal/Proctoring-AI

14. AI-assisted Git workflow
Reference: https://github.com/di-sukharev/opencommit
"""

from backend.app.ai_extracted import extract_local_evidence_block

item_13 = extract_local_evidence_block(
    sample_evidence,
    "item:13",
)

assert item_13 is not None
assert "Proctoring-AI" in item_13
assert "opencommit" not in item_13

item_14 = extract_local_evidence_block(
    sample_evidence,
    "item:14",
)

assert item_14 is not None
assert "opencommit" in item_14

print("EVIDENCE BOUNDARY TEST PASSED")

db.close()