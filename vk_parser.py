import os
import re
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from config import VK_GROUP_ID, VK_TOPIC_ID


MOBILE_URL = f"https://m.vk.com/topic-{VK_GROUP_ID}_{VK_TOPIC_ID}"
BASE = "https://m.vk.com"


class VKParser:
    def __init__(self, headless: bool = True, channel: str | None = None):
        """
        headless=True   — браузер без окна (для сервера)
        headless=False  — с окном (для отладки локально)
        channel=None    — авто: Windows → "chrome", Linux/сервер → Chromium Playwright
        channel="chrome"|"msedge" — явно указать системный браузер
        """
        proxy_url = os.getenv("VK_PROXY")  # только для VK, Discord не трогаем

        # Автодетект канала: локально на Windows пробуем системный Chrome,
        # на сервере используем чистый Chromium Playwright
        if channel is None and os.name == "nt":
            channel = "chrome"

        self._pw = sync_playwright().start()

        launch_kwargs = {"headless": headless}
        if channel:
            launch_kwargs["channel"] = channel
        if proxy_url:
            launch_kwargs["proxy"] = {"server": proxy_url}
            # В лог выводим только хвост, без логина и пароля
            safe = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
            print(f"[VK] Прокси: {safe}")

        self.browser = self._pw.chromium.launch(**launch_kwargs)
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 10; SM-G975F) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Mobile Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 412, "height": 915},
        )
        self.page = self.context.new_page()

    def close(self):
        for fn in (self.page.close, self.context.close,
                   self.browser.close, self._pw.stop):
            try:
                fn()
            except Exception:
                pass

    def fetch_topic_html(self) -> str:
        self.page.goto(MOBILE_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            self.page.wait_for_selector(
                ".post_item, [id^='topic_comment-']",
                timeout=30000,
            )
        except PWTimeout:
            pass
        time.sleep(2.0)
        return self.page.content()

    def get_topic_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        h = soup.select_one(".topic_header h2, .hp_header, h1, title")
        if h:
            text = h.get_text(" ", strip=True)
            text = re.sub(r"\s*[|·]\s*ВКонтакте.*$", "", text)
            return text[:200]
        return f"topic {VK_TOPIC_ID}"

    def parse_posts(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        posts = []

        # id вида "topic_comment-149167439_197140"
        containers = soup.select("[id^='topic_comment-']")

        for div in containers:
            raw_id = div.get("id", "")
            m = re.match(r"topic_comment-(\d+)_(\d+)$", raw_id)
            if not m:
                continue
            post_id = m.group(2)

            author_el = div.select_one(".pi_author")
            author = author_el.get_text(" ", strip=True) if author_el else "unknown"

            text_el = div.select_one(".pi_text")
            if text_el:
                for br in text_el.find_all("br"):
                    br.replace_with("\n")
                text = text_el.get_text(" ", strip=False).strip()
            else:
                text = ""

            photos = []
            for img in div.select(".thumb_map_img_as_div"):
                url = img.get("data-src_big") or ""
                if not url:
                    style = img.get("style", "")
                    mm = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style)
                    if mm:
                        url = mm.group(1)
                if url and url.startswith("http"):
                    # VK дописывает мусор через | или %7C и плодит невалидные cs=
                    url = url.split("|")[0].split("%7C")[0]
                    url = re.sub(r"[?&]cs=[^&]*", "", url)
                    if url not in photos:
                        photos.append(url)

            # doc-файлы (скриншоты, залитые как документы) — ссылки на страницу файла
            for doc in div.select("a.medias_link[href*='/doc']"):
                href = doc.get("href", "")
                if href.startswith("/"):
                    photos.append(BASE + href)

            posts.append({
                "id": post_id,
                "raw_id": raw_id,
                "author": author,
                "text": text,
                "photos": photos,
                "url": (
                    f"https://vk.com/topic-{VK_GROUP_ID}_{VK_TOPIC_ID}"
                    f"?post={post_id}"
                ),
            })

        posts.sort(key=lambda p: self._numeric_post_id(p["id"]))
        return posts

    @staticmethod
    def _numeric_post_id(post_id) -> int:
        if isinstance(post_id, int):
            return post_id
        m = re.search(r"(\d+)$", str(post_id))
        return int(m.group(1)) if m else 0

    def get_new_posts(self, last_post_id: int | None) -> tuple[list[dict], int | None]:
        html = self.fetch_topic_html()
        all_posts = self.parse_posts(html)
        if not all_posts:
            return [], last_post_id

        max_id = max(self._numeric_post_id(p["id"]) for p in all_posts)

        if last_post_id is None:
            return [], max_id

        new = [
            p for p in all_posts
            if self._numeric_post_id(p["id"]) > last_post_id
        ]
        return new, max_id