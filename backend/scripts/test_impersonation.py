"""
End-to-end test of the impersonation flow.

Steps:
  1. Platform admin logs in
  2. Admin starts a support session for a target tenant user
  3. Impersonation token is used to hit a tenant route → 200
  4. Same token hits a platform route → 403 (correct)
  5. Admin ends the session
  6. Same token retries tenant route → 403 (session ended)
"""
import sys
import requests


BASE = "http://localhost:8000/api/v1"

# ---------------------------------------------------------------------------
# EDIT THESE THREE VALUES BEFORE RUNNING
# ---------------------------------------------------------------------------
ADMIN_EMAIL = "969cey@gmail.com"
ADMIN_PASSWORD = "ChangeMe!2026-agritech"

TARGET_USER_EMAIL = "alice@agritech.dev"

# Create a throwaway tenant user or use an existing one.
# The user just needs to be active and belong to a tenant.
# ---------------------------------------------------------------------------


def step(label: str) -> None:
    print()
    print("=" * 70)
    print(label)
    print("=" * 70)


def main() -> None:
    # --- 1. Admin login ---
    step("1. Admin login")
    r = requests.post(
        f"{BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    admin_token = r.json()["access_token"]
    print(f"OK. Token: {admin_token[:30]}...")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # --- 2. Find target user id ---
    step("2. Find target user (search tenants → users)")
    r = requests.get(f"{BASE}/platform/tenants", headers=admin_headers, timeout=10)
    if r.status_code != 200:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    tenants = r.json()
    print(f"Tenants: {[t['slug'] for t in tenants]}")

    # We'll ask the DB via API for the target user - easiest path:
    # use the /platform/tenants/{id} enriched endpoint, or fall back to
    # a small pre-check. For the test we'll accept the target user id as
    # an argument on the command line if provided.
    target_user_id = None
    if len(sys.argv) > 1:
        target_user_id = sys.argv[1]
        print(f"Target user id (from CLI): {target_user_id}")
    else:
        # Look up by hitting each tenant's user list is not exposed here;
        # simplest is to require it as a CLI arg. Print instructions.
        print()
        print("Target user id not provided.")
        print("Run:  py.bat scripts/test_impersonation.py <TARGET_USER_UUID>")
        print("Or fetch it with:")
        print('  docker exec -it agritech-postgres psql -U agritech -d agritech \\')
        print(f"    -c \"SELECT id, email FROM users WHERE email='{TARGET_USER_EMAIL}';\"")
        sys.exit(1)

    # --- 3. Start support session ---
    step("3. Start support session")
    r = requests.post(
        f"{BASE}/platform/support-sessions",
        headers=admin_headers,
        json={
            "target_user_id": target_user_id,
            "reason": "Automated test run",
        },
        timeout=10,
    )
    if r.status_code != 201:
        print(f"FAILED: {r.status_code} {r.text}")
        sys.exit(1)
    data = r.json()
    session_id = data["session"]["id"]
    impersonation_token = data["access_token"]
    print(f"OK. Session: {session_id}")
    print(f"     Impersonating: {data['impersonated_user']['email']}")
    print(f"     Imp token:     {impersonation_token[:30]}...")

    imp_headers = {"Authorization": f"Bearer {impersonation_token}"}

    # --- 4. Tenant route as impersonated user ---
    step("4. GET /plots with impersonation token (expect 200)")
    r = requests.get(f"{BASE}/plots", headers=imp_headers, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"OK. Returned {len(r.json())} plots.")
    else:
        print(f"UNEXPECTED: {r.text}")

    # --- 5. Platform route with impersonation token ---
    step("5. GET /platform/stats with impersonation token (expect 403)")
    r = requests.get(f"{BASE}/platform/stats", headers=imp_headers, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Body:   {r.text[:200]}")
    if r.status_code == 403:
        print("OK — impersonation does not grant platform access.")
    else:
        print("UNEXPECTED — this should be 403.")

    # --- 6. End the session ---
    step("6. End support session")
    r = requests.post(
        f"{BASE}/platform/support-sessions/{session_id}/end",
        headers=admin_headers,
        timeout=10,
    )
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"OK. ended_at = {r.json()['ended_at']}")
    else:
        print(f"UNEXPECTED: {r.text}")

    # --- 7. Reuse the dead token ---
    step("7. Reuse impersonation token after session ended (expect 403)")
    r = requests.get(f"{BASE}/plots", headers=imp_headers, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Body:   {r.text[:200]}")
    if r.status_code == 403:
        print("OK — session termination revokes the token.")
    else:
        print("UNEXPECTED — the session should be dead.")

    print()
    print("=" * 70)
    print("All checks complete.")


if __name__ == "__main__":
    main()