import os
import re
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from config import VK_GROUP_ID, VK_TOPIC_ID, VK_TOPIC_URL


BASE = "https://m.vk.com"


class VKParser:
    def __init__(self, headless: bool = True, channel: str | None = None):
        proxy_url = os.getenv("VK_PROXY") or None

        # Всегда системный Chrome (Windows и Linux-сервер)
        if channel is None:
            channel = "chrome"

        self._pw = sync_playwright().start()

        launch_kwargs = {
            "headless": headless,
            "channel": channel,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-accelerated-2d-canvas",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        }

        if proxy_url:
            parsed = urlparse(proxy_url)
            proxy_cfg = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            }
            if parsed.username:
                proxy_cfg["username"] = parsed.username
            if parsed.password:
                proxy_cfg["password"] = parsed.password
            launch_kwargs["proxy"] = proxy_cfg
            print(f"[VK] Прокси: {parsed.scheme}://{parsed.hostname}:{parsed.port} "
                  f"(auth={'yes' if parsed.username else 'no'})")

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

        # Блокируем картинки/видео/шрифты — экономим память и трафик.
        # HTML и JS грузятся, парсер работает.
        def _block_heavy(route):
            if route.request.resource_type in ("image", "media", "font"):
                route.abort()
            else:
                route.continue_()

        self.context.route("**/*", _block_heavy)

        self.page = self.context.new_page()

    def close(self):
        for fn in (self.page.close, self.context.close,
                   self.browser.close, self._pw.stop):
            try:
                fn()
            except Exception:
                pass

    def get_last_page_url(self, html: str) -> str:
        """Находит URL последней страницы темы по пагинации."""
        soup = BeautifulSoup(html, "lxml")
        pagination = soup.select_one(".pagination")
        if pagination:
            for a in pagination.select("a.pg_link"):
                if a.get_text(strip=True) == "»":
                    href = a.get("href", "")
                    if href:
                        return BASE + href if href.startswith("/") else href

            offsets = []
            for a in pagination.select("a.pg_link"):
                href = a.get("href", "")
                m = re.search(r"offset=(\d+)", href)
                if m:
                    offsets.append((int(m.group(1)), href))
            if offsets:
                _, href = max(offsets, key=lambda x: x[0])
                return BASE + href if href.startswith("/") else href

        return VK_TOPIC_URL

    def fetch_topic_html(self) -> str:
        # 1. Первая страница — чтобы найти offset последней
        self.page.goto(VK_TOPIC_URL, wait_until="domcontentloaded", timeout=90000)
        try:
            self.page.wait_for_selector(
                ".post_item, [id^='topic_comment-'], .pagination",
                timeout=30000,
            )
        except PWTimeout:
            pass

        first_html = self.page.content()
        last_url = self.get_last_page_url(first_html)

        # 2. Грузим последнюю страницу
        if last_url and last_url != VK_TOPIC_URL:
            print(f"[VK] Загружаю последнюю страницу: {last_url}")
            self.page.goto(last_url, wait_until="domcontentloaded", timeout=90000)
            try:
                self.page.wait_for_selector(
                    ".post_item, [id^='topic_comment-']",
                    timeout=30000,
                )
            except PWTimeout:
                pass
            time.sleep(1.5)

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

        for div in soup.select("[id^='topic_comment-']"):
            raw_id = div.get("id", "")
            m = re.match(r"topic_comment-(\d+)_(\d+)$", raw_id)
            if not m:
                continue
            post_id = m.group(2)

            author_el = div.select_one(".pi_author")
            author = author_el.get_text(" ", strip=True) if author_el else "unknown"

            date_el = div.select_one(".item_date")
            date_str = date_el.get_text(" ", strip=True) if date_el else ""

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
                    url = url.split("|")[0].split("%7C")[0]
                    url = re.sub(r"[?&]cs=[^&]*", "", url)
                    if url not in photos:
                        photos.append(url)

            for doc in div.select("a.medias_link[href*='/doc']"):
                href = doc.get("href", "")
                if href.startswith("/"):
                    photos.append(BASE + href)

            posts.append({
                "id": post_id,
                "raw_id": raw_id,
                "author": author,
                "text": text,
                "date": date_str,
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