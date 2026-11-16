"""Post one sample ticket to the n8n webhook, to test alerts end to end.

Nothing is read from or written to the database. The ticket is labelled as a sample.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import find_dotenv, load_dotenv  # noqa: E402

from monitor import notify  # noqa: E402

load_dotenv(find_dotenv(usecwd=True))
url = os.getenv("N8N_WEBHOOK_URL", "").strip()
if not url:
    sys.exit("N8N_WEBHOOK_URL is not set")

sample = dict(id=0, competitor="SAMPLE Competitor", is_us=False, offer="SAMPLE Island Hopping (test ticket)",
              category="island_hopping", change_type="price_change", old_value=Decimal("3000"),
              new_value=Decimal("2600"), pct_change=Decimal("-13.33"), detected_at=None)
payload = notify.build_payload(0, "ok", [sample], [], {})
ok = notify.send(url, payload, os.getenv("N8N_WEBHOOK_SECRET", ""))
print("n8n accepted the sample ticket" if ok else "n8n did not accept the sample ticket")
sys.exit(0 if ok else 1)
