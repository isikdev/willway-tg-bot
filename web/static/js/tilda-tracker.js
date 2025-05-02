/**
 * WILLWAY Payment Tracker
 * Этот скрипт отслеживает переходы на страницу оплаты и отправляет данные на сервер
 * Для подключения на странице Tilda, добавьте следующий код в раздел HEAD:
 * <script src="https://api-willway.ru/static/js/tilda-tracker.js"></script>
 */

(function () {
    const API_URL = 'https://api-willway.ru/api/v1/payment/track';
    const PAYMENT_CHECK_URL = 'https://api-willway.ru/api/v1/payment/check';

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

    function setLocalStorageData(data) {
        try {
            if (data.user_id) {
                localStorage.setItem('willway_user_id', data.user_id.toString());
            }
        } catch (error) {
            console.error('Ошибка при записи в localStorage:', error);
        }
    }

    function trackPaymentPage() {
        const urlParams = getURLParams();
        const localData = getLocalStorageData();

        const userId = urlParams.tgid || (localData ? localData.user_id : null);

        if (!userId) {
            console.log('ID пользователя Telegram не найден в URL или localStorage');
            return;
        }

        setLocalStorageData({ user_id: userId });

        console.log('Отслеживание страницы оплаты для пользователя:', userId);
        console.log('API URL:', API_URL);

        fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: parseInt(userId, 10),
                page: 'payment',
                timestamp: new Date().toISOString(),
                referrer: document.referrer,
                url: window.location.href
            })
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Ошибка при отправке данных: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log('Данные успешно отправлены на сервер:', data);

                setTimeout(() => {
                    checkPaymentStatus(userId);
                }, 20000); // 20 секунд
            })
            .catch(error => {
                console.error('Ошибка при отправке данных:', error);
            });
    }

    function checkPaymentStatus(userId) {
        console.log('Проверка статуса оплаты для пользователя:', userId);
        console.log('API URL для проверки:', PAYMENT_CHECK_URL);

        fetch(PAYMENT_CHECK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: parseInt(userId, 10),
                timestamp: new Date().toISOString()
            })
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Ошибка при проверке статуса: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                console.log('Результат проверки статуса оплаты:', data);
            })
            .catch(error => {
                console.error('Ошибка при проверке статуса оплаты:', error);
            });
    }

    document.addEventListener('DOMContentLoaded', trackPaymentPage);
})();


