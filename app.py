"""
Веб-панель чата с клиентами Telegram
Отображает переписку с клиентами в реальном времени
"""
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import httpx
import asyncio

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Настройки
BOT_TOKEN = os.getenv("BOT_TOKEN", "8579638826:AAHg2YB8IQmc08VOQdS8TS6EVsYRS28ZQgE")
DB_PATH = os.path.join(os.path.dirname(__file__), "chat.db")

# YClients API для получения информации о клиентах
YCLIENTS_PARTNER_TOKEN = os.getenv("YCLIENTS_PARTNER_TOKEN", "befz68u9gpj6n3ut5zrs")
YCLIENTS_USER_TOKEN = os.getenv("YCLIENTS_USER_TOKEN", "3f51da75bd76560950ed70e1a3fbae27")
YCLIENTS_COMPANY_ID = os.getenv("YCLIENTS_COMPANY_ID", "1540716")


def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица чатов (клиентов)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            phone TEXT,
            name TEXT,
            username TEXT,
            yclients_client_id INTEGER,
            last_message_at TIMESTAMP,
            unread_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица сообщений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            direction TEXT NOT NULL,  -- 'in' или 'out'
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id)
        )
    """)
    
    # Индексы
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_telegram ON chats(telegram_id)")
    
    conn.commit()
    conn.close()


def get_db():
    """Получить подключение к БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_chat(telegram_id: int, name: str = None, username: str = None, phone: str = None):
    """Получить или создать чат"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM chats WHERE telegram_id = ?", (telegram_id,))
    chat = cursor.fetchone()
    
    if not chat:
        cursor.execute("""
            INSERT INTO chats (telegram_id, name, username, phone, last_message_at)
            VALUES (?, ?, ?, ?, ?)
        """, (telegram_id, name or "Клиент", username, phone, datetime.now()))
        conn.commit()
        chat_id = cursor.lastrowid
    else:
        chat_id = chat['id']
        # Обновляем имя если есть
        if name:
            cursor.execute("UPDATE chats SET name = ? WHERE id = ?", (name, chat_id))
            conn.commit()
    
    conn.close()
    return chat_id


def save_message(telegram_id: int, direction: str, text: str, name: str = None, username: str = None):
    """Сохранить сообщение"""
    chat_id = get_or_create_chat(telegram_id, name, username)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO messages (chat_id, telegram_id, direction, text)
        VALUES (?, ?, ?, ?)
    """, (chat_id, telegram_id, direction, text))
    
    # Обновляем время последнего сообщения и счетчик непрочитанных
    if direction == 'in':
        cursor.execute("""
            UPDATE chats SET last_message_at = ?, unread_count = unread_count + 1
            WHERE id = ?
        """, (datetime.now(), chat_id))
    else:
        cursor.execute("UPDATE chats SET last_message_at = ? WHERE id = ?", (datetime.now(), chat_id))
    
    conn.commit()
    message_id = cursor.lastrowid
    conn.close()
    
    return message_id, chat_id


@app.route('/')
def index():
    """Главная страница с чатами"""
    return render_template('index.html')


@app.route('/api/chats')
def get_chats():
    """Получить список чатов"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*, 
               (SELECT text FROM messages WHERE chat_id = c.id ORDER BY created_at DESC LIMIT 1) as last_message
        FROM chats c
        ORDER BY last_message_at DESC
    """)
    
    chats = []
    for row in cursor.fetchall():
        chats.append({
            'id': row['id'],
            'telegram_id': row['telegram_id'],
            'name': row['name'] or 'Клиент',
            'username': row['username'],
            'phone': row['phone'],
            'last_message': row['last_message'],
            'last_message_at': row['last_message_at'],
            'unread_count': row['unread_count']
        })
    
    conn.close()
    return jsonify(chats)


