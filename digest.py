"""
Daily Influencer Digest: X (Twitter) -> Telegram channel.
Sends only posts published "today" (in TIMEZONE) by the configured accounts.
"""
import html
import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

import requests

# ---- Config -----------------------------------------------------------------
# X usernames (without @). Remove anyone who doesn't post on X anymore.
USERNAMES = [
    "jarbon",           # Jason Arbon
    "tariq_king",       # Tariq King
    "techgirl1908",     # Angie Jones
    "joecolantonio",    # Joe Colantonio
    "AutomationPanda",  # Andy Knight
    "filip_hric",       # Filip Hric
    "michaelbolton",    # Michael Bolton
    "jamesmarcusbach",  # James Bach
]
TIMEZONE = ZoneInfo(os.getenv("DIGEST_TZ", "Asia/Yerevan"))
SEND_EMPTY_MESSAGE = True      # False = send nothing on days with no posts
EXCERPT_LEN = 700              # max characters of post text per message

X_BEARER = os.environ["X_BEARER_TOKEN"]
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]   # e.g. "@lusine_poghosyan_aiqa"

X_HEADERS = {"Authorization": f"Bearer {X_BEARER}"}


def lookup_user_ids(usernames):
    """One batch call: username -> numeric user id."""
    r = requests.get(
        "https://api.x.com/2/users/by",
        params={"usernames": ",".join(usernames)},
        headers=X_HEADERS, timeout=30,
    )
    if r.status_code != 200:
        print(f"X user lookup error: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    body = r.json()
    for err in body.get("errors", []):
        print(f"Skipping unknown user: {err.get('value')} ({err.get('detail')})",
              file=sys.stderr)
    return {u["username"]: u["id"] for u in body.get("data", [])}


def fetch_today_posts(user_id, start_iso):
    """Original posts (no replies/reposts) created since start_iso."""
    r = requests.get(
        f"https://api.x.com/2/users/{user_id}/tweets",
        params={
            "start_time": start_iso,
            "max_results": 20,
            "exclude": "replies,retweets",
            "tweet.fields": "created_at,note_tweet",
        },
        headers=X_HEADERS, timeout=30,
    )
    if r.status_code != 200:
        print(f"X API error for {user_id}: {r.status_code} {r.text}", file=sys.stderr)
        return []
    return r.json().get("data", [])


def send_telegram(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Telegram error: {r.status_code} {r.text}")


def format_post(username, post, when):
    # Long posts (>280 chars) keep their full text in note_tweet
    text = (post.get("note_tweet") or {}).get("text") or post.get("text", "")
    if len(text) > EXCERPT_LEN:
        text = text[:EXCERPT_LEN].rstrip() + "…"
    link = f"https://x.com/{username}/status/{post['id']}"
    return (
        f"<b>@{html.escape(username)}</b> · {when:%H:%M}\n\n"
        f"{html.escape(text)}\n\n"
        f'<a href="{link}">Open original post</a>'
    )


def main():
    now_local = datetime.now(TIMEZONE)
    start_local = datetime.combine(now_local.date(), time.min, TIMEZONE)
    start_iso = start_local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    ids = lookup_user_ids(USERNAMES)
    todays = []
    for username, user_id in ids.items():
        for post in fetch_today_posts(user_id, start_iso):
            when = datetime.fromisoformat(
                post["created_at"].replace("Z", "+00:00")).astimezone(TIMEZONE)
            # Strict date filter, in case the API returns anything older
            if start_local <= when <= now_local:
                todays.append((when, username, post))
    todays.sort(key=lambda x: x[0])

    for when, username, post in todays:
        send_telegram(format_post(username, post, when))

    if not todays and SEND_EMPTY_MESSAGE:
        send_telegram(f"No new posts today ({now_local:%d %b %Y}).")
    print(f"Sent {len(todays)} post(s).")


if __name__ == "__main__":
    main()
