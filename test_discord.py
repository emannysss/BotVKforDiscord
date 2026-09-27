from discord_sender import create_forum_post

result = create_forum_post(
    text="Тестовое сообщение из диагностики.",
    photo_urls=[],
    author="Диагностика",
    topic_title="Проверка",
    source_url="https://vk.com/topic-149167439_67913094",
)
print("Result:", result)