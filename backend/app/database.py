"""数据库连接"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from .models import db_models

    migrate_sqlite_community_schema()
    Base.metadata.create_all(bind=engine)
    sync_sqlite_schema()
    sync_conversation_schema()


def migrate_sqlite_community_schema():
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "community_places" not in inspector.get_table_names():
        return
    favorite_columns = {column["name"] for column in inspector.get_columns("place_favorites")}
    if "poi_id" in favorite_columns:
        return
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("ALTER TABLE place_favorites RENAME TO place_favorites_legacy"))
        conn.execute(text("ALTER TABLE place_checkins RENAME TO place_checkins_legacy"))
        conn.execute(text("ALTER TABLE place_reviews RENAME TO place_reviews_legacy"))
        conn.execute(text("ALTER TABLE place_posts RENAME TO place_posts_legacy"))
        conn.execute(text("CREATE TABLE place_favorites (id INTEGER PRIMARY KEY, poi_id VARCHAR(100) NOT NULL, user_id INTEGER NOT NULL, created_at DATETIME, CONSTRAINT uq_place_favorite_user UNIQUE (poi_id, user_id), FOREIGN KEY(user_id) REFERENCES users (id))"))
        conn.execute(text("CREATE TABLE place_checkins (id INTEGER PRIMARY KEY, poi_id VARCHAR(100) NOT NULL, user_id INTEGER NOT NULL, note TEXT, created_at DATETIME, updated_at DATETIME, CONSTRAINT uq_place_checkin_user UNIQUE (poi_id, user_id), FOREIGN KEY(user_id) REFERENCES users (id))"))
        conn.execute(text("CREATE TABLE place_reviews (id INTEGER PRIMARY KEY, poi_id VARCHAR(100) NOT NULL, user_id INTEGER NOT NULL, rating INTEGER NOT NULL, content TEXT, created_at DATETIME, updated_at DATETIME, CONSTRAINT uq_place_review_user UNIQUE (poi_id, user_id), FOREIGN KEY(user_id) REFERENCES users (id))"))
        conn.execute(text("CREATE TABLE place_posts (id INTEGER PRIMARY KEY, poi_id VARCHAR(100), user_id INTEGER NOT NULL, content TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'approved', created_at DATETIME, updated_at DATETIME, FOREIGN KEY(user_id) REFERENCES users (id))"))
        conn.execute(text("INSERT INTO place_favorites (id, poi_id, user_id, created_at) SELECT f.id, p.poi_id, f.user_id, f.created_at FROM place_favorites_legacy f JOIN community_places p ON p.id = f.place_id"))
        conn.execute(text("INSERT INTO place_checkins (id, poi_id, user_id, note, created_at, updated_at) SELECT c.id, p.poi_id, c.user_id, c.note, c.created_at, c.created_at FROM place_checkins_legacy c JOIN community_places p ON p.id = c.place_id"))
        conn.execute(text("INSERT INTO place_reviews (id, poi_id, user_id, rating, content, created_at, updated_at) SELECT r.id, p.poi_id, r.user_id, r.rating, r.content, r.created_at, r.updated_at FROM place_reviews_legacy r JOIN community_places p ON p.id = r.place_id"))
        conn.execute(text("INSERT INTO place_posts (id, poi_id, user_id, content, status, created_at, updated_at) SELECT s.id, p.poi_id, s.user_id, s.content, 'approved', s.created_at, s.created_at FROM place_posts_legacy s JOIN community_places p ON p.id = s.place_id"))
        conn.execute(text("DROP TABLE place_favorites_legacy"))
        conn.execute(text("DROP TABLE place_checkins_legacy"))
        conn.execute(text("DROP TABLE place_reviews_legacy"))
        conn.execute(text("DROP TABLE place_posts_legacy"))
        conn.execute(text("DROP TABLE community_places"))
        conn.execute(text("PRAGMA foreign_keys=ON"))


def sync_sqlite_schema():
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"))


def sync_conversation_schema():
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "conversation_messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("conversation_messages")}
    additions = {
        "task_status": "VARCHAR(20) NOT NULL DEFAULT 'completed'",
        "task_steps_json": "TEXT NOT NULL DEFAULT '[]'",
        "error_message": "TEXT NOT NULL DEFAULT ''",
        "duration_ms": "INTEGER NOT NULL DEFAULT 0"
    }
    with engine.begin() as conn:
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE conversation_messages ADD COLUMN {name} {definition}"))

    # conversations 表添加对话摘要字段
    if "conversations" in inspector.get_table_names():
        conv_columns = {column["name"] for column in inspector.get_columns("conversations")}
        conv_additions = {
            "summary": "TEXT NOT NULL DEFAULT ''",
            "summarized_message_count": "INTEGER NOT NULL DEFAULT 0",
        }
        with engine.begin() as conn:
            for name, definition in conv_additions.items():
                if name not in conv_columns:
                    conn.execute(text(f"ALTER TABLE conversations ADD COLUMN {name} {definition}"))
