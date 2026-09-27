import json
import time
from pathlib import Path

from config import POLL_INTERVAL
from vk_parser import VKParser
from discord_sender import create_forum_post
from discord_presence import start_presence_thread

STATE_FILE = Path("state.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_post_id": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def main():
    # 1. Запускаем Discord Gateway в фоне — бот станет онлайн
    start_presence_thread()

    # 2. Запускаем Playwright для VK
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

        # Показываем образец — видно, что это последняя страница
        print("\n[i] Образец последних постов:")
        for p in all_posts[-3:]:
            print(f"   id={p['id']} date={p['date']!r} author={p['author'][:40]!r}")
            print(f"      текст: {p['text'][:80]!r}")
            print(f"      фото: {len(p['photos'])}")

        state = load_state()

        # 3. При первом запуске ставим last_post_id на 1 меньше максимума
        #    — отправим ТОЛЬКО последнюю жалобу, дальше ждём новые
        if state["last_post_id"] is None:
            last_existing = vk._numeric_post_id(all_posts[-1]["id"])
            state["last_post_id"] = last_existing - 1
            save_state(state)
            print(f"\n[i] Первый запуск — старт с post_id={state['last_post_id']}")
            print(f"    Последний пост id={last_existing} будет отправлен сейчас")

        print(f"\n[i] Запуск цикла. Проверка каждые {POLL_INTERVAL} сек.")
        print(f"[i] Ждём посты с id > {state['last_post_id']}\n")

        # 4. Основной цикл с heartbeat-логами
        check_num = 0
        while True:
            check_num += 1
            timestamp = time.strftime("%H:%M:%S")

            try:
                new, max_id = vk.get_new_posts(state["last_post_id"])

                if new:
                    print(f"[{timestamp}] Проверка #{check_num}: найдено новых — {len(new)}")
                    for p in new:
                        print(f"    [+] id={p['id']} date={p['date']!r} "
                              f"автор={p['author']!r} фото={len(p['photos'])}")
                        print(f"        текст: {p['text'][:80]!r}")
                        create_forum_post(
                            text=p["text"],
                            photo_urls=p["photos"],
                            author=p["author"],
                            topic_title=topic_title,
                            source_url=p["url"],
                            date=p.get("date"),
                        )
                    if max_id:
                        state["last_post_id"] = max_id
                        save_state(state)
                        print(f"    [i] last_post_id обновлён → {max_id}")
                else:
                    print(
                        f"[{timestamp}] Проверка #{check_num}: новых нет, "
                        f"ждём id > {state['last_post_id']}"
                    )

            except Exception as e:
                print(f"[{timestamp}] [!] Ошибка цикла: {e}")

            time.sleep(POLL_INTERVAL)

    finally:
        vk.close()
        print("[i] Браузер закрыт")


if __name__ == "__main__":
    main()