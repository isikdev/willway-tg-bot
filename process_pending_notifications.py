import os
import sys
import json
import logging
import time
from datetime import datetime

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем путь к корневой директории проекта
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Импортируем необходимые модули
try:
    from database.models import get_session, User, PendingNotification
    from bot.handlers import initialize_bot
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    logger.info("Модули успешно импортированы")
except Exception as e:
    logger.error(f"Ошибка при импорте модулей: {str(e)}")
    sys.exit(1)

def send_referral_bonus_notification(bot, notification, session):
    """Отправляет уведомление о начислении реферального бонуса"""
    try:
        data = json.loads(notification.data)
        referral_username = data.get('referral_username', 'пользователь')
        
        # Получаем данные о пользователе
        user = session.query(User).filter_by(user_id=notification.user_id).first()
        if not user:
            logger.error(f"Пользователь {notification.user_id} не найден в базе данных")
            return False
        
        # Формируем сообщение с актуальной информацией о подписке
        subscription_end = user.subscription_expires.strftime("%d.%m.%Y") if user.subscription_expires else "неизвестно"
        message = (
            f"🎁 *Поздравляем!* Вы получили бонусный месяц подписки!\n\n"
            f"Ваш друг *{referral_username}* оплатил подписку по вашей реферальной ссылке.\n\n"
            f"Срок действия вашей подписки был продлен на 30 дней.\n"
            f"Текущая дата окончания подписки: *{subscription_end}*\n\n"
            f"Продолжайте приглашать друзей и получать бонусные месяцы!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Пригласить еще друзей", callback_data="invite_friend")],
            [InlineKeyboardButton(text="Управление подпиской", callback_data="subscription_management")]
        ])
        
        bot.send_message(
            chat_id=notification.user_id,
            text=message,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о бонусе: {str(e)}")
        return False

def process_pending_notifications():
    logger.info("Начало обработки отложенных уведомлений")
    
    try:
        bot = initialize_bot()
        if not bot:
            logger.error("Не удалось инициализировать бота")
            return False
        
        session = get_session()
        
        notifications = session.query(PendingNotification)\
            .filter(PendingNotification.sent == False)\
            .filter(PendingNotification.retries < 5)\
            .order_by(PendingNotification.created_at)\
            .limit(50)\
            .all()
        
        if not notifications:
            logger.info("Отложенных уведомлений не найдено")
            return True
        
        logger.info(f"Найдено {len(notifications)} отложенных уведомлений для обработки")
        
        for notification in notifications:
            try:
                result = False
                
                if notification.message_type == "referral_bonus":
                    result = send_referral_bonus_notification(bot, notification, session)
                
                if result:
                    notification.sent = True
                    notification.sent_at = datetime.now()
                    session.commit()
                    logger.info(f"Уведомление ID={notification.id} успешно отправлено")
                else:
                    notification.retries += 1
                    session.commit()
                    logger.warning(f"Не удалось отправить уведомление ID={notification.id}, попытка {notification.retries}/5")
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке уведомления ID={notification.id}: {str(e)}")
                notification.retries += 1
                session.commit()
            
        logger.info("Обработка отложенных уведомлений завершена")
        session.close()
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при обработке отложенных уведомлений: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Запуск обработчика отложенных уведомлений")
    if process_pending_notifications():
        logger.info("Обработка уведомлений завершена успешно")
    else:
        logger.error("Возникли ошибки при обработке уведомлений") 