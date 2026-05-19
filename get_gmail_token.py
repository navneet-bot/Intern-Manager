"""
Run this script ONCE locally to get your Gmail OAuth refresh token.
Then add the 3 values as Railway environment variables.

Steps:
  1. Go to https://console.cloud.google.com
  2. New Project → Enable "Gmail API"
  3. OAuth consent screen → External → Add your email as test user
  4. Credentials → Create OAuth 2.0 Client ID → Desktop app → Download JSON
  5. Paste CLIENT_ID and CLIENT_SECRET below
  6. Run:  python get_gmail_token.py
  7. A browser opens → sign in → copy the code shown → paste here
  8. Copy the REFRESH_TOKEN printed at the end
  9. Add to Railway:
       GMAIL_CLIENT_ID     = <your client id>
       GMAIL_CLIENT_SECRET = <your client secret>
       GMAIL_REFRESH_TOKEN = <refresh token from step 8>
"""

import urllib.request, urllib.parse, json, webbrowser

CLIENT_ID     = ""   # paste your Client ID here
CLIENT_SECRET = ""   # paste your Client Secret here
SCOPE         = "https://www.googleapis.com/auth/gmail.send"
REDIRECT      = "urn:ietf:wg:oauth:2.0:oob"

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌  Fill in CLIENT_ID and CLIENT_SECRET in this file first.")
    exit(1)

auth_url = (
    "https://accounts.google.com/o/oauth2/auth"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT}"
    "&response_type=code"
    f"&scope={urllib.parse.quote(SCOPE)}"
    "&access_type=offline"
    "&prompt=consent"
)
print("Opening browser for Google sign-in...")
webbrowser.open(auth_url)
code = input("\nPaste the auth code shown in the browser: ").strip()

data = urllib.parse.urlencode({
    "code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT, "grant_type": "authorization_code"
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token", data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST"
)
with urllib.request.urlopen(req) as r:
    tokens = json.loads(r.read())

print("\n✅  SUCCESS — add these to Railway environment variables:\n")
print(f"  GMAIL_CLIENT_ID     = {CLIENT_ID}")
print(f"  GMAIL_CLIENT_SECRET = {CLIENT_SECRET}")
print(f"  GMAIL_REFRESH_TOKEN = {tokens['refresh_token']}")
