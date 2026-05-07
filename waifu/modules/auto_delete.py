"""
modules/auto_delete.py — Centralized Auto Delete Module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rules:
  • waifu_drop  → claim ya expire hone pe drop message delete
  • nguess      → claim ya expire 2 min baad delete
  • hclaim      → 5 min baad delete
  • quiz        → 1 min baad delete
"""

import asyncio
from waifu import application, LOGGER


async def delete_after(bot, chat_id: int, message_id: int, delay: int) -> None:
    """Delay seconds baad message delete karo."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        LOGGER.debug("Auto-deleted msg %s in chat %s", message_id, chat_id)
    except Exception:
        pass  # Already deleted or no permission — ignore


def schedule_delete(bot, chat_id: int, message_id: int, delay: int) -> None:
    """Non-blocking delete schedule karo."""
    asyncio.create_task(delete_after(bot, chat_id, message_id, delay))


# ── Delay constants (seconds) ──────────────────────────────────────────────
WAIFU_DROP_DELAY  = 0      # Immediately on claim/expire
NGUESS_DELAY      = 120    # 2 minutes
HCLAIM_DELAY      = 300    # 5 minutes
QUIZ_DELAY        = 60     # 1 minute
