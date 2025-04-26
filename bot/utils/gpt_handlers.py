"""
Обработчики для модуля GPT Assistant
"""
import os
import sys
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.models import get_session, User, MessageHistory
from bot.survey.constants import MAIN, GPT_ASSISTANT
from bot.payment.handlers import get_payment_keyboard
from bot.utils.keyboards import menu_keyboard

# Получаем логгер
logger = logging.getLogger('root')

def health_assistant_button(update: Update, context: CallbackContext):
    """Обработчик нажатия на кнопку HealthAssistant"""
    query = update.callback_query
    query.answer()
    
    bot_message = (
        "Привет! Я Health Assistant. Я могу ответить на ваши вопросы о здоровье, питании и тренировках.\n\n"
        "Просто напишите свой вопрос, и я постараюсь на него ответить."
    )
    
    query.edit_message_text(
        text=bot_message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
        ])
    )
    
    # Устанавливаем состояние GPT_ASSISTANT
    context.user_data['state'] = GPT_ASSISTANT
    return GPT_ASSISTANT

def get_user_conversation_history(user_id, limit=10):
    """Получает историю диалога пользователя с ассистентом"""
    session = get_session()
    try:
        # Получаем последние сообщения пользователя
        messages = session.query(MessageHistory).filter(
            MessageHistory.user_id == user_id
        ).order_by(MessageHistory.created_at.desc()).limit(limit).all()
        
        # Сортируем сообщения в хронологическом порядке
        messages.reverse()
        
        # Форматируем сообщения в список словарей для модели
        history = []
        for message in messages:
            history.append({
                "role": message.role,
                "content": message.content
            })
        
        return history
    except Exception as e:
        logger.error(f"Ошибка при получении истории диалога: {e}")
        return []
    finally:
        session.close()

def save_message_to_history(user_id, role, content):
    """Сохраняет сообщение в историю диалога"""
    session = get_session()
    try:
        # Создаем новую запись в истории сообщений
        message = MessageHistory(
            user_id=user_id,
            role=role,
            content=content,
            created_at=datetime.now()
        )
        
        session.add(message)
        session.commit()
        
        # Удаляем старые сообщения, если их больше 50
        count = session.query(MessageHistory).filter(
            MessageHistory.user_id == user_id
        ).count()
        
        if count > 50:
            # Получаем ID самых старых сообщений для удаления
            old_messages = session.query(MessageHistory).filter(
                MessageHistory.user_id == user_id
            ).order_by(MessageHistory.created_at.asc()).limit(count - 50).all()
            
            for old_message in old_messages:
                session.delete(old_message)
            
            session.commit()
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении сообщения в историю: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def handle_health_assistant_message(update: Update, context: CallbackContext):
    """Обработчик сообщений для Health Assistant"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Если пользователь нажал кнопку "Назад", возвращаемся в главное меню
    if user_message == "Назад":
        # Импортируем функцию get_main_keyboard из handlers.py
        from bot.handlers import get_main_keyboard
        
        # Отправляем сообщение с главным меню и нижней клавиатурой
        update.message.reply_text(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
        
        # Очищаем состояние
        context.user_data.clear()
        
        return MAIN
    
    # Проверяем подписку пользователя
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or not user.is_subscribed:
            # Если пользователь не подписан, предлагаем оформить подписку
            update.message.reply_text(
                "Чтобы продолжить использование Health Assistant, необходимо оформить подписку.",
                reply_markup=get_payment_keyboard(user_id, context)
            )
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки: {e}")
    finally:
        session.close()
    
    # Сохраняем сообщение пользователя в историю
    save_message_to_history(user_id, "user", user_message)
    
    # Получаем историю диалога
    conversation_history = get_user_conversation_history(user_id)
    
    # Отправляем запрос к GPT и получаем ответ
    try:
        # Отправляем "печатает..." статус
        context.bot.send_chat_action(chat_id=user_id, action='typing')
        
        from bot.gpt_assistant import get_health_assistant_response
        assistant_response = get_health_assistant_response(user_message, conversation_history)
        
        # Сохраняем ответ ассистента в историю
        save_message_to_history(user_id, "assistant", assistant_response)
        
        # Отправляем ответ пользователю
        update.message.reply_text(
            assistant_response,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении ответа от ассистента: {e}")
        update.message.reply_text(
            "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
            ])
        )
    
    return GPT_ASSISTANT 