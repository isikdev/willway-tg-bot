import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from datetime import datetime
from health_bot.payment.payment_handler import PaymentHandler
from health_bot.database.database import get_user_by_tg_id, save_user_data, get_user_data

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация обработчика платежей
payment_handler = PaymentHandler()

# Состояния для ConversationHandler
(
    CHOOSING_SUBSCRIPTION,
    ENTERING_EMAIL,
    ENTERING_PHONE,
    CONFIRMING_PAYMENT
) = range(4)

# Цены подписок (для показа пользователю)
MONTHLY_PRICE = "2,222 ₽"
YEARLY_PRICE = "17,777 ₽ (экономия 35%)"

# Callback данные для клавиатуры
MONTHLY_SUBSCRIPTION = "subscription_monthly"
YEARLY_SUBSCRIPTION = "subscription_yearly"
CONFIRM_PAYMENT = "confirm_payment"
CANCEL_PAYMENT = "cancel_payment"

async def start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запуск процесса оплаты подписки.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    # Проверка текущего статуса подписки пользователя
    user_id = update.effective_user.id
    user = get_user_by_tg_id(user_id)
    
    if user:
        # Проверка статуса подписки в Airtable
        subscription_status = payment_handler.check_subscription_status(str(user_id))
        
        if subscription_status.get('has_subscription'):
            # У пользователя есть активная подписка
            expires_at = subscription_status.get('expires_at', '')
            days_left = subscription_status.get('days_left', 0)
            subscription_type = "месячная" if subscription_status.get('subscription_type') == 'monthly' else "годовая"
            
            await update.message.reply_text(
                f"У вас уже есть активная {subscription_type} подписка!\n\n"
                f"Подписка действует ещё {days_left} дней до {expires_at}.\n\n"
                f"Вы можете продлить подписку после её окончания."
            )
            return ConversationHandler.END
    
    # Предложение выбора подписки
    keyboard = [
        [InlineKeyboardButton(f"Месячная подписка ({MONTHLY_PRICE})", callback_data=MONTHLY_SUBSCRIPTION)],
        [InlineKeyboardButton(f"Годовая подписка ({YEARLY_PRICE})", callback_data=YEARLY_SUBSCRIPTION)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите тип подписки:",
        reply_markup=reply_markup
    )
    
    return CHOOSING_SUBSCRIPTION

async def subscription_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка выбора типа подписки.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    query = update.callback_query
    await query.answer()
    
    # Сохранение выбранного типа подписки
    if query.data == MONTHLY_SUBSCRIPTION:
        context.user_data['subscription_type'] = 'monthly'
        context.user_data['subscription_name'] = 'Месячная подписка'
        context.user_data['subscription_price'] = MONTHLY_PRICE
    else:
        context.user_data['subscription_type'] = 'yearly'
        context.user_data['subscription_name'] = 'Годовая подписка'
        context.user_data['subscription_price'] = YEARLY_PRICE
    
    # Запрос email
    await query.edit_message_text(
        f"Вы выбрали: {context.user_data['subscription_name']} ({context.user_data['subscription_price']})\n\n"
        "Пожалуйста, введите ваш email:"
    )
    
    return ENTERING_EMAIL

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка ввода email.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    user_email = update.message.text.strip()
    
    # Простая валидация email
    if '@' not in user_email or '.' not in user_email:
        await update.message.reply_text(
            "Пожалуйста, введите корректный email адрес:"
        )
        return ENTERING_EMAIL
    
    # Сохранение email
    context.user_data['email'] = user_email
    
    # Запрос номера телефона
    await update.message.reply_text(
        "Спасибо! Теперь введите ваш номер телефона в формате +7XXXXXXXXXX:"
    )
    
    return ENTERING_PHONE

async def process_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка ввода телефона.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    user_phone = update.message.text.strip()
    
    # Простая валидация номера телефона
    if not user_phone.startswith('+'):
        await update.message.reply_text(
            "Пожалуйста, введите номер телефона в международном формате, начиная с '+':"
        )
        return ENTERING_PHONE
    
    # Сохранение номера телефона
    context.user_data['phone'] = user_phone
    
    # Сохранение данных пользователя
    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    
    user_data = {
        'email': context.user_data['email'],
        'phone': context.user_data['phone']
    }
    
    save_user_data(user_id, user_data)
    
    # Подготовка данных для создания платежа
    payment_user_data = {
        'user_id': str(user_id),
        'email': context.user_data['email'],
        'phone': context.user_data['phone'],
        'username': username
    }
    
    # Создание ссылки на оплату
    payment_data = payment_handler.generate_payment_link(
        user_data=payment_user_data,
        subscription_type=context.user_data['subscription_type']
    )
    
    if not payment_data:
        await update.message.reply_text(
            "Произошла ошибка при создании платежа. Пожалуйста, попробуйте позже."
        )
        return ConversationHandler.END
    
    # Сохранение данных платежа
    context.user_data['payment_url'] = payment_data['payment_url']
    context.user_data['payment_id'] = payment_data['payment_id']
    
    logger.info(f"Создана ссылка на оплату: {payment_data['payment_url']}")
    
    # Отправка сообщения для подтверждения
    keyboard = [
        [InlineKeyboardButton("Оплатить", url=payment_data['payment_url'])],
        [InlineKeyboardButton("Проверить статус оплаты", callback_data=CONFIRM_PAYMENT)],
        [InlineKeyboardButton("Отмена", callback_data=CANCEL_PAYMENT)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Данные для оплаты:\n\n"
        f"Подписка: {context.user_data['subscription_name']}\n"
        f"Стоимость: {context.user_data['subscription_price']}\n"
        f"Email: {context.user_data['email']}\n"
        f"Телефон: {context.user_data['phone']}\n\n"
        f"Для оплаты нажмите кнопку 'Оплатить'.\n"
        f"После оплаты вернитесь в бот и нажмите 'Проверить статус оплаты'.",
        reply_markup=reply_markup
    )
    
    return CONFIRMING_PAYMENT

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Проверка статуса оплаты.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == CANCEL_PAYMENT:
        await query.edit_message_text("Оплата отменена.")
        return ConversationHandler.END
    
    # Проверка статуса платежа
    payment_id = context.user_data.get('payment_id')
    payment_status = payment_handler.check_payment_status(payment_id)
    
    if not payment_status:
        await query.edit_message_text(
            "Не удалось получить информацию о платеже. Пожалуйста, попробуйте позже."
        )
        return ConversationHandler.END
    
    if payment_status.get('is_paid'):
        # Платеж успешно оплачен
        user_id = update.effective_user.id
        
        # Сохраняем информацию о подписке
        user_data = get_user_data(user_id)
        if user_data:
            user_data['has_subscription'] = True
            user_data['subscription_type'] = context.user_data['subscription_type']
            user_data['subscription_expires'] = payment_status.get('expires_at', '')
            save_user_data(user_id, user_data)
        
        # Отправка сообщения об успешной оплате
        subscription_type = "месячная" if context.user_data['subscription_type'] == 'monthly' else "годовая"
        
        await query.edit_message_text(
            f"🎉 Поздравляем! Ваша {subscription_type} подписка успешно оплачена!\n\n"
            f"Теперь вам доступны все функции. Наслаждайтесь использованием!"
        )
        
        # Отправка сообщения с инструкциями
        await context.bot.send_message(
            chat_id=user_id,
            text="Теперь вы можете использовать все функции бота. "
                 "Доступ к подписке также открыт на сайте."
        )
        
        return ConversationHandler.END
    else:
        # Платеж не оплачен
        keyboard = [
            [InlineKeyboardButton("Оплатить", url=context.user_data['payment_url'])],
            [InlineKeyboardButton("Проверить статус оплаты", callback_data=CONFIRM_PAYMENT)],
            [InlineKeyboardButton("Отмена", callback_data=CANCEL_PAYMENT)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Оплата ещё не произведена. Пожалуйста, перейдите по ссылке для оплаты.\n"
            "После оплаты вернитесь и нажмите 'Проверить статус оплаты'.",
            reply_markup=reply_markup
        )
        
        return CONFIRMING_PAYMENT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отмена процесса оплаты.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    await update.message.reply_text(
        "Процесс оплаты отменен. Вы можете начать снова, введя команду /payment."
    )
    
    return ConversationHandler.END

async def subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Проверка статуса подписки пользователя.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
    """
    user_id = update.effective_user.id
    
    # Проверка статуса подписки в Airtable
    subscription_status = payment_handler.check_subscription_status(str(user_id))
    
    if subscription_status.get('has_subscription'):
        # У пользователя есть активная подписка
        expires_at = subscription_status.get('expires_at', '')
        days_left = subscription_status.get('days_left', 0)
        subscription_type = "Месячная" if subscription_status.get('subscription_type') == 'monthly' else "Годовая"
        
        await update.message.reply_text(
            f"✅ У вас есть активная подписка!\n\n"
            f"Тип подписки: {subscription_type}\n"
            f"Действует до: {expires_at}\n"
            f"Осталось дней: {days_left}"
        )
    else:
        # У пользователя нет активной подписки
        keyboard = [
            [InlineKeyboardButton("Приобрести подписку", callback_data="start_payment")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ У вас нет активной подписки.\n\n"
            "Приобретите подписку, чтобы получить доступ ко всем функциям.",
            reply_markup=reply_markup
        )

async def payment_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработка нажатия кнопки для начала оплаты.
    
    Args:
        update: Объект Update от Telegram
        context: Объект контекста
        
    Returns:
        int: Следующее состояние диалога
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_payment":
        # Предложение выбора подписки
        keyboard = [
            [InlineKeyboardButton(f"Месячная подписка ({MONTHLY_PRICE})", callback_data=MONTHLY_SUBSCRIPTION)],
            [InlineKeyboardButton(f"Годовая подписка ({YEARLY_PRICE})", callback_data=YEARLY_SUBSCRIPTION)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Выберите тип подписки:",
            reply_markup=reply_markup
        )
        
        return CHOOSING_SUBSCRIPTION
    
    return ConversationHandler.END

# Создание обработчиков
payment_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("payment", start_payment),
        CallbackQueryHandler(payment_button, pattern="^start_payment$")
    ],
    states={
        CHOOSING_SUBSCRIPTION: [
            CallbackQueryHandler(subscription_choice, pattern=f"^{MONTHLY_SUBSCRIPTION}$|^{YEARLY_SUBSCRIPTION}$")
        ],
        ENTERING_EMAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)
        ],
        ENTERING_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)
        ],
        CONFIRMING_PAYMENT: [
            CallbackQueryHandler(confirm_payment, pattern=f"^{CONFIRM_PAYMENT}$|^{CANCEL_PAYMENT}$")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

# Обработчик для проверки статуса подписки
status_handler = CommandHandler("status", subscription_status)

def register_payment_handlers(application):
    """
    Регистрация обработчиков платежей в приложении.
    
    Args:
        application: Объект Application Telegram бота
    """
    application.add_handler(payment_conversation)
    application.add_handler(status_handler) 