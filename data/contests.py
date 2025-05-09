import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm
from sqlalchemy_serializer import SerializerMixin


class Contest(SqlAlchemyBase, SerializerMixin):
    __tablename__ = "contests"

    cid = sqlalchemy.Column(sqlalchemy.Integer, autoincrement=True, primary_key=True)
    title = sqlalchemy.Column(sqlalchemy.String)
    start_time = sqlalchemy.Column(sqlalchemy.DateTime)
    end_time = sqlalchemy.Column(sqlalchemy.DateTime)

    news = orm.relationship("News", back_populates="contest")

    tasks = orm.relationship("Task", back_populates="contest")
    submissions = orm.relationship("Submission", back_populates="contest")