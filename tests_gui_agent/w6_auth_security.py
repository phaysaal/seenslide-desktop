"""W6: magic-link auth security, verified end-to-end against production.

The web viewer authenticates by magic link (no PIN — the wrong-PIN lockout
is a DESKTOP/phone identity feature, not reachable here). These are the
browser-account security properties worth proving, and the security logic
lives at the HTTP layer, so we exercise it there with two THROWAWAY
@harness.invalid accounts and purge them afterwards.

The magic-link email is only an identifier — no mail is sent that matters;
we read the freshly-created token straight from the magic_links table
(exactly what an inbox would have delivered) and complete the login.

Checks:
  1. login issues a working session (protected endpoint 200 with Bearer)
  2. the magic-link token is SINGLE-USE (second verify rejected)
  3. the two accounts are distinct identities (different user_id)
  4. logout INVALIDATES the session (protected endpoint 401 afterwards)

Usage: run with the production DATABASE_PUBLIC_URL in $SS_DBURL.
"""
import os
import sys
import time

import psycopg2
import requests

BASE = "https://seenslide.com"
ACCOUNTS = ["w6-viewer-a@harness.invalid", "w6-viewer-b@harness.invalid"]


def db():
    return psycopg2.connect(os.environ["SS_DBURL"])


def fetch_token(email: str) -> str:
    """The newest unused magic-link token for email — what the inbox gets."""
    con = db()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT token FROM magic_links WHERE email=%s AND used=false "
            "ORDER BY created_at DESC LIMIT 1", (email.lower(),))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        con.close()


def auth_status(session_token: str) -> int:
    """Hit a login-required endpoint and return its HTTP status. The auth
    BOUNDARY is what we test: a valid session reaches business logic (any
    non-401 — here 404 'No subscription found'); an invalid/logged-out one
    is rejected at the gate with 401. (Endpoint chosen to avoid unrelated
    business-logic errors — /api/credits/balance 500s on a fresh account,
    a separate defect filed in PRODUCTION_TODO.)"""
    r = requests.get(f"{BASE}/api/billing/subscription",
                     headers={"Authorization": f"Bearer {session_token}"},
                     timeout=15)
    return r.status_code


def check(desc, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {desc}")
    return cond


def run():
    ok = True
    sessions = {}
    for email in ACCOUNTS:
        print(f"\n[{email}]")
        # 1. request magic link (creates the account + token)
        r = requests.post(f"{BASE}/api/auth/request-magic-link",
                          json={"email": email, "full_name": "W6 Harness"},
                          timeout=20)
        ok &= check(f"request-magic-link accepted ({r.status_code})",
                    r.status_code == 200)
        time.sleep(1.0)
        token = fetch_token(email)
        ok &= check("magic-link token present in DB", bool(token))
        if not token:
            continue
        # 2. verify -> session
        r = requests.post(f"{BASE}/api/auth/verify-magic-link",
                          json={"token": token}, timeout=20)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        st = data.get("session_token")
        ok &= check("verify issues a session token", bool(st))
        sessions[email] = st
        # 3. session validates
        ok &= check("session authenticates on a protected endpoint (not 401)",
                    auth_status(st) != 401)
        # 4. token is single-use
        r2 = requests.post(f"{BASE}/api/auth/verify-magic-link",
                           json={"token": token}, timeout=20)
        d2 = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
        reused = bool(d2.get("session_token")) and d2.get("success", True)
        ok &= check("magic-link token rejected on reuse (single-use)",
                    not reused)

    # 5. distinct identities
    if len(sessions) == 2:
        con = db()
        try:
            cur = con.cursor()
            cur.execute("SELECT user_id, email FROM viewer_users "
                        "WHERE email = ANY(%s)", (ACCOUNTS,))
            ids = {e: u for u, e in cur.fetchall()}
        finally:
            con.close()
        ok &= check("the two accounts are distinct user_ids",
                    len(set(ids.values())) == 2)

        # 6. logout invalidates the session
        a = ACCOUNTS[0]
        requests.post(f"{BASE}/api/auth/logout",
                      headers={"Authorization": f"Bearer {sessions[a]}"},
                      timeout=15)
        time.sleep(1.0)
        ok &= check("logout invalidates the session (401 afterwards)",
                    auth_status(sessions[a]) == 401)

    print(f"\n{'ALL W6 CHECKS PASSED' if ok else 'W6 FAILURES ABOVE'}")
    return ok


def purge():
    """Delete the throwaway accounts + their magic-link tokens. Name-gated
    on @harness.invalid so nothing else can ever be touched."""
    con = db()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM magic_links WHERE email = ANY(%s)", (ACCOUNTS,))
        ml = cur.rowcount
        cur.execute("DELETE FROM viewer_users WHERE email = ANY(%s)", (ACCOUNTS,))
        vu = cur.rowcount
        con.commit()
        print(f"purged: {vu} account(s), {ml} magic-link row(s)")
    finally:
        con.close()


if __name__ == "__main__":
    if "--purge" in sys.argv:
        purge()
    else:
        result = run()
        if "--keep" not in sys.argv:
            purge()
        sys.exit(0 if result else 1)
