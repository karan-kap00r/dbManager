from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, Index

metadata = MetaData()

# Users table with an index on "name"
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("age", Integer),
)
Index("idx_users_name", users.c.name)

# Posts table
posts = Table(
    "posts", metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(200)),
    Column("user_id", Integer, ForeignKey("users.id")),
)
