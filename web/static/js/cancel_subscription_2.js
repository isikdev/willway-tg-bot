/**
 * JavaScript для обработки отмены подписки на странице willway.pro/cancelmembers
 */

// Создаем функцию логирования с временной меткой
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

    // Получаем ID пользователя из URL параметров
    const urlParams = new URLSearchParams(window.location.search);
    const userId = urlParams.get('user_id');

    if (!userId) {
        logEvent('ОШИБКА: Отсутствует ID пользователя в URL параметрах');
        return;
    }

    logEvent(`Найден ID пользователя: ${userId}`);

    // Находим форму отмены подписки или основной контейнер
    const cancelForm = document.querySelector('form[action*="cancel"]');
    const mainContainer = document.querySelector('.t-container') ||
        document.querySelector('.tn-atom') ||
        document.querySelector('main') ||
        document.body;

    logEvent(`Основной контейнер найден: ${mainContainer.tagName}`);

    // В текущей версии не отображаем ничего на странице отмены подписки
    // Весь основной блок закомментирован

    /*
    if (cancelForm) {
        logEvent('Найдена форма отмены подписки');
        // Если форма существует, добавляем к ней скрытое поле с ID пользователя
        const userIdField = document.createElement('input');
        userIdField.type = 'hidden';
        userIdField.name = 'telegram_user_id';
        userIdField.value = userId;
        cancelForm.appendChild(userIdField);
        logEvent('Добавлено скрытое поле с ID пользователя в форму');

        // Добавляем обработчик отправки формы
        cancelForm.addEventListener('submit', function (event) {
            // Предотвращаем стандартную отправку формы
            event.preventDefault();
            logEvent('Перехвачена отправка формы');

            // Получаем данные формы
            const formData = new FormData(cancelForm);
            const formDataObj = {};

            formData.forEach((value, key) => {
                formDataObj[key] = value;
            });

            // Добавляем ID пользователя
            formDataObj.user_id = userId;
            logEvent('Подготовлены данные формы для отправки', formDataObj);

            // Отправляем webhook в наш бот
            sendCancellationWebhook(userId, 'cancelled', formDataObj);
        });
    } else {
        logEvent('Форма отмены подписки не найдена на странице, создаю ссылку-кнопку');

        // Создаем контейнер для центрирования
        const centerContainer = document.createElement('div');
        centerContainer.style.cssText = 'text-align: center; margin: 30px auto; max-width: 600px;';
        mainContainer.appendChild(centerContainer);
        logEvent('Создан центрирующий контейнер');

        // Добавляем заголовок
        const header = document.createElement('h2');
        header.textContent = 'Отмена подписки WILLWAY';
        header.style.cssText = `
            text-align: center;
            margin: 30px auto 20px;
            color: #333;
            font-size: 28px;
            font-weight: bold;
        `;
        centerContainer.appendChild(header);
        logEvent('Добавлен заголовок');

        // Создаем поясняющий текст
        const infoText = document.createElement('p');
        infoText.textContent = 'Нажмите кнопку, чтобы отменить вашу подписку. После отмены вы сохраните доступ до конца оплаченного периода.';
        infoText.style.cssText = `
            text-align: center;
            margin: 10px auto 30px;
            color: #555;
            font-size: 16px;
            line-height: 1.5;
        `;
        centerContainer.appendChild(infoText);
        logEvent('Добавлен информационный текст');

        // Создаем прямую ссылку на API вместо JavaScript-обработчика
        // Формируем URL с параметрами для прямого запроса
        const directCancelUrl = `https://api-willway.ru/api/v1/subscription/cancel?user_id=${userId}&status=cancelled&source=web_direct&timestamp=${encodeURIComponent(new Date().toISOString())}`;

        // Создаем ссылку-кнопку отмены подписки
        const cancelLink = document.createElement('a');
        cancelLink.textContent = 'Отменить подписку';
        cancelLink.href = directCancelUrl; // Прямая ссылка на API
        cancelLink.target = "_blank"; // Открываем в новой вкладке
        cancelLink.id = 'cancel-subscription-button';
        cancelLink.className = 'cancel-subscription-button';
        cancelLink.setAttribute('data-action', 'cancel-subscription');
        cancelLink.setAttribute('data-user-id', userId);
        cancelLink.style.cssText = `
            display: inline-block;
            margin: 20px auto;
            padding: 15px 30px;
            background-color: #dc3545;
            color: white !important;
            text-decoration: none;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.3s;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            -webkit-appearance: none;
            -moz-appearance: none;
            appearance: none;
        `;
        logEvent('Создана кнопка отмены подписки как прямая ссылка на API', { url: directCancelUrl });

        // Добавляем эффект при наведении
        cancelLink.onmouseover = function () {
            this.style.backgroundColor = '#c82333';
            this.style.color = 'white';
            logEvent('Наведение на кнопку отмены подписки');
        };
        cancelLink.onmouseout = function () {
            this.style.backgroundColor = '#dc3545';
            this.style.color = 'white';
        };

        // Добавляем обработчик клика (для логирования)
        cancelLink.addEventListener('click', function (event) {
            logEvent('КЛИК: Кнопка отмены подписки нажата (прямая ссылка)', { userId: userId, url: directCancelUrl });

            // Показываем сообщение об успешной отмене
            // Небольшая задержка, чтобы пользователь успел увидеть сообщение
            setTimeout(function () {
                showConfirmationMessage();
            }, 500);
        });

        // Добавляем кнопку на страницу
        centerContainer.appendChild(cancelLink);
        logEvent('Кнопка отмены подписки добавлена на страницу');

        // Добавляем дополнительную текстовую инструкцию
        const noteText = document.createElement('p');
        noteText.textContent = 'Примечание: Если ссылка не работает, скопируйте и вставьте её в адресную строку браузера.';
        noteText.style.cssText = `
            text-align: center;
            margin: 15px auto;
            color: #666;
            font-size: 14px;
            font-style: italic;
        `;
        centerContainer.appendChild(noteText);

        // Добавляем текстовую копию ссылки
        const linkTextContainer = document.createElement('div');
        linkTextContainer.style.cssText = `
            text-align: center;
            margin: 10px auto;
            padding: 10px;
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            word-break: break-all;
            max-width: 500px;
        `;
        linkTextContainer.textContent = directCancelUrl;
        centerContainer.appendChild(linkTextContainer);

        // Добавляем прямое логирование в консоль для проверки
        console.log('Прямая проверка кнопки:', cancelLink);

        // Добавляем информацию о том, работает ли кнопка
        setTimeout(function () {
            logEvent('Проверка доступности кнопки после рендеринга:', {
                размещена: document.body.contains(cancelLink),
                видима: cancelLink.offsetWidth > 0 && cancelLink.offsetHeight > 0
            });
        }, 1000);
    }

    // Находим кнопку подтверждения отмены (как существующую, так и созданную выше)
    const confirmCancelButton = document.querySelector('.cancel-subscription-button, a[data-action="cancel-subscription"]');

    if (confirmCancelButton) {
        logEvent(`Кнопка отмены найдена: ${confirmCancelButton.tagName}`, {
            id: confirmCancelButton.id,
            classes: confirmCancelButton.className,
            attributes: Array.from(confirmCancelButton.attributes).map(a => `${a.name}="${a.value}"`).join(', ')
        });

        // Добавим обработчик для всех типов событий активации
        ['mousedown', 'mouseup', 'touchstart', 'touchend'].forEach(eventType => {
            confirmCancelButton.addEventListener(eventType, function (event) {
                logEvent(`Событие ${eventType} на кнопке отмены подписки`);
            });
        });
    } else {
        logEvent('ОШИБКА: Кнопка отмены подписки не найдена на странице после создания');
    }

    // Добавляем глобальный обработчик для перехвата всех кликов
    document.addEventListener('click', function (event) {
        const target = event.target;
        // Проверяем, был ли клик по кнопке отмены или ее дочернему элементу
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
    */

    // Оставляем пустую страницу, не показывая никакой информации о подписке и кнопке отмены
});

