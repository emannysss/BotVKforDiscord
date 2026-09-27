import os
from dotenv import load_dotenv

load_dotenv()

VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "0"))
VK_TOPIC_ID = int(os.getenv("VK_TOPIC_ID", "0"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_FORUM_CHANNEL_ID = os.getenv("DISCORD_FORUM_CHANNEL_ID")

VK_TOPIC_URL = f"https://m.vk.com/topic-{VK_GROUP_ID}_{VK_TOPIC_ID}"

_required = {
    "VK_GROUP_ID": VK_GROUP_ID,
    "VK_TOPIC_ID": VK_TOPIC_ID,
    "DISCORD_BOT_TOKEN": DISCORD_BOT_TOKEN,
    "DISCORD_FORUM_CHANNEL_ID": DISCORD_FORUM_CHANNEL_ID,
}
for name, value in _required.items():
    if not value:
        raise RuntimeError(f"Не задано {name} в .env")