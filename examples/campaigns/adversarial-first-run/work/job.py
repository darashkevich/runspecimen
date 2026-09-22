import json
import time
from pathlib import Path

time.sleep(2)
path = Path("outputs/result.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"status": "ok"}) + "\n", encoding="utf-8")
print("done")