/**
 * Отправляет webhook в наш сервер об отмене подписки
 * 
 * @param {string} userId - ID пользователя Telegram
 * @param {string} status - Статус отмены подписки ('cancelled', 'pending', etc.)
 * @param {Object} [additionalData] - Дополнительные данные для отправки
 */
function sendCancellationWebhook(userId, status, additionalData = {}) {
    logEvent(`ЗАПРОС: Начало отправки webhook для отмены подписки пользователя: ${userId}`);

    // Используем сразу рабочий URL вместо нерабочего маршрута
    const apiUrl = 'https://api-willway.ru/api/v1/subscription/cancel';
    logEvent(`ЗАПРОС: Endpoint URL для webhook: ${apiUrl}`);

    // Формируем данные для отправки
    const webhookData = {
        user_id: userId,
        status: status,
        timestamp: new Date().toISOString(),
        source: 'web',
        ...additionalData
    };

    logEvent('ЗАПРОС: Отправляемые данные:', webhookData);

    // Отправляем POST запрос
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
                // В случае ошибки разбора JSON просто возвращаем статус
                logEvent('ОТВЕТ: Не удалось разобрать JSON, возвращаем статус');
                return { status: response.status, success: response.ok };
            });
        })
        .then(data => {
            logEvent('УСПЕХ: Webhook отправлен успешно, ответ сервера:', data);

            // Показываем сообщение пользователю
            showConfirmationMessage();
        })
        .catch(error => {
            logEvent(`ОШИБКА: При отправке webhook: ${error.message}`, {
                stack: error.stack
            });
            // Показываем сообщение об ошибке пользователю
            showConfirmationMessage('Возникла ошибка при отправке запроса. Пожалуйста, свяжитесь с поддержкой.');
        });
}

