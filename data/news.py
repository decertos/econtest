import datetime

import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm
from sqlalchemy_serializer import SerializerMixin


class News(SqlAlchemyBase, SerializerMixin):
    __tablename__ = "news"

    nid = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    title = sqlalchemy.Column(sqlalchemy.String)
    author = sqlalchemy.Column(sqlalchemy.String)
    date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now())
    content = sqlalchemy.Column(sqlalchemy.String)
    edited = sqlalchemy.Column(sqlalchemy.Boolean, default=False)

    cid = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contests.cid"))
    contest = orm.relationship("Contest")