import os
from peewee import SqliteDatabase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


db = SqliteDatabase(
    os.path.join(BASE_DIR, "invoice.db"),
    pragmas={"foreign_keys": 1},
)
