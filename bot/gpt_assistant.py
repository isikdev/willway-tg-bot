import os
from openai import OpenAI
from dotenv import load_dotenv
from database.models import get_session, User, ChatHistory
from datetime import datetime, timedelta

# Загружаем переменные окружения
load_dotenv()

# Инициализируем клиент OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Загружаем промпт из файла
def load_prompt_from_file(file_path="bot/gpt/WILLWAY_health_assistant_prompt.txt"):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Ошибка при чтении файла промпта: {e}")
        return ""

# Загружаем наш новый промпт
HEALTH_SYSTEM_PROMPT = load_prompt_from_file()

# Функции для работы с историей чата
def save_message_to_history(user_id, role, content):
    """Сохраняет сообщение в историю диалога"""
    db_session = get_session()
    try:
        chat_message = ChatHistory(
            user_id=user_id,
            role=role,
            content=content,
            timestamp=datetime.now()
        )
        db_session.add(chat_message)
        db_session.commit()
    except Exception as e:
        print(f"Ошибка при сохранении сообщения: {e}")
        db_session.rollback()
    finally:
        db_session.close()

def get_chat_history(user_id, limit=10):
    """Получает историю диалога пользователя"""
    db_session = get_session()
    try:
        history = db_session.query(ChatHistory)\
            .filter(ChatHistory.user_id == user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(limit)\
            .all()
        # Переворачиваем список, чтобы сообщения шли в хронологическом порядке
        history.reverse()
        return [{"role": msg.role, "content": msg.content} for msg in history]
    except Exception as e:
        print(f"Ошибка при получении истории: {e}")
        return []
    finally:
        db_session.close()

def get_user_profile(user_id):
    """Получает профиль пользователя из базы данных"""
    db_session = get_session()
    user = db_session.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        db_session.close()
        return None
    
    # Формируем профиль пользователя
    user_profile = {
        'id': user.id,
        'username': user.username,
        'gender': user.gender,
        'age': user.age,
        'height': user.height,
        'weight': user.weight,
        'main_goal': user.main_goal,
        'additional_goal': user.additional_goal,
        'work_format': user.work_format,
        'sport_frequency': user.sport_frequency
    }
    
    db_session.close()
    return user_profile

def format_user_profile_for_gpt(profile):
    """Форматирует профиль пользователя для включения в запрос к GPT"""
    if not profile:
        return "Информация о пользователе отсутствует."
    
    return f"""
Информация о пользователе:
- Пол: {profile['gender'] or 'Не указан'}
- Возраст: {profile['age'] or 'Не указан'} лет
- Рост: {profile['height'] or 'Не указан'} см
- Вес: {profile['weight'] or 'Не указан'} кг
- Основная цель: {profile['main_goal'] or 'Не указана'}
- Дополнительная цель: {profile['additional_goal'] or 'Не указана'}
- Формат работы: {profile['work_format'] or 'Не указан'}
- Частота тренировок: {profile['sport_frequency'] or 'Не указана'}
"""

def get_health_assistant_response(user_id, user_message, conversation_history=None):
    """
    Получает ответ от GPT на запрос пользователя с сохранением истории
    
    Args:
        user_id (int): ID пользователя в Telegram
        user_message (str): Сообщение пользователя
        conversation_history (list, optional): История диалога
        
    Returns:
        str: Ответ от модели GPT
    """
    # Получаем информацию о пользователе
    user_profile = get_user_profile(user_id)
    profile_text = format_user_profile_for_gpt(user_profile)
    
    # Формируем полный промпт с учетом информации о пользователе
    full_prompt = f"{HEALTH_SYSTEM_PROMPT}\n\n{profile_text}"
    
    # Получаем историю диалога из базы данных
    # Если история уже передана, используем ее
    if conversation_history is None:
        conversation_history = get_chat_history(user_id)
    
    # Формируем сообщения для API
    messages = [
        {"role": "system", "content": full_prompt}
    ]
    
    # Добавляем историю диалога
    for message in conversation_history:
        messages.append(message)
    
    # Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})
    
    try:
        # Сохраняем сообщение пользователя в историю
        save_message_to_history(user_id, "user", user_message)
        
        # Отправляем запрос к API OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Можно улучшить до gpt-4o
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        # Получаем ответ
        assistant_response = response.choices[0].message.content
        
        # Сохраняем ответ ассистента в историю
        save_message_to_history(user_id, "assistant", assistant_response)
        
        # Возвращаем текст ответа
        return assistant_response
    except Exception as e:
        return f"Извините, произошла ошибка при обработке вашего запроса: {str(e)}"
