/**
 * WILLWAY Payment Success Tracker
 * Этот скрипт отслеживает успешную оплату и отправляет информацию на сервер
 * Для подключения на странице Tilda, добавьте следующий код в раздел HEAD:
 * <script src="https://api-willway.ru/static/js/tilda-success.js"></script>
 */

(function () {
    const API_URL = 'https://api-willway.ru/api/v1/payment/success';

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

    function addReturnToTelegramButton(userId) {
        if (document.querySelector('.return-to-bot')) {
            console.log('Кнопка возврата уже существует');
            return;
        }

        const container = document.querySelector('.t-container') || document.querySelector('body');
        if (container) {
            const botUsername = window.BOT_USERNAME || 'willwayapp_bot';

            const button = document.createElement('div');
            button.className = 'return-to-bot';
            button.innerHTML = '<a href="https://t.me/' + botUsername + '?start=payment_success_' + userId + '" class="telegram-button">Вернуться в бот</a>';
            button.style.textAlign = 'center';
            button.style.margin = '30px auto';
            button.style.fontSize = '18px';

            if (container.firstChild) {
                container.insertBefore(button, container.firstChild);
            } else {
                container.appendChild(button);
            }

            console.log('Кнопка возврата в бот добавлена');
        }
    }

    function trackSuccessfulPayment() {
        const urlParams = getURLParams();
        const localData = getLocalStorageData();

        const userId = urlParams.tgid || (localData ? localData.user_id : null);
        const subscriptionType = urlParams.subscription_type || 'monthly';

        const monthlyPrice = 1555;
        const yearlyPrice = 13333;

        const amount = subscriptionType === 'yearly' ? yearlyPrice : monthlyPrice;

        if (!userId) {
            console.log('ID пользователя Telegram не найден в URL или localStorage');
            return;
        }

        console.log('Отправка данных об успешной оплате для пользователя:', userId);
        console.log('API URL:', API_URL);

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

                addReturnToTelegramButton(userId);

                setTimeout(() => {
                    const botUsername = window.BOT_USERNAME || 'willwayapp_bot';
                    window.location.href = `https://t.me/${botUsername}?start=payment_success_${userId}`;
                }, 5000);
            })
            .catch(error => {
                console.error('Ошибка при отправке данных об успешной оплате:', error);

                addReturnToTelegramButton(userId);
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        console.log('Страница успешной оплаты загружена');
        trackSuccessfulPayment();
    });

})(); 