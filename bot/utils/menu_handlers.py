"""
Обработчики меню и навигации
"""
import os
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from database.models import get_session, User
from bot.survey.constants import MAIN, SUPPORT_OPTIONS, SUBSCRIPTION
from bot.payment.handlers import get_payment_keyboard
from bot.utils.keyboards import menu_keyboard, support_keyboard
from bot.utils.gpt_handlers import health_assistant_button

# Получаем логгер
logger = logging.getLogger('root')

def back_to_main_menu(update: Update, context: CallbackContext):
    """Возвращает пользователя в главное меню"""
    user_id = update.effective_user.id
    
    # Определяем тип запроса (callback или обычное сообщение)
    is_callback = update.callback_query is not None
    
    # Проверяем, заполнил ли пользователь анкету
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь существует, но анкета не заполнена
        if user and not user.registered:
            logger.info(f"[SURVEY_REQUIRED] Пользователь {user_id} пытается использовать меню без заполнения анкеты")
            
            # Предлагаем заполнить анкету
            keyboard = [
                [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if is_callback:
                query = update.callback_query
                query.answer()
                query.edit_message_text(
                    "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                    reply_markup=reply_markup
                )
            else:
                update.message.reply_text(
                    "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                    reply_markup=reply_markup
                )
            
            session.close()
            return ConversationHandler.END
        
        session.close()
        
        # Импортируем функцию get_main_keyboard из handlers.py
        from bot.handlers import get_main_keyboard
        
        # Если анкета заполнена, показываем главное меню с клавиатурой внизу
        if is_callback:
            query = update.callback_query
            query.answer()
            
            # Сначала отредактируем текущее сообщение, чтобы убрать inline кнопки
            try:
                query.edit_message_text("Главное меню:")
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения: {e}")
                
            # Затем отправим новое сообщение с основной клавиатурой внизу
            context.bot.send_message(
                chat_id=user_id,
                text="Выберите действие:",
                reply_markup=get_main_keyboard()
            )
        else:
            update.message.reply_text(
                "Выберите действие:",
                reply_markup=get_main_keyboard()
            )
        
        # Очищаем состояние
        context.user_data.clear()
        
        return MAIN
    except Exception as e:
        logger.error(f"[SURVEY_CHECK_ERROR] Ошибка при проверке статуса анкеты: {e}")
        if 'session' in locals() and session:
            session.close()
        
        # В случае ошибки все равно показываем меню
        try:
            # Импортируем функцию get_main_keyboard из handlers.py
            from bot.handlers import get_main_keyboard
            
            if is_callback:
                try:
                    query = update.callback_query
                    query.answer()
                    
                    # Пробуем отредактировать текущее сообщение
                    try:
                        query.edit_message_text("Главное меню:")
                    except Exception as e:
                        logger.error(f"Ошибка при редактировании сообщения: {e}")
                    
                    # Отправляем новое сообщение с основной клавиатурой
                    context.bot.send_message(
                        chat_id=user_id,
                        text="Выберите действие:",
                        reply_markup=get_main_keyboard()
                    )
                except Exception as edit_error:
                    logger.error(f"[MENU_ERROR] Не удалось отправить сообщение: {edit_error}")
                    if update.message:
                        update.message.reply_text(
                            "Выберите действие:",
                            reply_markup=get_main_keyboard()
                        )
            else:
                update.message.reply_text(
                    "Выберите действие:",
                    reply_markup=get_main_keyboard()
                )
        except Exception as import_error:
            logger.error(f"[IMPORT_ERROR] Не удалось импортировать get_main_keyboard: {import_error}")
            # Если импорт не удался, используем встроенное меню
            if is_callback:
                query = update.callback_query
                query.answer()
                query.edit_message_text(
                    "Главное меню:",
                    reply_markup=menu_keyboard()
                )
            else:
                update.message.reply_text(
                    "Главное меню:",
                    reply_markup=menu_keyboard()
                )
        
        return MAIN

def handle_menu_callback(update: Update, context: CallbackContext):
    """Обработчик нажатий на кнопки меню."""
    query = update.callback_query
    query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    # Проверяем, заполнил ли пользователь анкету
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь существует, но анкета не заполнена
        if user and not user.registered:
            logger.info(f"[SURVEY_REQUIRED] Пользователь {user_id} пытается использовать меню без заполнения анкеты")
            
            # Предлагаем заполнить анкету
            keyboard = [
                [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(
                "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                reply_markup=reply_markup
            )
            
            session.close()
            return ConversationHandler.END
        
        # Если анкета заполнена, продолжаем обычную обработку
        if callback_data == "health_assistant":
            # Переход к Health Assistant
            session.close()
            return health_assistant_button(update, context)
        
        elif callback_data == "menu_support":
            # Показываем меню поддержки
            session.close()
            query.edit_message_text(
                "Выберите опцию поддержки:",
                reply_markup=support_keyboard()
            )
            return SUPPORT_OPTIONS
        
        elif callback_data == "menu_nutrition" or callback_data == "menu_training":
            # Проверяем, есть ли активная подписка
            is_subscribed = user and user.is_subscribed
            
            if not is_subscribed:
                # Если нет подписки, предлагаем оформить
                session.close()
                query.edit_message_text(
                    "Для доступа к этому разделу необходима подписка:",
                    reply_markup=get_payment_keyboard(user_id, context)
                )
                return SUBSCRIPTION
            
            # Если есть подписка, показываем соответствующий раздел
            if callback_data == "menu_nutrition":
                # Показываем раздел питания
                session.close()
                query.edit_message_text(
                    "Раздел питания:\n\n"
                    "Здесь будут доступны ваши персональные рекомендации по питанию, рецепты и многое другое.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                    ])
                )
            else:  # menu_training
                # Показываем раздел тренировок
                session.close()
                query.edit_message_text(
                    "Раздел тренировок:\n\n"
                    "Здесь будут доступны ваши персональные тренировки и рекомендации.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Вернуться в меню", callback_data="back_to_menu")]
                    ])
                )
                
    except Exception as e:
        logger.error(f"Ошибка при проверке подписки или анкеты: {e}")
        # В случае ошибки возвращаем в главное меню
        if 'session' in locals() and session:
            session.close()
        query.edit_message_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=menu_keyboard()
        )
    
    return MAIN