/**
 * Показывает сообщение о успешной отмене подписки
 * 
 * @param {string} [customMessage] - Пользовательское сообщение для отображения
 */
function showConfirmationMessage(customMessage) {
    logEvent('Показываем сообщение о результате: ' + (customMessage || 'успешно'));

    // Проверяем, существует ли уже элемент сообщения
    let messageElement = document.querySelector('.cancellation-confirmation-message');

    if (!messageElement) {
        // Создаем новый элемент, если он не существует
        messageElement = document.createElement('div');
        messageElement.className = 'cancellation-confirmation-message';
        messageElement.style.cssText = 'background-color: #4CAF50; color: white; padding: 15px; margin: 20px auto; border-radius: 5px; text-align: center; max-width: 600px; font-weight: bold; z-index: 9999;';

        // Находим форму или другой подходящий контейнер для вставки сообщения
        const container = document.querySelector('.form-container') ||
            document.querySelector('.t-container') ||
            document.querySelector('.tn-atom') ||
            document.querySelector('main') ||
            document.body;

        // Вставляем сообщение в начало контейнера
        container.insertBefore(messageElement, container.firstChild);
        logEvent('Создан элемент сообщения');
    }

    // Устанавливаем текст сообщения
    messageElement.textContent = customMessage || 'Ваша подписка успешно отменена. Уведомление отправлено в Telegram.';

    // Если это сообщение об ошибке, меняем цвет на красный
    if (customMessage && customMessage.includes('ошибка')) {
        messageElement.style.backgroundColor = '#dc3545';
    }

    // Прокручиваем страницу к сообщению
    messageElement.scrollIntoView({ behavior: 'smooth' });
    logEvent('Страница прокручена к сообщению');

    // Скрываем кнопку отмены подписки
    const cancelButton = document.querySelector('.cancel-subscription-button, a[data-action="cancel-subscription"]');
    if (cancelButton) {
        cancelButton.style.display = 'none';
        logEvent('Кнопка отмены подписки скрыта');
    }
} 