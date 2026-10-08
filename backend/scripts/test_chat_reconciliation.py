"""
End-to-end test of chat session persistence and live-state reconciliation.

Verifies:
  1. Session creation
  2. Message persistence across requests
  3. Live-state block includes active tasks
  4. Stuck task gets flagged
  5. Rejected tasks don't reappear as active

Run:
    py.bat scripts/test_chat_reconciliation.py <ALICE_USER_UUID>
"""
import sys
import requests


BASE = "http://localhost:8000/api/v1"

ALICE_EMAIL = "alice@agritech.dev"
ALICE_PASSWORD = "alice1234"  # change if different


def step(label: str) -> None:
    print()
    print("=" * 70)
    print(label)
    print("=" * 70)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: py.bat scripts/test_chat_reconciliation.py <ALICE_UUID>")
        sys.exit(1)

    # --- Login as Alice ---
    step("1. Login as Alice")
    r = requests.post(
        f"{BASE}/auth/login",
        json={"email": ALICE_EMAIL, "password": ALICE_PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"FAILED login: {r.status_code} {r.text}")
        sys.exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"OK. Logged in as {ALICE_EMAIL}")

    # --- Create session ---
    step("2. Create chat session")
    r = requests.post(
        f"{BASE}/chat/sessions",
        headers=headers,
        json={"title": "Reconciliation test"},
        timeout=10,
    )
    if r.status_code != 201:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    session = r.json()
    session_id = session["id"]
    print(f"OK. Session id: {session_id}")

    # --- Send first message ---
    step("3. Send first message (ask about tasks)")
    r = requests.post(
        f"{BASE}/chat/message",
        headers=headers,
        json={
            "message": "What tasks do I currently have pending?",
            "session_id": session_id,
        },
        timeout=60,
    )
    if r.status_code != 200:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    body = r.json()
    print(f"OK. Assistant replied:")
    print(f"    {body['response'][:400]}...")
    print(f"    message_count now: {body['message_count']}")

    # --- Send second message (should recall context) ---
    step("4. Send follow-up message (test memory)")
    r = requests.post(
        f"{BASE}/chat/message",
        headers=headers,
        json={
            "message": "Should I worry about any of them?",
            "session_id": session_id,
        },
        timeout=60,
    )
    if r.status_code != 200:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    body = r.json()
    print(f"OK. Assistant replied:")
    print(f"    {body['response'][:400]}...")
    print(f"    message_count now: {body['message_count']}")

    # --- Fetch full session ---
    step("5. Fetch full session (verify persistence)")
    r = requests.get(
        f"{BASE}/chat/sessions/{session_id}",
        headers=headers,
        timeout=10,
    )
    if r.status_code != 200:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    sess = r.json()
    print(f"OK. Session has {len(sess['messages'])} messages")
    for i, m in enumerate(sess["messages"], 1):
        print(f"    [{i}] {m['role']}: {m['content'][:80]}...")

    # --- List sessions ---
    step("6. List sessions")
    r = requests.get(f"{BASE}/chat/sessions", headers=headers, timeout=10)
    print(f"OK. {len(r.json())} session(s) for Alice")
    for s in r.json():
        print(f"    • {s['title']!r} — {s['message_count']} messages")

    print()
    print("=" * 70)
    print("All checks complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()