import threading
import discord
from config import DISCORD_BOT_TOKEN


class PresenceClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.none())

    async def on_ready(self):
        print(f"[Discord] Бот онлайн: {self.user}")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="жалобы VK",
            ),
        )


def _run():
    try:
        PresenceClient().run(DISCORD_BOT_TOKEN, log_handler=None)
    except Exception as e:
        print(f"[Discord] Presence упал: {e}")


def start_presence_thread() -> threading.Thread:
    t = threading.Thread(target=_run, daemon=True, name="discord-presence")
    t.start()
    return t