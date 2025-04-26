/**
 * WILLWAY Payment Success Tracker
 * Этот скрипт отслеживает успешную оплату и отправляет информацию на сервер
 * Для подключения на странице Tilda, добавьте следующий код в раздел HEAD:
 * <script src="https://api-willway.ru/static/js/tilda-success.js"></script>
 */

(function () {
    // Определяем URL API сервера
    const API_URL = 'https://api-willway.ru/api/v1/payment/success';
    const BOT_USERNAME = 'willway_super_bot';

    // Функция для получения данных из localStorage
    function getLocalStorageData() {
        try {
            const userId = localStorage.getItem('willway_user_id');
            if (userId) {
                return { user_id: parseInt(userId, 10) };
            }
            return null;
        } catch (error) {
            console.error('Ошибка при получении данных из localStorage:', error);
            return null;
        }
    }

    // Функция для получения параметров из URL
    function getURLParams() {
        const params = {};
        const queryString = window.location.search.substring(1);
        const pairs = queryString.split('&');

        for (let i = 0; i < pairs.length; i++) {
            const pair = pairs[i].split('=');
            params[decodeURIComponent(pair[0])] = decodeURIComponent(pair[1] || '');
        }

        return params;
    }

    // Добавление кнопки для возврата в Telegram
    function addReturnToTelegramButton(userId) {
        // Проверяем существование кнопки
        if (document.querySelector('.return-to-bot')) {
            console.log('Кнопка возврата уже существует');
            return;
        }

        // Добавляем кнопку для возврата в бот
        const container = document.querySelector('.t-container') || document.querySelector('body');
        if (container) {
            const button = document.createElement('div');
            button.className = 'return-to-bot';
            button.innerHTML = '<a href="https://t.me/' + BOT_USERNAME + '?start=payment_success_' + userId + '" class="telegram-button">Вернуться в бот</a>';
            button.style.textAlign = 'center';
            button.style.margin = '30px auto';
            button.style.fontSize = '18px';
            container.appendChild(button);

            console.log('Кнопка возврата в бот добавлена');
        }
    }

    // Функция для отслеживания успешной оплаты
    function trackSuccessfulPayment() {
        // Получаем параметры из URL
        const urlParams = getURLParams();
        // Получаем данные из localStorage
        const localData = getLocalStorageData();

        // Определяем user_id из параметров URL или localStorage
        const userId = urlParams.tgid || (localData ? localData.user_id : null);
        const subscriptionType = urlParams.subscription_type || 'monthly';
        const amount = urlParams.amount || (subscriptionType === 'monthly' ? 1555 : 13333);

        // Если user_id не найден, прекращаем выполнение
        if (!userId) {
            console.log('User ID не найден в URL или localStorage');
            return;
        }

        console.log('Отправка данных об успешной оплате для пользователя:', userId);

        // Отправляем данные на сервер
        fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: parseInt(userId, 10),
                subscription_type: subscriptionType,
                amount: amount,
                timestamp: new Date().toISOString(),
                url: window.location.href,
                page: 'success'
            })
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Ошибка при отправке данных: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log('Данные об успешной оплате отправлены на сервер:', data);

                // Добавляем кнопку для возврата в бот и выделяем её
                addReturnToTelegramButton(userId);

                // Автоматический переход в бот через 5 секунд
                setTimeout(() => {
                    window.location.href = `https://t.me/${BOT_USERNAME}?start=payment_success_${userId}`;
                }, 5000);
            })
            .catch(error => {
                console.error('Ошибка при отправке данных об успешной оплате:', error);
                // Всё равно добавляем кнопку для возврата в бот
                addReturnToTelegramButton(userId);
            });
    }

    // Запускаем отслеживание при загрузке страницы
    document.addEventListener('DOMContentLoaded', function () {
        console.log('Страница успешной оплаты загружена');
        trackSuccessfulPayment();
    });

})(); 