def handle_text_messages(update, context):
    """Обрабатывает текстовые сообщения от пользователя."""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, находится ли пользователь в состоянии GPT_ASSISTANT
    if context.user_data.get('state') == 'GPT_ASSISTANT':
        # Перенаправляем сообщение в обработчик Health Assistant
        from bot.utils.gpt_handlers import handle_health_assistant_message
        return handle_health_assistant_message(update, context)
    
    # Проверяем, заполнил ли пользователь анкету
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь существует, но анкета не заполнена
        if user and not user.registered:
            logger.info(f"[SURVEY_REQUIRED] Пользователь {user_id} пытается использовать текстовые команды без заполнения анкеты")
            
            # Предлагаем заполнить анкету
            keyboard = [
                [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                reply_markup=reply_markup
            )
            
            session.close()
            return ConversationHandler.END
        
        session.close()
        
        # Обрабатываем текстовые сообщения
        update.message.reply_text(
            "Пожалуйста, используйте меню для взаимодействия с ботом.",
            reply_markup=menu_keyboard()
        )
        
        return MAIN
    except Exception as e:
        logger.error(f"[SURVEY_CHECK_ERROR] Ошибка при проверке статуса анкеты: {e}")
        if 'session' in locals() and session:
            session.close()
        
        # В случае ошибки все равно показываем сообщение
        update.message.reply_text(
            "Пожалуйста, используйте меню для взаимодействия с ботом.",
            reply_markup=menu_keyboard()
        )
        
        return MAIN

def cancel(update: Update, context: CallbackContext) -> int:
    """Отменяет текущий диалог и возвращает пользователя в главное меню."""
    user_id = update.effective_user.id
    
    # Проверяем, заполнил ли пользователь анкету
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        
        # Если пользователь существует, но анкета не заполнена
        if user and not user.registered:
            logger.info(f"[SURVEY_REQUIRED] Пользователь {user_id} пытается вернуться в меню без заполнения анкеты")
            
            # Предлагаем заполнить анкету
            keyboard = [
                [InlineKeyboardButton("Подобрать персональную программу", callback_data="start_survey")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                "Для получения доступа к функциям бота, пожалуйста, заполните анкету:",
                reply_markup=reply_markup
            )
            
            session.close()
            return ConversationHandler.END
        
        session.close()
        
        # Если анкета заполнена, возвращаем в главное меню
        update.message.reply_text(
            "Операция отменена. Вы можете вернуться к этому позже.",
            reply_markup=menu_keyboard()
        )
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"[SURVEY_CHECK_ERROR] Ошибка при проверке статуса анкеты: {e}")
        if 'session' in locals() and session:
            session.close()
        
        # В случае ошибки все равно показываем меню
        update.message.reply_text(
            "Операция отменена. Вы можете вернуться к этому позже.",
            reply_markup=menu_keyboard()
        )
        return ConversationHandler.END 