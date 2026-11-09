CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    telegram_bot_token TEXT,
    telegram_chat_id TEXT,
    downloads INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
