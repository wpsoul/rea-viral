#!/usr/bin/env python3
"""Is GreenLight Dash running on this computer? (For the Advanced remake. It never blocks the run.)

    python3 check_app.py [--base URL] [--timeout 1.5]

Asks the app's board API once: --base when given, else $GREENLIGHT_API_BASE_URL (the app sets it in its own
terminals), else http://127.0.0.1:18000. GET <base>/api/moodboards answering a JSON list = running.
Prints one JSON object {"running": true|false, "base": ..., "why": ...}. Exit 0 = running, 1 = not.
It reads nothing else and changes nothing. It never starts the app.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    base = os.environ.get("GREENLIGHT_API_BASE_URL") or (argv[argv.index("--base") + 1] if "--base" in argv else None) \
        or "http://127.0.0.1:18000"
    if "--base" in argv:
        base = argv[argv.index("--base") + 1]
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 1.5
    url = base.rstrip("/") + "/api/moodboards"
    res = {"running": False, "base": base}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=timeout) as r:
            body = r.read(200000)
        data = json.loads(body.decode("utf-8", "replace"))
        if isinstance(data, list):
            res.update({"running": True, "why": "the board API answered"})
        else:
            res["why"] = "something answered on %s, but not the GreenLight Dash board API" % base
    except urllib.error.HTTPError as e:
        res["why"] = "an app answered with HTTP %d; not taken as GreenLight Dash" % e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        res["why"] = "no answer (%s)" % (getattr(e, "reason", None) or e)
    print(json.dumps(res))
    return 0 if res["running"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
