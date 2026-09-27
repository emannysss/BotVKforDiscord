from vk_parser import VKParser

vk = VKParser(headless=False)  # окно браузера будет видно
try:
    html = vk.fetch_topic_html()
    with open("debug.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML сохранён в debug.html")
    print("Длина HTML:", len(html))

    # Показать все id, начинающиеся с post- или reply-, или содержащие цифры
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    all_ids = [tag.get("id") for tag in soup.find_all(id=True)]
    print("\nВсего элементов с id:", len(all_ids))
    print("\nПервые 40 id:")
    for i in all_ids[:40]:
        print("  ", i)
finally:
    vk.close()