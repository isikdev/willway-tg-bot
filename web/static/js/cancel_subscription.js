function logEvent(message, data = null) {
    const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
    if (data) {
        console.log(`[${timestamp}] ${message}`, data);
    } else {
        console.log(`[${timestamp}] ${message}`);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    logEvent('Скрипт отмены подписки успешно инициализирован');

    const urlParams = new URLSearchParams(window.location.search);
    const userId = urlParams.get('user_id');

    if (!userId) {
        logEvent('ОШИБКА: Отсутствует ID пользователя в URL параметрах');
        return;
    }

    logEvent(`Найден ID пользователя: ${userId}`);

    const cancelForm = document.querySelector('form[action*="cancel"]');
    const mainContainer = document.querySelector('.t-container') ||
        document.querySelector('.tn-atom') ||
        document.querySelector('main') ||
        document.body;

    logEvent(`Основной контейнер найден: ${mainContainer.tagName}`);

    const confirmCancelButton = document.querySelector('.cancel-subscription-button, a[data-action="cancel-subscription"]');

    if (confirmCancelButton) {
        logEvent(`Кнопка отмены найдена: ${confirmCancelButton.tagName}`, {
            id: confirmCancelButton.id,
            classes: confirmCancelButton.className,
            attributes: Array.from(confirmCancelButton.attributes).map(a => `${a.name}="${a.value}"`).join(', ')
        });

        ['mousedown', 'mouseup', 'touchstart', 'touchend'].forEach(eventType => {
            confirmCancelButton.addEventListener(eventType, function (event) {
                logEvent(`Событие ${eventType} на кнопке отмены подписки`);
            });
        });
    } else {
        logEvent('ОШИБКА: Кнопка отмены подписки не найдена на странице после создания');
    }

    document.addEventListener('click', function (event) {
        const target = event.target;
        if (target.classList.contains('cancel-subscription-button') ||
            target.closest('.cancel-subscription-button') ||
            target.hasAttribute('data-action') && target.getAttribute('data-action') === 'cancel-subscription') {
            logEvent('ГЛОБАЛЬНЫЙ ПЕРЕХВАТ: Клик по кнопке отмены подписки', {
                element: target.tagName,
                id: target.id,
                class: target.className
            });
        }
    });
});

function sendCancellationWebhook(userId, status, additionalData = {}) {
    logEvent(`ЗАПРОС: Начало отправки webhook для отмены подписки пользователя: ${userId}`);

    const apiUrl = 'https://api-willway.ru/api/v1/subscription/cancel';
    logEvent(`ЗАПРОС: Endpoint URL для webhook: ${apiUrl}`);

    const webhookData = {
        user_id: userId,
        status: status,
        timestamp: new Date().toISOString(),
        source: 'web',
        ...additionalData
    };

    logEvent('ЗАПРОС: Отправляемые данные:', webhookData);

    logEvent('ЗАПРОС: Отправка запроса...');
    fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(webhookData)
    })
        .then(response => {
            logEvent(`ОТВЕТ: Получен HTTP-статус: ${response.status}`);
            logEvent('ОТВЕТ: Полный объект ответа:', {
                ok: response.ok,
                status: response.status,
                statusText: response.statusText,
                headers: Array.from(response.headers.entries())
            });

            if (!response.ok) {
                throw new Error('Ошибка HTTP: ' + response.status);
            }
            return response.json().catch(() => {
                logEvent('ОТВЕТ: Не удалось разобрать JSON, возвращаем статус');
                return { status: response.status, success: response.ok };
            });
        })
        .then(data => {
            logEvent('УСПЕХ: Webhook отправлен успешно, ответ сервера:', data);

            showConfirmationMessage();
        })
        .catch(error => {
            logEvent(`ОШИБКА: При отправке webhook: ${error.message}`, {
                stack: error.stack
            });
            showConfirmationMessage('Возникла ошибка при отправке запроса. Пожалуйста, свяжитесь с поддержкой.');
        });
}

function showConfirmationMessage(customMessage) {
    logEvent('Показываем сообщение о результате: ' + (customMessage || 'успешно'));

    let messageElement = document.querySelector('.cancellation-confirmation-message');

    if (!messageElement) {
        messageElement = document.createElement('div');
        messageElement.className = 'cancellation-confirmation-message';
        messageElement.style.cssText = 'background-color: #4CAF50; color: white; padding: 15px; margin: 20px auto; border-radius: 5px; text-align: center; max-width: 600px; font-weight: bold; z-index: 9999;';

        const container = document.querySelector('.form-container') ||
            document.querySelector('.t-container') ||
            document.querySelector('.tn-atom') ||
            document.querySelector('main') ||
            document.body;

        container.insertBefore(messageElement, container.firstChild);
        logEvent('Создан элемент сообщения');
    }

    messageElement.textContent = customMessage || 'Ваша подписка успешно отменена. Уведомление отправлено в Telegram.';

    if (customMessage && customMessage.includes('ошибка')) {
        messageElement.style.backgroundColor = '#dc3545';
    }

    messageElement.scrollIntoView({ behavior: 'smooth' });
    logEvent('Страница прокручена к сообщению');

    const cancelButton = document.querySelector('.cancel-subscription-button, a[data-action="cancel-subscription"]');
    if (cancelButton) {
        cancelButton.style.display = 'none';
        logEvent('Кнопка отмены подписки скрыта');
    }
}