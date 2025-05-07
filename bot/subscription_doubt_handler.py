#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CallbackQueryHandler, ConversationHandler, CommandHandler, MessageHandler, Filters, MessageFilter

# Добавляем корневую директорию проекта в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import User, get_session

# Настраиваем логгер для этого модуля
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Определяем функцию get_bot_config
def get_bot_config():
    """Возвращает конфигурацию бота из файла bot_config.json"""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        else:
            logger.warning(f"Файл конфигурации не найден: {config_path}")
            return {'reviews_channel_url': 'https://t.me/willway_reviews'}
    except Exception as e:
        logger.error(f"Ошибка при чтении конфигурации: {e}")
        return {'reviews_channel_url': 'https://t.me/willway_reviews'}

# Создаем класс для генерации ссылок на оплату
class PaymentHelper:
    @staticmethod
    def generate_payment_url(user_id):
        """Генерирует ссылку на страницу оплаты с ID пользователя"""
        payment_url = "https://willway.pro/payment"
        full_url = f"{payment_url}?tgid={user_id}"
        logger.info(f"[PAYMENT] Сгенерирована ссылка: {full_url}")
        return full_url

# Создаем экземпляр PaymentHelper
payment_helper = PaymentHelper()

# Состояния диалога в процессе выбора подписки
DOUBT_HANDLER, EXPENSIVE_HANDLER, RESULT_DOUBT_HANDLER = range(100, 103)

# Идентификаторы для callback_data
DOUBT_CB = "subscription_doubt"
EXPENSIVE_CB = "expensive_doubt"
RESULT_CB = "result_doubt"
BACK_TO_PLANS_CB = "back_to_plans"

def get_subscription_keyboard(user_id=None):
    if user_id:
        payment_url = payment_helper.generate_payment_url(user_id)
        logger.info(f"Сгенерирована ссылка на оплату для пользователя {user_id}: {payment_url}")
    else:
        payment_url = "https://willway.pro/payment"
        logger.warning("ID пользователя не передан, используется стандартная ссылка без параметров")
    
    keyboard = [
        [InlineKeyboardButton("30 дней | 1.555 руб", url=payment_url)],
        [InlineKeyboardButton("1 год | 13.333 руб (- 30%) + тренер", url=payment_url)],
    ]
    
    config = get_bot_config()
    reviews_url = config.get('reviews_channel_url', 'https://t.me/willway_reviews')
    
    keyboard.extend([
        [InlineKeyboardButton("Отзывы", url=reviews_url)],
        [InlineKeyboardButton("Подумаю", callback_data=f"{DOUBT_CB}")]
    ])
    
    logger.info(f"Создана клавиатура подписки: кнопка 'Подумаю' имеет callback_data={DOUBT_CB}")
    logger.info(f"Полная клавиатура: {keyboard}")
    
    return InlineKeyboardMarkup(keyboard)

