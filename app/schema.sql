-- Runs at app start-up. IF NOT EXISTS makes it safe to run every time.

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(30)  NOT NULL UNIQUE,
    password_hash TEXT         NOT NULL,          -- never the plain password
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(100) NOT NULL,
    content     TEXT         NOT NULL DEFAULT '',
    category    VARCHAR(20)  NOT NULL DEFAULT 'Other'
                CHECK (category IN ('Work', 'Study', 'Personal', 'Other')),
    priority    VARCHAR(10)  NOT NULL DEFAULT 'Medium'
                CHECK (priority IN ('High', 'Medium', 'Low')),
    pinned      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP
);

-- Every page filters notes by user, so index that column
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes (user_id);