@app.route('/api/chats/<int:chat_id>/messages')
def get_messages(chat_id):
    """Получить сообщения чата"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Сбрасываем счетчик непрочитанных
    cursor.execute("UPDATE chats SET unread_count = 0 WHERE id = ?", (chat_id,))
    conn.commit()
    
    cursor.execute("""
        SELECT * FROM messages WHERE chat_id = ?
        ORDER BY created_at ASC
    """, (chat_id,))
    
    messages = []
    for row in cursor.fetchall():
        messages.append({
            'id': row['id'],
            'direction': row['direction'],
            'text': row['text'],
            'created_at': row['created_at']
        })
    
    conn.close()
    return jsonify(messages)


@app.route('/api/chats/<int:chat_id>/send', methods=['POST'])
def send_message(chat_id):
    """Отправить сообщение клиенту"""
    data = request.json
    text = data.get('text', '')
    
    if not text:
        return jsonify({'error': 'Текст сообщения обязателен'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT telegram_id FROM chats WHERE id = ?", (chat_id,))
    chat = cursor.fetchone()
    conn.close()
    
    if not chat:
        return jsonify({'error': 'Чат не найден'}), 404
    
    telegram_id = chat['telegram_id']
    
    # Отправляем через Telegram Bot API
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": telegram_id,
                "text": text
            }
        )
        
        if response.status_code == 200:
            # Сохраняем в БД
            message_id, _ = save_message(telegram_id, 'out', text)
            
            # Оповещаем всех через WebSocket
            socketio.emit('new_message', {
                'chat_id': chat_id,
                'message': {
                    'id': message_id,
                    'direction': 'out',
                    'text': text,
                    'created_at': datetime.now().isoformat()
                }
            })
            
            return jsonify({'success': True, 'message_id': message_id})
        else:
            return jsonify({'error': 'Ошибка отправки в Telegram'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Webhook для получения сообщений от Telegram"""
    data = request.json
    
    if 'message' in data:
        message = data['message']
        telegram_id = message['from']['id']
        text = message.get('text', '')
        name = message['from'].get('first_name', '') + ' ' + message['from'].get('last_name', '')
        name = name.strip() or 'Клиент'
        username = message['from'].get('username')
        
        # Сохраняем сообщение
        message_id, chat_id = save_message(telegram_id, 'in', text, name, username)
        
        # Оповещаем всех через WebSocket
        socketio.emit('new_message', {
            'chat_id': chat_id,
            'telegram_id': telegram_id,
            'name': name,
            'message': {
                'id': message_id,
                'direction': 'in',
                'text': text,
                'created_at': datetime.now().isoformat()
            }
        })
    
    return jsonify({'ok': True})


@app.route('/api/messages/sync', methods=['POST'])
def sync_message():
    """Синхронизация сообщений от бота"""
    data = request.json
    
    telegram_id = data.get('telegram_id')
    direction = data.get('direction', 'in')
    text = data.get('text', '')
    name = data.get('name')
    username = data.get('username')
    phone = data.get('phone')
    
    if not telegram_id or not text:
        return jsonify({'error': 'telegram_id и text обязательны'}), 400
    
    # Обновляем телефон если есть
    if phone:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE chats SET phone = ? WHERE telegram_id = ?", (phone, telegram_id))
        conn.commit()
        conn.close()
    
    # Сохраняем сообщение
    message_id, chat_id = save_message(telegram_id, direction, text, name, username)
    
    # Оповещаем всех через WebSocket
    socketio.emit('new_message', {
        'chat_id': chat_id,
        'telegram_id': telegram_id,
        'name': name,
        'message': {
            'id': message_id,
            'direction': direction,
            'text': text,
            'created_at': datetime.now().isoformat()
        }
    })
    
    return jsonify({'ok': True, 'message_id': message_id})


@socketio.on('connect')
def handle_connect():
    """Клиент подключился"""
    print('Клиент подключился к чату')


@socketio.on('disconnect')
def handle_disconnect():
    """Клиент отключился"""
    print('Клиент отключился от чата')


if __name__ == '__main__':
    init_db()
    print("🚀 Запуск панели чата на http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

