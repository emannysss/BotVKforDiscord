import requests
from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_TAG_NEW,
    DISCORD_TAG_ACCEPTED,
    DISCORD_TAG_REJECTED,
)

DISCORD_API = "https://discord.com/api/v10"

STATUS_TO_TAG = {
    "new": DISCORD_TAG_NEW,
    "accepted": DISCORD_TAG_ACCEPTED,
    "rejected": DISCORD_TAG_REJECTED,
}


def _update_thread_tag(thread_id: str, tag_id: str) -> bool:
    if not tag_id:
        print(f"[updater] Нет tag_id для thread {thread_id}")
        return False

    r = requests.patch(
        f"{DISCORD_API}/channels/{thread_id}",
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "User-Agent": "vk2discord/1.0",
            "Content-Type": "application/json",
        },
        json={"applied_tags": [tag_id]},
        timeout=15,
    )
    if r.status_code >= 400:
        print(f"[updater] Ошибка {r.status_code} для треда {thread_id}: {r.text[:200]}")
        return False
    return True


def process_replies(vk_posts: list[dict], threads: dict) -> int:
    """
    Проходит по всем постам VK, находит ответы модераторов,
    обновляет теги в соответствующих Discord-тредах.
    Возвращает число обновлённых.
    """
    updated = 0

    for p in vk_posts:
        reply_to = p.get("reply_to")
        status = p.get("status")
        if not reply_to or not status:
            continue

        entry = threads.get(reply_to)
        if not entry:
            continue

        if entry.get("status") == status:
            continue

        thread_id = entry.get("thread_id")
        tag_id = STATUS_TO_TAG.get(status)
        if not tag_id:
            print(f"[updater] Не знаю тег для status={status}")
            continue

        print(f"[updater] Жалоба {reply_to} → {status}, thread={thread_id}")
        if _update_thread_tag(thread_id, tag_id):
            entry["status"] = status
            updated += 1

    return updated