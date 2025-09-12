from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, Index, DateTime
from datetime import datetime

metadata = MetaData()

# Users table with an index on "name"
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("age", Integer),
    Column("created_at", DateTime, default=datetime.now)
)
Index("idx_users_name", users.c.name)

# Posts table
posts = Table(
    "posts", metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(200)),
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("created_at", DateTime, default=datetime.now),
    Column("test_col_1", String(200))
)
