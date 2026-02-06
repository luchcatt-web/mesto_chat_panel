"""
Код для добавления в бота (bot.py)
Этот код отправляет сообщения в чат-панель
"""

# ============================================
# Добавь эту переменную в начало bot.py:
# ============================================

CHAT_PANEL_URL = "https://ваш-домен-chat-panel.twc1.net"  # Замени на реальный URL


# ============================================
# Добавь эту функцию в bot.py:
# ============================================

async def send_to_chat_panel(telegram_id: int, direction: str, text: str, 
                              name: str = None, username: str = None, phone: str = None):
    """Отправить сообщение в панель чата"""
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{CHAT_PANEL_URL}/api/messages/sync",
                json={
                    "telegram_id": telegram_id,
                    "direction": direction,  # "in" или "out"
                    "text": text,
                    "name": name,
                    "username": username,
                    "phone": phone
                },
                timeout=aiohttp.ClientTimeout(total=5)
            )
    except Exception as e:
        logger.error(f"Ошибка отправки в чат-панель: {e}")


# ============================================
# Модифицируй обработчик сообщений в bot.py:
# ============================================

# Найди место где обрабатываются входящие сообщения и добавь:
#
# await send_to_chat_panel(
#     telegram_id=message.from_user.id,
#     direction="in",
#     text=message.text,
#     name=message.from_user.full_name,
#     username=message.from_user.username
# )

# Найди место где отправляются исходящие сообщения и добавь:
#
# await send_to_chat_panel(
#     telegram_id=chat_id,
#     direction="out", 
#     text=text
# )
"""

