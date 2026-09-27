import io
import json
import requests
from config import DISCORD_BOT_TOKEN, DISCORD_FORUM_CHANNEL_ID

DISCORD_API = "https://discord.com/api/v10"


def _escape(text: str) -> str:
    for ch in ("*", "_", "`", "~", "|", ">"):
        text = text.replace(ch, "\\" + ch)
    return text


def _make_title(author: str, text: str) -> str:
    """Заголовок форум-поста — только 'Жалоба от <автор>'."""
    return f"Жалоба от {author}"[:100]


def create_forum_post(
    text: str,
    photo_urls: list[str],
    author: str,
    topic_title: str,
    source_url: str | None = None,
    date: str | None = None,
) -> str | None:
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "User-Agent": "vk2discord/1.0",
    }

    files = {}
    opened = []
    try:
        for i, url in enumerate(photo_urls[:10]):
            try:
                r = requests.get(
                    url,
                    timeout=15,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://vk.com/",
                    },
                )
                r.raise_for_status()
                buf = io.BytesIO(r.content)
                files[f"files[{i}]"] = (f"photo_{i}.jpg", buf, "image/jpeg")
                opened.append(buf)
            except Exception as e:
                print(f"[Discord] Фото не скачалось ({url}): {e}")

        lines = [f"**Тема:** {topic_title}", f"**Автор:** {author}"]
        if date:
            lines.append(f"**Дата:** {date}")
        if text:
            lines += ["", _escape(text)]
        if source_url:
            lines += ["", f"[Открыть в ВК]({source_url})"]
        content = "\n".join(lines)[:2000]

        attachments_meta = [
            {"id": i, "filename": f"photo_{i}.jpg"}
            for i in range(len(files))
        ]

        payload = {
            "name": _make_title(author, text),
            "message": {
                "content": content,
                "attachments": attachments_meta,
            },
        }

        resp = requests.post(
            f"{DISCORD_API}/channels/{DISCORD_FORUM_CHANNEL_ID}/threads",
            headers=headers,
            data={"payload_json": json.dumps(payload)},
            files=files or None,
            timeout=30,
        )

        if resp.status_code >= 400:
            print(f"[Discord] {resp.status_code}: {resp.text[:400]}")
            return None

        thread = resp.json()
        print(f"[Discord] Создан пост: {thread.get('id')}")
        return thread.get("id")
    finally:
        for buf in opened:
            buf.close()