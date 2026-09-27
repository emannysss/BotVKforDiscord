import json
import time
from pathlib import Path

from config import POLL_INTERVAL
from vk_parser import VKParser
from discord_sender import create_forum_post

STATE_FILE = Path("state.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_post_id": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def main():
    vk = VKParser()
    try:
        html = vk.fetch_topic_html()
        topic_title = vk.get_topic_title(html)
        all_posts = vk.parse_posts(html)

        print(f"[i] Тема: {topic_title}")
        print(f"[i] Постов на странице: {len(all_posts)}")
        print(f"[i] Интервал опроса: {POLL_INTERVAL}s")

        if not all_posts:
            print("[!] Не удалось извлечь ни одного поста.")
            return

        print("\n[i] Образец постов (первые 3):")
        for p in all_posts[:3]:
            print(f"   id={p['id']} author={p['author'][:40]!r}")
            print(f"      text={p['text'][:80]!r}")
            print(f"      photos={len(p['photos'])}")

        state = load_state()

        if state["last_post_id"] is None:
            # Отправляем последний пост сразу — ставим last_post_id на 1 меньше
            last_existing = vk._numeric_post_id(all_posts[-1]["id"])
            state["last_post_id"] = last_existing - 1
            save_state(state)
            print(f"\n[i] Первый запуск — старт с post_id={state['last_post_id']}")
            print(f"    Последний пост id={last_existing} будет отправлен сейчас")

        print("\n[i] Запуск цикла. Ждём новые жалобы...\n")

        while True:
            try:
                new, max_id = vk.get_new_posts(state["last_post_id"])
                if new:
                    for p in new:
                        print(f"[+] {p['author']}: {p['text'][:60]!r}, фото: {len(p['photos'])}")
                        create_forum_post(
                            text=p["text"],
                            photo_urls=p["photos"],
                            author=p["author"],
                            topic_title=topic_title,
                            source_url=p["url"],
                        )
                    if max_id:
                        state["last_post_id"] = max_id
                        save_state(state)
            except Exception as e:
                print(f"[!] Ошибка цикла: {e}")

            time.sleep(POLL_INTERVAL)

    finally:
        vk.close()
        print("[i] Браузер закрыт")


if __name__ == "__main__":
    main()