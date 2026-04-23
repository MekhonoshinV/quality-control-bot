import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
# ВСТАВЬТЕ ВАШ ТОКЕН СЮДА!!!
BOT_TOKEN = "8793965382:AAEHyLSocH9wzGMt7o9p5WCQ-Lr7BTit5A4"  # <--- ЗАМЕНИТЕ НА ВАШ ТОКЕН
DB_NAME = "quality.db"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            product_name TEXT,
            inspector_name TEXT,
            result TEXT,
            defect_category TEXT,
            defect_description TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("База данных инициализирована")

def save_inspection(batch_id, product_name, inspector_name, result, defect_category="Нет", defect_description="Нет"):
    """Сохранение результата проверки в БД"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inspections (batch_id, product_name, inspector_name, result, defect_category, defect_description, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (batch_id, product_name, inspector_name, result, defect_category, defect_description, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logging.info(f"Сохранена проверка: партия {batch_id}, результат {result}")

# ========== КОМАНДЫ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - главное меню"""
    keyboard = [
        [InlineKeyboardButton("📦 Новая проверка", callback_data='new_inspection')],
        [InlineKeyboardButton("📊 Статистика качества", callback_data='stats')],
        [InlineKeyboardButton("📋 Мои проверки", callback_data='my_inspections')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏭 *Система контроля качества*\n\n"
        "Добро пожаловать! Я помогаю сотрудникам ОТК фиксировать результаты проверки качества товаров.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик всех callback-запросов (нажатий на кнопки)"""
    query = update.callback_query
    await query.answer()  # Обязательно отвечаем на callback
    
    data = query.data
    logging.info(f"Получен callback: {data}")
    
    # ===== НОВАЯ ПРОВЕРКА =====
    if data == 'new_inspection':
        context.user_data.clear()  # Очищаем предыдущие данные
        context.user_data['step'] = 'batch_id'
        await query.edit_message_text(
            "📦 *Новая проверка качества*\n\n"
            "Введите ID партии (номер накладной или документа поставки):",
            parse_mode='Markdown'
        )
    
    # ===== СТАТИСТИКА =====
    elif data == 'stats':
        await show_stats(query, context)
    
    # ===== МОИ ПРОВЕРКИ =====
    elif data == 'my_inspections':
        await show_my_inspections(query, context)
    
    # ===== ПОМОЩЬ =====
    elif data == 'help':
        await query.edit_message_text(
            "❓ *Помощь*\n\n"
            "📦 **Новая проверка** - зафиксировать результат проверки товара\n"
            "📊 **Статистика** - посмотреть общие показатели качества\n"
            "📋 **Мои проверки** - просмотреть свои записи\n\n"
            "После ввода данных они автоматически отправляются в дашборд!\n"
            "Дашборд доступен по адресу: http://127.0.0.1:8050",
            parse_mode='Markdown'
        )
        await show_menu_after_help(query)
    
    # ===== ВОЗВРАТ В МЕНЮ =====
    elif data == 'back_to_menu':
        await show_menu(query)
    
    # ===== ОБРАБОТКА РЕЗУЛЬТАТА ПРОВЕРКИ (ГОДЕН/БРАК) =====
    elif data == 'result_pass':
        # Сохраняем как годный
        save_inspection(
            context.user_data.get('batch_id', 'неизвестно'),
            context.user_data.get('product_name', 'неизвестно'),
            query.from_user.first_name,
            'pass'
        )
        await query.edit_message_text(
            "✅ *Результат сохранен!*\n\n"
            "Товар признан годным. Данные отправлены в дашборд.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        await show_menu(query)
    
    elif data == 'result_fail':
        context.user_data['result'] = 'fail'
        context.user_data['step'] = 'defect_category'
        
        keyboard = [
            [InlineKeyboardButton("🔴 Критический", callback_data='defect_critical')],
            [InlineKeyboardButton("🟡 Значительный", callback_data='defect_major')],
            [InlineKeyboardButton("🟢 Незначительный", callback_data='defect_minor')]
        ]
        await query.edit_message_text(
            "❌ *Выберите категорию дефекта:*\n\n"
            "• **Критический** - угрожает безопасности\n"
            "• **Значительный** - влияет на функциональность\n"
            "• **Незначительный** - косметический дефект",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    # ===== ОБРАБОТКА КАТЕГОРИЙ ДЕФЕКТОВ =====
    elif data in ['defect_critical', 'defect_major', 'defect_minor']:
        defect_map = {
            'defect_critical': 'Критический',
            'defect_major': 'Значительный',
            'defect_minor': 'Незначительный'
        }
        defect_category = defect_map.get(data, 'Неизвестный')
        
        save_inspection(
            context.user_data.get('batch_id', 'неизвестно'),
            context.user_data.get('product_name', 'неизвестно'),
            query.from_user.first_name,
            'fail',
            defect_category
        )
        
        await query.edit_message_text(
            f"❌ *Результат сохранен!*\n\n"
            f"Категория дефекта: {defect_category}\n"
            f"Данные отправлены в дашборд.",
            parse_mode='Markdown'
        )
        context.user_data.clear()
        await show_menu(query)

async def show_menu(query):
    """Показать главное меню"""
    keyboard = [
        [InlineKeyboardButton("📦 Новая проверка", callback_data='new_inspection')],
        [InlineKeyboardButton("📊 Статистика качества", callback_data='stats')],
        [InlineKeyboardButton("📋 Мои проверки", callback_data='my_inspections')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    await query.edit_message_text(
        "🏭 *Система контроля качества*\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_menu_after_help(query):
    """Показать меню после помощи"""
    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]
    ]
    await query.edit_message_text(
        "🏭 *Система контроля качества*\n\n"
        "Вернуться в главное меню:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_stats(query, context):
    """Показать статистику качества"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM inspections')
    total = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM inspections WHERE result="pass"')
    passed = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM inspections WHERE result="fail"')
    failed = cursor.fetchone()[0] or 0
    
    cursor.execute('''
        SELECT defect_category, COUNT(*) FROM inspections 
        WHERE result="fail" AND defect_category != "Нет"
        GROUP BY defect_category
    ''')
    defects = cursor.fetchall()
    
    conn.close()
    
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    stats_text = f"📊 *Статистика качества*\n\n"
    stats_text += f"📦 Всего проверок: {total}\n"
    stats_text += f"✅ Годных: {passed} ({pass_rate:.1f}%)\n"
    stats_text += f"❌ Брак: {failed}\n\n"
    
    if defects:
        stats_text += "📋 *Распределение дефектов:*\n"
        for cat, count in defects:
            stats_text += f"• {cat}: {count} шт.\n"
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_my_inspections(query, context):
    """Показать последние проверки пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT batch_id, product_name, result, date FROM inspections 
        WHERE inspector_name=? 
        ORDER BY date DESC LIMIT 5
    ''', (query.from_user.first_name,))
    
    inspections = cursor.fetchall()
    conn.close()
    
    if not inspections:
        text = "📋 *Мои проверки*\n\nУ вас пока нет записей. Используйте 'Новая проверка' чтобы добавить."
    else:
        text = "📋 *Мои последние проверки:*\n\n"
        for batch_id, product, result, date in inspections:
            emoji = "✅" if result == "pass" else "❌"
            short_date = date[:10] if date else "дата неизвестна"
            text += f"{emoji} Партия {batch_id} - {product} ({short_date})\n"
    
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_menu')]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (пошаговый ввод данных)"""
    if 'step' not in context.user_data:
        await update.message.reply_text("Используйте /start для начала работы")
        return
    
    step = context.user_data['step']
    text = update.message.text.strip()
    
    if step == 'batch_id':
        context.user_data['batch_id'] = text
        context.user_data['step'] = 'product_name'
        await update.message.reply_text("Введите наименование товара:")
    
    elif step == 'product_name':
        context.user_data['product_name'] = text
        context.user_data['step'] = 'result'
        
        keyboard = [
            [InlineKeyboardButton("✅ Годен", callback_data='result_pass')],
            [InlineKeyboardButton("❌ Брак", callback_data='result_fail')]
        ]
        await update.message.reply_text(
            "Результат проверки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    else:
        await update.message.reply_text("Что-то пошло не так. Начните заново с /start")

# ========== ЗАПУСК БОТА ==========
def main():
    """Запуск Telegram-бота"""
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))  # Один обработчик на все кнопки
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logging.info("Бот контроля качества запущен...")
    print("✅ Бот успешно запущен! Перейдите в Telegram и отправьте /start")
    app.run_polling()

if __name__ == '__main__':
    main()