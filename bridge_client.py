"""CLI that reads the current session token on every invocation."""
import argparse
import json
import urllib.request
import urllib.error
from security import state_directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="/api/status")
    parser.add_argument("--body", help="JSON object; supplying it makes a POST")
    args = parser.parse_args()
    if not args.path.startswith("/api/") or any(c in args.path for c in "\r\n#"):
        parser.error("path must start with /api/")
    try:
        body = json.loads(args.body) if args.body is not None else None
        if body is not None and not isinstance(body, dict):
            parser.error("body must be an object")
        token = (state_directory() / "token").read_text(encoding="ascii").strip()
        request = urllib.request.Request("http://127.0.0.1:13371" + args.path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        return 1
    except (OSError, ValueError):
        print(json.dumps({"error": "Cannot read the token or connect. Start run_bridge.py first."}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
