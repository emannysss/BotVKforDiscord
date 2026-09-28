import json
import time
from pathlib import Path

from config import POLL_INTERVAL, VK_GROUP_ID, DISCORD_TAG_NEW
from vk_parser import VKParser
from discord_sender import create_forum_post
from discord_presence import start_presence_thread
from thread_updater import process_replies

STATE_FILE = Path("state.json")
THREADS_FILE = Path("threads.json")

STAFF_MARKERS = (
    "Команда модерации MineBlaze",
    "Доверенное лицо",
)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_post_id": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def load_threads() -> dict:
    if THREADS_FILE.exists():
        return json.loads(THREADS_FILE.read_text())
    return {}


def save_threads(threads: dict):
    THREADS_FILE.write_text(json.dumps(threads, indent=2, ensure_ascii=False))


def is_staff_reply(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in STAFF_MARKERS)


def main():
    start_presence_thread()

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

        print("\n[i] Образец последних постов:")
        for p in all_posts[-3:]:
            extra = ""
            if p.get("reply_to"):
                extra = f" reply_to={p['reply_to']} status={p.get('status')}"
            print(f"   id={p['id']} date={p['date']!r} author={p['author'][:30]!r}{extra}")

        state = load_state()
        threads = load_threads()

        if state["last_post_id"] is None:
            last_existing = vk._numeric_post_id(all_posts[-1]["id"])
            state["last_post_id"] = last_existing - 1
            save_state(state)
            print(f"\n[i] Первый запуск — старт с post_id={state['last_post_id']}")

        print(f"\n[i] Запуск цикла. Проверка каждые {POLL_INTERVAL} сек.")
        print(f"[i] Ждём посты с id > {state['last_post_id']}")
        print(f"[i] Отслеживаем ответы модераторов для {len(threads)} жалоб\n")

        check_num = 0
        while True:
            check_num += 1
            ts = time.strftime("%H:%M:%S")

            try:
                html = vk.fetch_topic_html()
                all_posts = vk.parse_posts(html)

                if not all_posts:
                    print(f"[{ts}] Проверка #{check_num}: страница пустая")
                    time.sleep(POLL_INTERVAL)
                    continue

                # 1. Обновляем теги по ответам модераторов
                updated = process_replies(all_posts, threads)
                if updated:
                    save_threads(threads)
                    print(f"[{ts}] Обновлено тегов: {updated}")

                # 2. Ищем новые жалобы
                new_posts = [
                    p for p in all_posts
                    if vk._numeric_post_id(p["id"]) > state["last_post_id"]
                ]
                new_posts.sort(key=lambda p: vk._numeric_post_id(p["id"]))

                if new_posts:
                    print(f"[{ts}] Проверка #{check_num}: новых — {len(new_posts)}")
                    for p in new_posts:
                        if is_staff_reply(p["text"]):
                            print(f"    [skip] id={p['id']} — ответ сотрудника")
                            continue

                        print(f"    [+] id={p['id']} date={p.get('date')!r} "
                              f"автор={p['author']!r} фото={len(p.get('photos', []))}")
                        thread_id = create_forum_post(
                            text=p["text"],
                            photo_urls=p["photos"],
                            author=p["author"],
                            topic_title=topic_title,
                            source_url=p["url"],
                            date=p.get("date"),
                            tag_ids=[DISCORD_TAG_NEW] if DISCORD_TAG_NEW else None,
                        )
                        if thread_id:
                            threads[p["id"]] = {
                                "thread_id": thread_id,
                                "status": "new",
                                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                            save_threads(threads)

                    max_id = vk._numeric_post_id(new_posts[-1]["id"])
                    state["last_post_id"] = max_id
                    save_state(state)
                    print(f"    [i] last_post_id обновлён → {max_id}")
                else:
                    print(f"[{ts}] Проверка #{check_num}: новых нет, "
                          f"ждём id > {state['last_post_id']}")

            except Exception as e:
                print(f"[{ts}] [!] Ошибка цикла: {e}")

            time.sleep(POLL_INTERVAL)

    finally:
        vk.close()
        print("[i] Браузер закрыт")


if __name__ == "__main__":
    main()