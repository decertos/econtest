import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy_serializer import SerializerMixin
from functools import lru_cache
from sqlalchemy import orm
import json


class Task(SqlAlchemyBase, SerializerMixin):
    __tablename__ = "tasks"

    tid = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True, index=True)
    title = sqlalchemy.Column(sqlalchemy.String)
    statement = sqlalchemy.Column(sqlalchemy.String)
    input_spec = sqlalchemy.Column(sqlalchemy.String)
    output_spec = sqlalchemy.Column(sqlalchemy.String)
    test_cases = sqlalchemy.Column(sqlalchemy.String, default="")
    time_limit = sqlalchemy.Column(sqlalchemy.Integer, default=1)
    memory_limit = sqlalchemy.Column(sqlalchemy.Integer, default=256)
    mode = sqlalchemy.Column(sqlalchemy.Integer, default=0)

    scoring = sqlalchemy.Column(sqlalchemy.String, default='{"scoring":[]}')

    submissions = orm.relationship("Submission", back_populates="task")

    contest_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contests.cid"))
    contest = orm.relationship("Contest")

    points = sqlalchemy.Column(sqlalchemy.Float, default=0)
    solved_count = sqlalchemy.Column(sqlalchemy.Integer, default=0)

    @lru_cache(maxsize=32)
    def get_test_cases(self):
        return json.loads(self.test_cases)

    @lru_cache(maxsize=32)
    def get_scoring(self):
        return json.loads(self.scoring)["scoring"]