def get_doubt_options_keyboard():
    """Клавиатура с вариантами сомнений"""
    keyboard = [
        [InlineKeyboardButton("Дорого", callback_data=f"{EXPENSIVE_CB}")],
        [InlineKeyboardButton("Будет ли результат?", callback_data=f"{RESULT_CB}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_yes_no_keyboard(action_type):
    """Клавиатура Да/Нет с действием"""
    keyboard = [
        [InlineKeyboardButton("Да", callback_data=f"{action_type}_yes")],
        [InlineKeyboardButton("Нет", callback_data=f"{action_type}_no")]
    ]
    return InlineKeyboardMarkup(keyboard)

def handle_subscription_doubt(update: Update, context: CallbackContext):
    """Обработчик нажатия на кнопку 'Подумаю'"""
    query = update.callback_query
    
    # Отладочное логирование
    logger.info(f"Сработал обработчик handle_subscription_doubt с callback_data={query.data}")
    
    query.answer()
    
    user_id = update.effective_user.id
    
    # Текст сообщения перед выбором причины сомнения
    doubt_text = ("Покажись, что важно учитывать уверенность в своем решении.\n"
                 "Чего тебе не хватает, чтобы дать нам шанс?")
    
    # Отправляем сообщение с вариантами сомнения
    query.edit_message_text(
        text=doubt_text, 
        reply_markup=get_doubt_options_keyboard()
    )
    logger.info(f"Отправлена клавиатура с опциями сомнений пользователю {user_id}")
    
    # Сохраняем в БД информацию о том, что пользователь выбрал "Подумаю"
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_status = "Показ вариантов"
            session.commit()
            logger.info(f"Пользователь {user_id} выбрал 'Подумаю', показываем варианты сомнений")
        else:
            logger.error(f"Пользователь {user_id} не найден в базе данных при выборе 'Подумаю'")
    
    return DOUBT_HANDLER

def handle_expensive_doubt(update: Update, context: CallbackContext):
    """Обработчик нажатия на кнопку 'Дорого'"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Текст сообщения по ветке "Дорого"
    expensive_text = ("Давай честно.\n"
                      "Это не правда. Это цена: вложиться в то, что даёт результат — в своё здоровье, в своё тело, в своё качество жизни.\n\n"
                      "1 555 ₽ — это всего 50 рублей в день.\n"
                      "Меньше, чем чашка кофе.\n\n"
                      "А возможности Они безмерны:\n"
                      "— Осанка, которая дарит уверенность\n"
                      "— Спокойный сон и высокий уровень энергии\n"
                      "— Ты освобождаешь свое время от боли, зажимов и тревог.\n\n"
                      "И знаешь, подумай о моменте: ничего не меняется - \"выбить\" себя.\n\n"
                      "Но всегда правильное решение — выбрать себя.\n\n"
                      "А мы проведём тебя по этому пути за руку вместе.")
    
    # Отправляем сообщение с вопросом "Дорого?"
    query.edit_message_text(
        text=expensive_text, 
        reply_markup=get_yes_no_keyboard(EXPENSIVE_CB)
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_status = "Дорого"
            session.commit()
            logger.info(f"Пользователь {user_id} указал причину сомнения: 'Дорого'")
    
    return EXPENSIVE_HANDLER

def handle_result_doubt(update: Update, context: CallbackContext):
    """Обработчик нажатия на кнопку 'Будет ли результат?'"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Текст сообщения по ветке "Будет ли результат?"
    result_text = ("Так понятно, что есть недоверие к обещаниям.\n\n"
                  "Как же обычно нарушают их люди?\n"
                  "В WILLWAY мы даем: настоящие результаты реальных людей, регулярно публикуем Трансформации в канале с отзывами, случаи уникальны.\n\n"
                  "Когда это читаешь и вспоминаешь: Тренеры — умелые, Стихия, соревнования, усталость, И это нормально.\n\n"
                  "Мы рядом, чтобы помочь тебе выйти и не дать сойти с пути.\n\n"
                  "Ты здесь не один.\n\n"
                  "Сотни людей выбрали заботиться о себе — канал отзывов это подтверждает.\n\n"
                  "Ссылка на канал с отзывами\n\n"
                  "Гарантия:\n"
                  "— Ты имеешь 7 дней отказа, если что-то не понравится. В течение 7 дней просто напишешь в поддержку и мы вернем деньги.")
    
    # Получаем URL канала отзывов из конфигурации
    config = get_bot_config()
    reviews_url = config.get('reviews_channel_url', 'https://t.me/willway_reviews')
    
    # Форматируем текст, добавляя URL канала отзывов
    result_text = result_text.replace("Ссылка на канал с отзывами", f"[Ссылка на канал с отзывами]({reviews_url})")
    
    # Отправляем сообщение с вопросом "Будет ли результат?"
    query.edit_message_text(
        text=result_text, 
        reply_markup=get_yes_no_keyboard(RESULT_CB),
        parse_mode='Markdown'
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_status = "Насчет результата"
            session.commit()
            logger.info(f"Пользователь {user_id} указал причину сомнения: 'Будет ли результат?'")
    
    return RESULT_DOUBT_HANDLER

def handle_expensive_yes(update: Update, context: CallbackContext):
    """Обработчик нажатия 'Да' после сомнения 'Дорого'"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Показываем варианты подписки снова
    query.edit_message_text(
        text="Варианты WILLWAY подписки:", 
        reply_markup=get_subscription_keyboard(user_id)
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Согласился, что дорого"
            session.commit()
            logger.info(f"Пользователь {user_id} согласился, что подписка дорогая, показываем варианты подписки")
    
    return ConversationHandler.END

def handle_expensive_no(update: Update, context: CallbackContext):
    """Обработчик нажатия 'Нет' после сомнения 'Дорого'"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Текст после отрицания дороговизны
    text = ("Ты сказал, что это подписка не дорогая.\n\n"
           "Мы не обещаем чудес за подписку.\n"
           "В WILLWAY мы даем: постоянное улучшение и прогресс — через регулярные напоминания когда и как нужно выполнять упражнения. И в своем темпе.\n\n"
           "Когда это читаешь и вспоминаешь: тренеры — умелые, соревнования, усталость. И это нормально.\n\n"
           "Мы рядом, чтобы помочь тебе выйти и не дать сойти с пути.\n\n"
           "Ты здесь не один.\n\n"
           "Сотни людей выбрали заботиться о себе — канал отзывов это подтверждает.\n\n"
           "Ссылка на канал с отзывами\n\n"
           "Гарантия:\n"
           "— Ты имеешь 7 дней отказа, если что-то не понравится. В течение 7 дней просто напишешь в поддержку и мы вернем деньги.")
    
    # Получаем URL канала отзывов из конфигурации
    config = get_bot_config()
    reviews_url = config.get('reviews_channel_url', 'https://t.me/willway_reviews')
    
    # Форматируем текст, добавляя URL канала отзывов
    text = text.replace("Ссылка на канал с отзывами", f"[Ссылка на канал с отзывами]({reviews_url})")
    
    # Клавиатура для финального выбора
    keyboard = [
        [InlineKeyboardButton("Да (хочет на тарифы)", callback_data=f"{BACK_TO_PLANS_CB}")],
        [InlineKeyboardButton("Нет", callback_data=f"final_no")]
    ]
    
    # Отправляем сообщение с клавиатурой выбора
    query.edit_message_text(
        text=text, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Считает, что не дорого"
            session.commit()
            logger.info(f"Пользователь {user_id} считает, что подписка не дорогая")
    
    return EXPENSIVE_HANDLER

def handle_result_yes(update: Update, context: CallbackContext):
    """Обработчик нажатия 'Да' после сомнения о результате"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Показываем варианты подписки снова
    query.edit_message_text(
        text="Варианты WILLWAY подписки:", 
        reply_markup=get_subscription_keyboard(user_id)
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Сомневается в результате, но готов попробовать"
            session.commit()
            logger.info(f"Пользователь {user_id} сомневается в результате, но готов попробовать, показываем варианты подписки")
    
    return ConversationHandler.END

def handle_result_no(update: Update, context: CallbackContext):
    """Обработчик нажатия 'Нет' после сомнения о результате"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Текст после отрицания сомнений в результате
    text = ("Давай честно.\n"
           "Это не правда. Это шанс: вложиться в то, что даёт результат — в своё тело, в своё качество жизни.\n\n"
           "1 555 ₽ — это всего 50 рублей в день.\n"
           "Меньше, чем чашка кофе.\n\n"
           "А возможности Они безмерны:\n"
           "— Гармония в теле\n"
           "— Осанка, которая дарит уверенность\n"
           "— Спокойный сон и высокий уровень энергии\n"
           "— Ты освобождаешь свое время от боли, зажимов и тревог.\n\n"
           "И знаешь, недельного варианта нигде не бывает.\n\n"
           "Но всегда правильное решение — выбрать себя.\n\n"
           "А мы проведём тебя по этому пути за руку вместе.")
    
    # Клавиатура для финального выбора
    keyboard = [
        [InlineKeyboardButton("Да (хочет на тарифы)", callback_data=f"{BACK_TO_PLANS_CB}")],
        [InlineKeyboardButton("Нет", callback_data=f"final_no")]
    ]
    
    # Отправляем сообщение с клавиатурой
    query.edit_message_text(
        text=text, 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Не верит в результат"
            session.commit()
            logger.info(f"Пользователь {user_id} не верит в результат, показываем следующий шаг")
    
    return RESULT_DOUBT_HANDLER

def handle_back_to_plans(update: Update, context: CallbackContext):
    """Обработчик возврата к выбору тарифа"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    
    # Показываем варианты подписки снова
    query.edit_message_text(
        text="Варианты WILLWAY подписки:", 
        reply_markup=get_subscription_keyboard(user_id)
    )
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Вернулся к выбору тарифов"
            session.commit()
            logger.info(f"Пользователь {user_id} вернулся к выбору тарифов")
    
    return ConversationHandler.END

def handle_final_no(update: Update, context: CallbackContext):
    """Обработчик финального отказа"""
    query = update.callback_query
    query.answer()
    
    user_id = update.effective_user.id
    logger.info(f"[FINAL_NO] Пользователь {user_id} выбрал финальный отказ")
    
    # Текст после финального отказа
    final_text = ("Жаль, что у нас не получится поработать вместе, но будем очень счастливы увидеть тебя снова. Ты всегда знаешь, где нас найти.")
    
    # Отправляем сообщение без клавиатуры
    query.edit_message_text(text=final_text)
    logger.info(f"[FINAL_NO] Отправлено сообщение с финальным текстом пользователю {user_id}")
    
    # Отправляем уведомление админам о том, что пользователь отказался
    config = get_bot_config()
    manager_username = config.get('manager_username', 'telegram')
    
    # Формируем сообщение для администратора
    admin_message = f"Пользователь {user_id} (@{update.effective_user.username if update.effective_user.username else 'без username'}) отказался от подписки после серии сомнений."
    
    try:
        context.bot.send_message(chat_id=manager_username, text=admin_message)
        logger.info(f"[FINAL_NO] Уведомление о финальном отказе отправлено администратору")
    except Exception as e:
        logger.error(f"[FINAL_NO] Ошибка при отправке уведомления администратору: {e}")
    
    # Сохраняем в БД информацию о выборе
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_response = "Финальный отказ"
            user.subscription_doubt_feedback = "Ожидается ответ пользователя"
            session.commit()
            logger.info(f"[FINAL_NO] Статус пользователя {user_id} обновлен в БД: финальный отказ, ожидается обратная связь")
        else:
            logger.error(f"[FINAL_NO] Пользователь {user_id} не найден в базе данных")
    
    # Запрашиваем обратную связь от пользователя
    feedback_msg = "Поделитесь, пожалуйста, что стало причиной вашего решения? Это поможет нам стать лучше."
    context.bot.send_message(
        chat_id=user_id,
        text=feedback_msg
    )
    logger.info(f"[FINAL_NO] Отправлен запрос обратной связи пользователю {user_id}: '{feedback_msg}'")
    
    # Устанавливаем ожидание текстового сообщения от пользователя
    previous_value = context.user_data.get('waiting_for_feedback', False)
    context.user_data['waiting_for_feedback'] = True
    logger.info(f"[FINAL_NO] Установлен флаг waiting_for_feedback=True для пользователя {user_id} (было: {previous_value})")
    logger.info(f"[FINAL_NO] Текущее состояние user_data для пользователя {user_id}: {context.user_data}")
    
    return ConversationHandler.END

def handle_user_feedback(update: Update, context: CallbackContext):
    """Обработчик обратной связи от пользователя после отказа"""
    user_id = update.effective_user.id
    feedback_text = update.message.text
    
    logger.info(f"[FEEDBACK_HANDLER] Получено сообщение от пользователя {user_id}: {feedback_text}")
    
    # Проверяем, ожидаем ли мы обратную связь от этого пользователя
    if not context.user_data.get('waiting_for_feedback'):
        logger.info(f"[FEEDBACK_HANDLER] Пользователь {user_id} не ожидает обратной связи, пропускаем обработку")
        return None
    
    # Сохраняем обратную связь в БД
    with get_session() as session:
        user = session.query(User).filter(User.user_id == str(user_id)).first()
        if user:
            user.subscription_doubt_feedback = feedback_text
            session.commit()
            logger.info(f"[FEEDBACK_HANDLER] Сохранена обратная связь от пользователя {user_id}: {feedback_text}")
            
            # Сбрасываем флаг ожидания обратной связи
            context.user_data['waiting_for_feedback'] = False
            logger.info(f"[FEEDBACK_HANDLER] Флаг waiting_for_feedback сброшен для пользователя {user_id}")
            
            # Отправляем благодарность пользователю
            update.message.reply_text("Спасибо за ваш отзыв! Мы обязательно учтем его в нашей работе.")
            logger.info(f"[FEEDBACK_HANDLER] Отправлено сообщение благодарности пользователю {user_id}")
            
            # Отправляем уведомление администратору
            config = get_bot_config()
            manager_username = config.get('manager_username', 'telegram')
            
            admin_message = (
                f"Получена обратная связь от пользователя {user_id} "
                f"(@{update.effective_user.username if update.effective_user.username else 'без username'}):\n\n"
                f"{feedback_text}"
            )
            
            try:
                context.bot.send_message(chat_id=manager_username, text=admin_message)
                logger.info(f"[FEEDBACK_HANDLER] Уведомление с обратной связью отправлено администратору")
            except Exception as e:
                logger.error(f"[FEEDBACK_HANDLER] Ошибка при отправке уведомления с обратной связью администратору: {e}")
        else:
            logger.error(f"[FEEDBACK_HANDLER] Пользователь {user_id} не найден в базе данных")
    
    # Всегда возвращаем ConversationHandler.END, чтобы сообщение не обрабатывалось другими обработчиками
    logger.info(f"[FEEDBACK_HANDLER] Завершена обработка обратной связи для пользователя {user_id}")
    return ConversationHandler.END

# Функция для добавления обработчиков в диспетчер
def setup_subscription_doubt_handlers(dispatcher):
    """Добавляет обработчики сомнений при подписке в диспетчер"""
    # Регистрируем обработчики для кнопок сомнений
    logger.info("Настройка обработчиков для сценария сомнений при подписке")
    
    # Обработчики для кнопок сомнений
    dispatcher.add_handler(CallbackQueryHandler(handle_subscription_doubt, pattern=f"^{DOUBT_CB}$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_expensive_doubt, pattern=f"^{EXPENSIVE_CB}$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_result_doubt, pattern=f"^{RESULT_CB}$"))
    
    # Обработчики для ответов "Да/Нет" по дороговизне
    dispatcher.add_handler(CallbackQueryHandler(handle_expensive_yes, pattern=f"^{EXPENSIVE_CB}_yes$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_expensive_no, pattern=f"^{EXPENSIVE_CB}_no$"))
    
    # Обработчики для ответов "Да/Нет" по результату
    dispatcher.add_handler(CallbackQueryHandler(handle_result_yes, pattern=f"^{RESULT_CB}_yes$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_result_no, pattern=f"^{RESULT_CB}_no$"))
    
    # Обработчики для финальных действий
    dispatcher.add_handler(CallbackQueryHandler(handle_back_to_plans, pattern=f"^{BACK_TO_PLANS_CB}$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_final_no, pattern=f"^final_no$"))
    
    # Обработчик для получения обратной связи после отказа
    # Используем фильтр для проверки, ожидаем ли мы обратную связь от этого пользователя
    class FeedbackFilter(MessageFilter):
        def filter(self, message):
            user_id = message.from_user.id
            context = dispatcher.user_data.get(user_id, {})
            waiting = context.get('waiting_for_feedback', False)
            logger.info(f"[FEEDBACK_FILTER] Проверка фильтра для пользователя {user_id}: waiting_for_feedback={waiting}")
            return waiting

    feedback_filter = FeedbackFilter()
    
    # Используем group=-1, чтобы обработчик обратной связи имел приоритет выше других обработчиков текста
    dispatcher.add_handler(MessageHandler(
        Filters.text & ~Filters.command & feedback_filter,
        handle_user_feedback
    ), group=-1)  # Назначаем самый высокий приоритет (group=-1)
    
    # Подробное логирование
    logger.info(f"Зарегистрирован обработчик для кнопки 'Подумаю' с pattern=^{DOUBT_CB}$")
    logger.info(f"Зарегистрирован обработчик для 'Дорого' с pattern=^{EXPENSIVE_CB}$")
    logger.info(f"Зарегистрирован обработчик для 'Будет ли результат' с pattern=^{RESULT_CB}$")
    logger.info(f"Зарегистрирован обработчик обратной связи с приоритетом -1")
    logger.info(f"DOUBT_CB={DOUBT_CB}, EXPENSIVE_CB={EXPENSIVE_CB}, RESULT_CB={RESULT_CB}")
    
    logger.info("Настроены обработчики для сценария сомнений при подписке") 