import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy import orm
import json


class Task(SqlAlchemyBase, SerializerMixin):
    __tablename__ = "tasks"

    tid = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    title = sqlalchemy.Column(sqlalchemy.String)
    statement = sqlalchemy.Column(sqlalchemy.String)
    input_spec = sqlalchemy.Column(sqlalchemy.String)
    output_spec = sqlalchemy.Column(sqlalchemy.String)
    test_cases = sqlalchemy.Column(sqlalchemy.String, default="")
    time_limit = sqlalchemy.Column(sqlalchemy.Integer, default=1)
    memory_limit = sqlalchemy.Column(sqlalchemy.Integer, default=256)
    mode = sqlalchemy.Column(sqlalchemy.Integer, default=0)

    submissions = orm.relationship("Submission", back_populates="task")

    contest_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contests.cid"))
    contest = orm.relationship("Contest")

    def get_test_cases(self):
        return json.loads(self.test_cases)