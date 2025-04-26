/**
 * WILLWAY Payment Tracker
 * Этот скрипт отслеживает переходы на страницу оплаты и отправляет данные на сервер
 * Для подключения на странице Tilda, добавьте следующий код в раздел HEAD:
 * <script src="https://api-willway.ru/static/js/tilda-tracker.js"></script>
 */

(function () {
    // Определяем URL API сервера
    const API_URL = 'https://api-willway.ru/api/v1/payment/track';
    const PAYMENT_CHECK_URL = 'https://api-willway.ru/api/v1/payment/check';

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

    // Функция для записи данных в localStorage
    function setLocalStorageData(data) {
        try {
            if (data.user_id) {
                localStorage.setItem('willway_user_id', data.user_id.toString());
            }
        } catch (error) {
            console.error('Ошибка при записи в localStorage:', error);
        }
    }

    // Функция для отслеживания посещения страницы оплаты
    function trackPaymentPage() {
        // Получаем параметры из URL
        const urlParams = getURLParams();
        // Получаем данные из localStorage
        const localData = getLocalStorageData();

        // Определяем user_id из параметров URL или localStorage
        const userId = urlParams.user_id || (localData ? localData.user_id : null);

        // Если user_id не найден, прекращаем выполнение
        if (!userId) {
            console.log('User ID не найден в URL или localStorage');
            return;
        }

        // Сохраняем user_id в localStorage для использования на странице успешной оплаты
        setLocalStorageData({ user_id: userId });

        // Отправляем данные на сервер
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
            .then(response => response.json())
            .then(data => {
                console.log('Данные успешно отправлены на сервер:', data);

                // Запускаем таймер для проверки статуса оплаты через 20 секунд
                setTimeout(() => {
                    checkPaymentStatus(userId);
                }, 20000); // 20 секунд
            })
            .catch(error => {
                console.error('Ошибка при отправке данных:', error);
            });
    }

    // Функция для проверки статуса оплаты
    function checkPaymentStatus(userId) {
        // Отправляем запрос на сервер для проверки статуса
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
            .then(response => response.json())
            .then(data => {
                console.log('Результат проверки статуса оплаты:', data);
                // Если сервер вернул успешный ответ, но пользователь не подписан,
                // автоматически будет отправлено сообщение через бота
            })
            .catch(error => {
                console.error('Ошибка при проверке статуса оплаты:', error);
            });
    }

    // Запускаем отслеживание при загрузке страницы
    document.addEventListener('DOMContentLoaded', trackPaymentPage);
})();


