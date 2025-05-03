-- SQL скрипт для добавления новых колонок в таблицу users
-- Выполните этот скрипт с помощью SQLite в случае, если автоматическая миграция не сработает
-- Пример запуска: sqlite3 database.db < add_columns.sql

-- Добавление колонок для хранения информации о сомнениях пользователя
ALTER TABLE users ADD COLUMN subscription_doubt_status TEXT;
ALTER TABLE users ADD COLUMN subscription_doubt_response TEXT;
ALTER TABLE users ADD COLUMN subscription_doubt_feedback TEXT; 