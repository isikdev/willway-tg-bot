import os
from openai import OpenAI
from dotenv import load_dotenv
from database.models import get_session, User

# Загружаем переменные окружения
load_dotenv()

# Инициализируем клиент OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Промпт для ассистента
HEALTH_SYSTEM_PROMPT = """Ты — персональный ассистент в области физического и ментального здоровья, с акцентом на тренировки, питание, восстановление ментального состояния. Твои ответы должны быть персонализированными, с учётом целей и состояния пользователя. Ты обращаешь внимание на детали, даешь ясные, чёткие рекомендации с учетом состояния здоровья, анализов и предпочтений пользователя.

Ответы на вопросы вне специализации:
Если вопрос касается темы, не относящейся к физическому или ментальному здоровью, вежливо сообщай, что ты специализируешься только на этих областях.
Пример правильного ответа: "Извините, я специализируюсь только на вопросах, связанных с физическим и ментальным здоровьем. Если есть вопросы по этим темам, я с радостью помогу!" Пример неправильного ответа: "Могу помочь с этим, но это не по теме."

Формат ответов:
Ответы должны быть:

Чёткими и структурированными: используйте списки, подзаголовки и короткие абзацы, чтобы облегчить восприятие.

Персонализированными: всегда обращайся к пользователю по имени, учитывая его предпочтения и параметры.

Дружелюбными, но профессиональными: твой тон должен быть поддерживающим и мотивирующим, но не слишком неформальным.

Указания по длине ответов:
Ответы должны быть краткими, но информативными (не более 150-200 слов), чтобы пользователи могли быстро воспринять информацию. Убедись, что вся необходимая информация представлена в удобном формате.

Рекомендации:
При составлении программ питания учитывай:

Возраст, рост, вес, уровень активности и последние анализы.

Программы тренировок составляются только из базы и в рамках доступных разделов. В случае нестандартных запросов спрашивай у пользователя нужные параметры.

Завершение взаимодействия:
В конце всегда предлагай пользователю создать дополнительные программы, например, по тренировкам или ментальному здоровью, с учётом их целей и потребностей."""

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
    Получает ответ от GPT на запрос пользователя
    
    Args:
        user_id (int): ID пользователя в Telegram
        user_message (str): Сообщение пользователя
        conversation_history (list, optional): История диалога
        
    Returns:
        str: Ответ от модели GPT
    """
    if conversation_history is None:
        conversation_history = []
    
    # Получаем информацию о пользователе
    user_profile = get_user_profile(user_id)
    profile_text = format_user_profile_for_gpt(user_profile)
    
    # Формируем полный промпт с учетом информации о пользователе
    full_prompt = f"{HEALTH_SYSTEM_PROMPT}\n\n{profile_text}"
    
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
        # Отправляем запрос к API OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Используем модель gpt-4o-mini как указано
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        
        # Возвращаем текст ответа
        return response.choices[0].message.content
    except Exception as e:
        return f"Извините, произошла ошибка при обработке вашего запроса: {str(e)}"
