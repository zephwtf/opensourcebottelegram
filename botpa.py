import sqlite3
import requests
import json
import logging
import os
import re
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем абсолютный путь к директории скрипта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'bot_interactions.db')
TASKS_PATH = os.path.join(BASE_DIR, 'tasks.txt')

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Получение и отображение истории взаимодействий пользователя.
    Позволяет указать необязательный параметр количества последних взаимодействий.
    """
    user_id = update.effective_user.id
    
    # Парсинг количества взаимодействий (по умолчанию 5)
    try:
        # Команда может быть /history или /history 10
        num_interactions = 5
        if context.args and context.args[0].isdigit():
            num_interactions = min(int(context.args[0]), 20)  # Ограничение до 20 взаимодействий
    except Exception:
        num_interactions = 5
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Получение последних взаимодействий пользователя
        cursor.execute('''
            SELECT user_message, bot_response, timestamp 
            FROM interactions 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, num_interactions))
        
        interactions = cursor.fetchall()
        
        if not interactions:
            await update.message.reply_text("У вас пока нет истории взаимодействий.")
            return
        
        # Форматирование истории
        history_text = "📜 Ваша история взаимодействий:\n\n"
        for i, (user_msg, bot_resp, timestamp) in enumerate(interactions, 1):
            history_text += f"<b>Взаимодействие {i}:</b>\n"
            history_text += f"📅 {timestamp}\n"
            history_text += f"👤 Вы: {user_msg}\n"
            bot_resp_preview = bot_resp[:10000] + '...' if len(bot_resp) > 500 else bot_resp
            history_text += f"🤖 Бот: {bot_resp_preview}\n\n"
        
        await update.message.reply_text(history_text, parse_mode=ParseMode.HTML)
    
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения истории: {e}")
        await update.message.reply_text("Не удалось получить историю взаимодействий.")
    
    finally:
        if 'conn' in locals():
            conn.close()

def ensure_database():
    """Принудительная инициализация базы данных."""
    try:
        # Создаем соединение (если БД не существует, она будет создана)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Создаем таблицу, если она не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                user_message TEXT NOT NULL,
                bot_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем индекс для оптимизации
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_id ON interactions(user_id)
        ''')
        
        conn.commit()
        logger.info("✅ База данных успешно инициализирована")
        return True
    
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка инициализации базы данных: {e}")
        return False
    
    finally:
        if 'conn' in locals():
            conn.close()

def log_interaction(user_id, username, user_message, bot_response):
    """Логирование взаимодействия с принудительной инициализацией."""
    # Принудительная инициализация перед логированием
    ensure_database()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Усечение длинных сообщений
        max_length = 1000
        user_message = user_message[:max_length]
        bot_response = bot_response[:max_length] if bot_response else None
        
        cursor.execute('''
            INSERT INTO interactions 
            (user_id, username, user_message, bot_response) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, user_message, bot_response))
        
        conn.commit()
        logger.info(f"📝 Логирование для пользователя {user_id}")
        return True
    
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка логирования: {e}")
        return False
    
    finally:
        if 'conn' in locals():
            conn.close()
def read_tasks():
    """Читает задания из файла tasks.txt"""
    try:
        if not os.path.exists(TASKS_PATH):
            logger.error(f"❌ Файл с заданиями не найден: {TASKS_PATH}")
            return ["Выполни простое задание: улыбнись!"]
        
        with open(TASKS_PATH, 'r', encoding='utf-8') as file:
            tasks = file.read().splitlines()
        
        # Фильтруем пустые строки
        tasks = [task for task in tasks if task.strip()]
        
        if not tasks:
            logger.warning("⚠️ Файл с заданиями пуст")
            return ["Выполни простое задание: улыбнись!"]
        
        return tasks
    
    except Exception as e:
        logger.error(f"❌ Ошибка чтения файла заданий: {e}")
        return ["Выполни простое задание: улыбнись!"]

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователю случайное задание."""
    tasks = read_tasks()
    random_task = random.choice(tasks)
    
    keyboard = [
        [InlineKeyboardButton("🔄 Другое задание", callback_data='new_task')],
        [InlineKeyboardButton("✅ Задание выполнено", callback_data='task_completed')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎯 *Ваше задание*:\n\n{random_task}\n\n"
        "Выполнение таких заданий поможет вам сократить виртуальное общение "
        "и развить навыки реального общения.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Answer the callback query to remove the loading indicator
    
    data = query.data
    
    if data == 'new_task':
        # Send a new random task
        tasks = read_tasks()
        random_task = random.choice(tasks)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Другое задание", callback_data='new_task')],
            [InlineKeyboardButton("✅ Задание выполнено", callback_data='task_completed')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🎯 *Ваше задание*:\n\n{random_task}\n\n"
            "Выполнение таких заданий поможет вам сократить виртуальное общение "
            "и развить навыки реального общения.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    elif data == 'task_completed':
        # Handle task completion
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        # Log completion
        log_interaction(user_id, username, "Задание выполнено", "Пользователь отметил задание как выполненное")
        
        # Send a completion message with encouragement
        await query.edit_message_text(
            "🎉 *Отлично! Задание выполнено!*\n\n"
            "Вы делаете важные шаги к сокращению виртуального общения в пользу живого!🎯"
            "Продолжайте в том же духе!\n\n"
            "Хотите получить новое задание? Используйте команду /task",
            parse_mode=ParseMode.MARKDOWN
        )

# Немедленная инициализация при импорте модуля
ensure_database()
# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ключи API
TELEGRAM_TOKEN = ""  # Токен вашего Telegram бота от BotFather
API_KEY = ""  # Ваш API ключ OpenRouter
MODEL = "deepseek/deepseek-r1"

# ID админа, куда будет отправляться обратная связь
ADMIN_ID = 1097981276  # Замените на ваш Telegram ID

# Режим форматирования:
# "parse" - обрабатывать Markdown
# "strip" - удалять символы форматирования
FORMATTING_MODE = "strip"  # Рекомендую использовать "strip" для удаления символов форматирования

# Создаем семафор для ограничения одновременных запросов к API
API_SEMAPHORE = asyncio.Semaphore(10)  # Позволяет до 10 одновременных запросов

def remove_thinking(content):
    """Удаление размышлений из контента."""
    # Удаление тегов <think>
    content = content.replace('<think>', '').replace('</think>', '')
    
    # Удаление характерных размышлений DeepSeek
    
    # Паттерн 1: Удаление текста между "Размышление:" и "Ответ:"
    if "Размышление:" in content and "Ответ:" in content:
        try:
            parts = content.split("Ответ:", 1)
            if len(parts) > 1:
                content = parts[1].strip()
        except:
            pass
    
    # Паттерн 2: Удаление английских версий
    if "Reasoning:" in content and "Answer:" in content:
        try:
            parts = content.split("Answer:", 1)
            if len(parts) > 1:
                content = parts[1].strip()
        except:
            pass
            
    # Паттерн 3: Другие варианты начала размышлений
    thinking_patterns = [
        "Let me think through this",
        "Let me think about",
        "Let me reason through",
        "I'll think through",
        "Let's think about",
        "I need to think about",
        "Here's my thought process:",
        "My reasoning:",
        "Рассуждение:",
        "Ход мыслей:",
        "Давайте подумаем",
        "Я обдумаю"
    ]
    
    for pattern in thinking_patterns:
        if pattern in content:
            try:
                # Ищем, где заканчиваются размышления (обычно начало абзаца после нескольких строк)
                lines = content.split('\n')
                # Ищем первую пустую строку после размышлений
                found_pattern = False
                result_lines = []
                for i, line in enumerate(lines):
                    if not found_pattern and pattern in line:
                        found_pattern = True
                        continue
                    if found_pattern and line.strip() == "":
                        found_pattern = False
                    if not found_pattern:
                        result_lines.append(line)
                
                if result_lines:
                    content = '\n'.join(result_lines)
                    break
            except:
                pass
    
    # Паттерн 4: Для случаев, когда ответ отмечен после плана или сгенерированных шагов
    step_markers = ["Step 1:", "Шаг 1:", "1.", "1)", "План:"]
    answer_markers = ["Ответ:", "Answer:", "Итак,", "В итоге,", "Таким образом,", "Therefore,", "In conclusion,"]
    
    for answer_marker in answer_markers:
        if answer_marker in content:
            for step_marker in step_markers:
                if step_marker in content and content.find(step_marker) < content.find(answer_marker):
                    try:
                        parts = content.split(answer_marker, 1)
                        if len(parts) > 1:
                            content = answer_marker + parts[1]
                            break
                    except:
                        pass
    
    # Удаление любых оставшихся упоминаний о размышлениях
    content = re.sub(r'^\s*(?:Размышления|Рассуждения|Thinking|Reasoning):\s*', '', content, flags=re.MULTILINE)
    
    # Удаление фраз типа "Позвольте мне проанализировать этот вопрос"
    analysis_phrases = [
        r"Позвольте мне проанализировать.*?\n",
        r"Давайте разберем.*?\n",
        r"Let me analyze.*?\n",
        r"I'll analyze.*?\n"
    ]
    
    for phrase in analysis_phrases:
        content = re.sub(phrase, '', content)
    
    return content.strip()

def process_content(content):
    """Обработка контента от DeepSeek."""
    # Сначала удаляем размышления
    content = remove_thinking(content)
    
    # Затем обрабатываем форматирование
    if FORMATTING_MODE == "strip":
        # Удаление символов форматирования Markdown
        content = re.sub(r'#+\s+', '', content)  # Удаление заголовков
        content = re.sub(r'\*\*', '', content)   # Удаление жирного текста
        content = re.sub(r'`', '', content)      # Удаление кода
        content = re.sub(r'\*', '', content)     # Удаление курсива
        content = re.sub(r'_', '', content)      # Удаление подчеркивания
        content = re.sub(r'~', '', content)      # Удаление зачеркивания
        # Удаление блоков кода
        content = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', ''), content)
    elif FORMATTING_MODE == "parse":
        # Экранирование специальных символов для Markdown V2
        content = content.replace('_', '\\_')
        content = content.replace('*', '\\*')
        content = content.replace('[', '\\[')
        content = content.replace(']', '\\]')
        content = content.replace('(', '\\(')
        content = content.replace(')', '\\)')
        content = content.replace('~', '\\~')
        content = content.replace('`', '\\`')
        content = content.replace('>', '\\>')
        content = content.replace('#', '\\#')
        content = content.replace('+', '\\+')
        content = content.replace('-', '\\-')
        content = content.replace('=', '\\=')
        content = content.replace('|', '\\|')
        content = content.replace('{', '\\{')
        content = content.replace('}', '\\}')
        content = content.replace('.', '\\.')
        content = content.replace('!', '\\!')
    
    return content

async def chat_with_deepseek(prompt):
    """Взаимодействие с API DeepSeek через OpenRouter."""
    # Используем семафор для ограничения одновременных запросов
    async with API_SEMAPHORE:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Добавляем инструкцию, чтобы модель не делала размышлений
        system_message = """Пожалуйста, отвечайте на запросы пользователя напрямую, без размышлений, анализа или пошаговых рассуждений. Старайтесь давать развернутые, подробные ответы, объясняя контекст и предоставляя полезную информацию. Избегайте слишком коротких ответов. Твоя основная цель — помогать пользователям преодолевать зависимость от социальных сетей, предоставляя поддержку, стратегии и конструктивные советы. Действуй как заботливый и мудрый наставник, который:

1. Внимательно слушает пользователя
2. Не осуждает, а поддерживает и мотивирует
3. Предлагает практические и индивидуальные стратегии

Принципы общения:
- Всегда начинай с эмпатии и понимания сложности преодоления зависимости
- Предлагай конкретные, реалистичные шаги для减少социальных сетей
- Помогай пользователю осознать триггеры и механизмы зависимого поведения
- Учи методам саморегуляции и замещения деструктивных привычек

Когда пользователь пишет "Сегодня я...", детально анализируй его действия и прогресс. Обращай внимание на:
- Успехи в уменьшении времени в социальных сетях
- Эмоциональное состояние
- Новые активности и замещающие занятия
- Трудности, которые встретились

Стратегии, которые можно порекомендовать:
- Техники осознанности
- Дневник зависимости
- Постепенное уменьшение экранного времени
- Замещающие активности
- Технические способы ограничения доступа к соцсетям
- Работа с underlying психологическими причинами

Важно: Создавай безопасное, доверительное пространство для честного диалога о зависимости."""
        
        data = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            # Используем асинхронный HTTP клиент вместо requests
            response = await asyncio.to_thread(
                requests.post,
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data
            )
            
            if response.status_code != 200:
                logger.error(f"Ошибка API: {response.status_code}")
                return "Произошла ошибка при обращении к API. Пожалуйста, попробуйте позже."
                
            response_json = response.json()
            content = response_json["choices"][0]["message"].get("content", "")
            return process_content(content)
        
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")
            return "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз позже."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    global ADMIN_ID
    # Если ADMIN_ID не установлен, и сообщение от пользователя,
    # спрашиваем, хочет ли он стать админом
    if ADMIN_ID is None:
        keyboard = [
            [InlineKeyboardButton("Да, я хочу получать фидбек", callback_data='set_admin')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Привет! Я бот, использующий новейшую для ответов на ваши вопросы.\n"
            "Просто напишите мне, и я отвечу!\n\n"
            "Хотите ли вы получать фидбек от пользователей?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Привет! Я бот, который поможет сократить виртуальное общение в пользу живого!\n"
            "Просто напишите мне, и я отвечу!\n\n"
            "Если хотите оставить отзыв о работе бота, используйте команду /feedback"
            "💡 Кстати, вы можете использовать этот чат как дневник для отслеживания своих достижений. Просто начните сообщение со слов 'Сегодня я...' и опишите свои действия и их результат."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    help_text = (
        "🤖 Использование бота:\n\n"
        "1. Просто отправьте сообщение, и я отвечу вам.\n"
        "2. Используйте /start для начала работы\n"
        "3. Используйте /help для отображения этой справки\n"
        "4. Используйте /feedback для отправки отзыва о работе бота\n\n"
        "5. Используйте /task для получения интересного задания\n\n"
        "💡 Кстати, вы можете использовать этот чат как дневник для отслеживания своих достижений. Просто начните сообщение со слов 'Сегодня я...' и опишите свои действия и их результат.\n"
    )
    
    await update.message.reply_text(help_text)

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /feedback."""
    keyboard = [
        [
            InlineKeyboardButton("👍 Хорошо", callback_data='feedback_good'),
            InlineKeyboardButton("👎 Плохо", callback_data='feedback_bad')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Оцените работу бота:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик обычных сообщений."""
    user_text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Получено сообщение от пользователя {user_id} в чате {chat_id}: {user_text}")
    
    # Отправка уведомления о принятии запроса
    notification = await update.message.reply_text("✅ Принял твои слова. Обдумываю...")
    
    # Отправка 'typing...' действия
    await update.message.chat.send_action(action="typing")
    
    # Создаем отдельную задачу для обработки сообщения
    # Это позволит боту обрабатывать другие сообщения, пока ждет ответ от API
    task = asyncio.create_task(process_user_message(update, notification, user_text))
    
    # Сохраняем задачу в контексте пользователя, чтобы она не была уничтожена сборщиком мусора
    if 'tasks' not in context.user_data:
        context.user_data['tasks'] = []
    context.user_data['tasks'].append(task)

async def process_user_message(update, notification, user_text):
    """Обрабатывает сообщение пользователя в отдельной асинхронной задаче."""
    try:
        # Получение ответа от DeepSeek
        response_text = await chat_with_deepseek(user_text)
        
        # Логирование взаимодействия
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        log_interaction(user_id, username, user_text, response_text)
        
        # Разделение длинных ответов на несколько сообщений (лимит Telegram ~4096 символов)
        max_length = 4000  # Берем с запасом
        
        # Удаление предыдущего сообщения о принятии запроса
        try:
            await notification.delete()
        except Exception as e:
            # Обработка любых исключений, чтобы бот продолжал работать
            logger.error(f"Ошибка обработки сообщения: {str(e)}")
            try:
                await update.message.reply_text("❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.")
            except:
                pass

        
        # Если ответ короткий, отправляем как есть
        if len(response_text) <= max_length:
            if FORMATTING_MODE == "parse":
                try:
                    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e:
                    # В случае ошибки парсинга Markdown, отправляем без форматирования
                    logger.warning(f"Ошибка парсинга Markdown: {e}")
                    await update.message.reply_text(response_text)
            else:
                await update.message.reply_text(response_text)
        else:
            # Разбиваем длинный ответ на части
            chunks = [response_text[i:i+max_length] for i in range(0, len(response_text), max_length)]
            for i, chunk in enumerate(chunks):
                if FORMATTING_MODE == "parse":
                    try:
                        await update.message.reply_text(f"Часть {i+1}/{len(chunks)}:\n\n{chunk}", 
                                                 parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception as e:
                        # В случае ошибки парсинга Markdown, отправляем без форматирования
                        logger.warning(f"Ошибка парсинга Markdown: {e}")
                        await update.message.reply_text(f"Часть {i+1}/{len(chunks)}:\n\n{chunk}")
                else:
                    await update.message.reply_text(f"Часть {i+1}/{len(chunks)}:\n\n{chunk}")
                
                # Небольшая задержка между отправкой частей сообщения
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.3)  # Задержка 300 мс между сообщениями
                    
    except Exception as e:
        # Обработка любых исключений, чтобы бот продолжал работать
        logger.error(f"Ошибка обработки сообщения: {str(e)}")
        try:
            await update.message.reply_text("❌ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте еще раз.")
        except:
            pass

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()  # Отвечаем на запрос, чтобы убрать индикатор загрузки
    
    # Получаем данные из кнопки
    data = query.data
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    
    if data == 'set_admin':
        global ADMIN_ID
        ADMIN_ID = user_id
        await query.edit_message_text(
            "✅ Вы настроены как админ для получения обратной связи.\n\n"
            "Теперь можете использовать бота для получения ответов от DeepSeek-R1."
        )
        return
    
    # ПРОБЛЕМНЫЙ БЛОК: Обработка обратной связи
    if data.startswith('feedback_'):
        # Определяем тип обратной связи
        if data == 'feedback_good':
            # Для положительной обратной связи просто благодарим пользователя
            keyboard = [
                [InlineKeyboardButton("📝 Добавить комментарий", callback_data='add_comment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Спасибо за положительный отзыв!", reply_markup=reply_markup)
            
            # Отправляем уведомление администратору
            if ADMIN_ID:
                feedback_text = (
                    f"📊 Новый положительный отзыв!\n\n"
                    f"👤 Пользователь: {username} (ID: {user_id})\n"
                )
                try:
                    await context.bot.send_message(ADMIN_ID, feedback_text)
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление администратору: {str(e)}")
        
        elif data == 'feedback_bad':
            # Для отрицательной обратной связи просим уточнить проблему
            keyboard = [
                [
                    InlineKeyboardButton("Неточный ответ", callback_data='reason_inaccurate'),
                    InlineKeyboardButton("Непонятно", callback_data='reason_unclear')
                ],
                [
                    InlineKeyboardButton("Слишком кратко", callback_data='reason_short'),
                    InlineKeyboardButton("Слишком длинно", callback_data='reason_long')
                ],
                [
                    InlineKeyboardButton("Другое", callback_data='reason_other')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Что именно вам не понравилось?", reply_markup=reply_markup)
        
        return
    
    if data.startswith('reason_'):
        # Обработка причины отрицательного отзыва
        reason_map = {
            'reason_inaccurate': "Неточный ответ",
            'reason_unclear': "Непонятный ответ",
            'reason_short': "Слишком краткий ответ",
            'reason_long': "Слишком длинный ответ",
            'reason_other': "Другое"
        }
        
        reason = reason_map.get(data, "Неизвестная причина")
        
        # Запрашиваем дополнительный комментарий
        keyboard = [
            [InlineKeyboardButton("📝 Добавить комментарий", callback_data='add_comment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Спасибо за ваш отзыв! Причина: {reason}", reply_markup=reply_markup)
        
        # Отправляем уведомление администратору
        if ADMIN_ID:
            feedback_text = (
                f"⚠️ Новый отрицательный отзыв!\n\n"
                f"👤 Пользователь: {username} (ID: {user_id})\n"
                f"📌 Причина: {reason}\n"
            )
            try:
                await context.bot.send_message(ADMIN_ID, feedback_text)
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление администратору: {str(e)}")
                
        return
    
    if data == 'add_comment':
        # Сохраняем в контексте пользователя, что ожидаем от него комментарий
        context.user_data['awaiting_feedback'] = True
        context.user_data['feedback_message_id'] = query.message.message_id
        
        # Удаляем кнопки и просим оставить комментарий
        await query.edit_message_text(
            "Пожалуйста, напишите ваш комментарий к ответу. Ваш отзыв важен для улучшения работы бота.",
            reply_markup=None
        )
        return

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка комментариев к отзывам"""
    # Проверяем, ожидаем ли мы комментарий от пользователя
    if not context.user_data.get('awaiting_feedback', False):
        # Если не ожидаем комментарий, передаем сообщение в стандартную обработку
        await handle_message(update, context)
        return

    comment = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or "Без имени"
    
    # Сбрасываем состояние ожидания отзыва
    context.user_data['awaiting_feedback'] = False
    feedback_message_id = context.user_data.pop('feedback_message_id', None)
    
    # Благодарим пользователя
    await update.message.reply_text("Спасибо за ваш комментарий! Он поможет улучшить работу бота.")
    
    # Отправляем уведомление администратору
    if ADMIN_ID:
        feedback_text = (
            f"💬 Новый комментарий от пользователя!\n\n"
            f"👤 Пользователь: {username} (ID: {user_id})\n"
            f"📝 Комментарий: {comment}\n"
        )
        try:
            await context.bot.send_message(ADMIN_ID, feedback_text)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление администратору: {str(e)}")

async def command_setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /setadmin для установки ID администратора."""
    global ADMIN_ID
    ADMIN_ID = update.effective_user.id
    await update.message.reply_text(f"✅ Вы установлены как администратор. Ваш ID: {ADMIN_ID}")

# Исправление admin_panel_command
async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель администратора."""
    # Проверяем, является ли пользователь администратором
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к административной панели.")
        return

    # Получаем статистику
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Статистика пользователей
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM interactions")
        total_users = cursor.fetchone()[0]
        
        # Статистика взаимодействий
        cursor.execute("SELECT COUNT(*) FROM interactions")
        total_interactions = cursor.fetchone()[0]
        
        # Статистика за последние 24 часа
        cursor.execute('''
            SELECT COUNT(*) 
            FROM interactions 
            WHERE timestamp >= datetime('now', '-1 day')
        ''')
        interactions_last_24h = cursor.fetchone()[0]
        
        # Топ-5 активных пользователей
        cursor.execute('''
            SELECT user_id, username, COUNT(*) as interaction_count 
            FROM interactions 
            GROUP BY user_id, username 
            ORDER BY interaction_count DESC 
            LIMIT 5
        ''')
        top_users = cursor.fetchall()
        
        # Создаем клавиатуру для администратора
        keyboard = [
            [
                InlineKeyboardButton("📊 Статистика", callback_data='admin_stats'),
                InlineKeyboardButton("👥 Пользователи", callback_data='admin_users')
            ],
            [
                InlineKeyboardButton("📝 Логи", callback_data='admin_logs'),
                InlineKeyboardButton("🛠 Настройки", callback_data='admin_settings')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формируем текст статистики
        stats_text = (
            "🤖 <b>Административная панель бота</b> 🤖\n\n"
            f"📈 Общая статистика:\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"💬 Всего взаимодействий: {total_interactions}\n"
            f"🕒 Взаимодействий за 24 часа: {interactions_last_24h}\n\n"
            "🏆 Топ-5 активных пользователей:\n"
        )
        
        for i, (user_id, username, count) in enumerate(top_users, 1):
            stats_text += f"{i}. {username or 'Без имени'} (ID: {user_id}): {count} взаимодействий\n"
        
        await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    except sqlite3.Error as e:
        logger.error(f"Ошибка в административной панели: {e}")
        await update.message.reply_text("❌ Не удалось получить статистику.")
    
    finally:
        if 'conn' in locals():
            conn.close()

    # Остальная логика функции (без query.answer())
    # ...
async def handle_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопок административной панели.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет доступа к административной панели.")
        return
    
    data = query.data
    
    if data == 'admin_stats':
        # Показываем подробную статистику
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Статистика по дням
            cursor.execute('''
                SELECT 
                    date(timestamp) as interaction_date, 
                    COUNT(*) as daily_interactions 
                FROM interactions 
                GROUP BY interaction_date 
                ORDER BY interaction_date DESC 
                LIMIT 7
            ''')
            daily_stats = cursor.fetchall()
            
            stats_text = "📊 Детальная статистика взаимодействий за 7 дней:\n\n"
            for date, count in daily_stats:
                stats_text += f"📅 {date}: {count} взаимодействий\n"
            
            await query.edit_message_text(stats_text)
        
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения статистики: {e}")
            await query.edit_message_text("❌ Не удалось получить детальную статистику.")
        
        finally:
            if 'conn' in locals():
                conn.close()
    
    elif data == 'admin_users':
        # Показываем список последних активных пользователей
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT user_id, username, MAX(timestamp) as last_interaction 
                FROM interactions 
                GROUP BY user_id, username 
                ORDER BY last_interaction DESC 
                LIMIT 10
            ''')
            recent_users = cursor.fetchall()
            
            users_text = "👥 Последние активные пользователи:\n\n"
            for user_id, username, last_interaction in recent_users:
                users_text += f"👤 {username or 'Без имени'} (ID: {user_id})\n"
                users_text += f"🕒 Последнее взаимодействие: {last_interaction}\n\n"
            
            await query.edit_message_text(users_text)
        
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения списка пользователей: {e}")
            await query.edit_message_text("❌ Не удалось получить список пользователей.")
        
        finally:
            if 'conn' in locals():
                conn.close()
    
    elif data == 'admin_logs':
        # Показываем последние системные логи
        log_content = ""
        try:
            with open('bot.log', 'r') as log_file:
                # Читаем последние 20 строк
                log_content = ''.join(log_file.readlines()[-20:])
        except Exception as e:
            log_content = f"Ошибка чтения логов: {str(e)}"
        
        await query.edit_message_text(f"🔍 Последние системные логи:\n\n{log_content}")
    
    elif data == 'admin_settings':
        # Показываем текущие настройки бота
        settings_text = (
            "🛠 <b>Настройки бота</b>:\n\n"
            f"🤖 Модель: {MODEL}\n"
            f"📝 Режим форматирования: {FORMATTING_MODE}\n"
            f"📊 Максимальное количество API-запросов: {API_SEMAPHORE._value}\n"
            "📡 Статус: Активен"
        )
        
        # Клавиатура для настроек
        keyboard = [
            [
                InlineKeyboardButton("🔄 Сменить модель", callback_data='change_model'),
                InlineKeyboardButton("📝 Режим форматирования", callback_data='change_formatting')
            ],
            [
                InlineKeyboardButton("🔙 Назад", callback_data='back_to_admin_panel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(settings_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    # Добавьте обработку других кнопок
    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
     await update.message.reply_text("✅ Сообщение обработано!")
     


def main():
    """Основная функция для запуска бота."""
    # Дополнительное логирование
    logging.basicConfig(
        level=logging.DEBUG,  # Более подробное логирование
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("task", task_command))
    application.add_handler(CommandHandler("setadmin", command_setadmin))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("admin", admin_panel_command))
    application.add_handler(CallbackQueryHandler(button_callback, pattern='^(new_task|task_completed)$'))

    # Обработчик для всех текстовых сообщений с подробным логированием
    async def debug_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"Получено сообщение от {update.effective_user.id}: {update.message.text}")
        
        # Проверка состояния обратной связи
        if context.user_data.get('awaiting_feedback', False):
            logger.debug("Сообщение ожидается как комментарий к обратной связи")
            await handle_feedback(update, context)
        else:
            logger.debug("Обычное сообщение, передаем в handle_message")
            await handle_message(update, context)

    # Регистрация обработчика сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, debug_message_handler))

    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(CallbackQueryHandler(handle_admin_buttons, pattern="^admin_"))

    logger.info("✅ Бот запускается...")
    
    try:
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()