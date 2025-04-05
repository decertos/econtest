import sqlalchemy
from .db_session import SqlAlchemyBase
import datetime
from sqlalchemy import orm


class Submission(SqlAlchemyBase):
    __tablename__ = "submissions"

    s_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    language = sqlalchemy.Column(sqlalchemy.String, default="py")
    verdict = sqlalchemy.Column(sqlalchemy.String, default="qu")

    code = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    time = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now)
    execution_time = sqlalchemy.Column(sqlalchemy.Integer, default=0)

    uid = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.uid"))
    user = orm.relationship("User")

    tid = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("tasks.tid"))
    task = orm.relationship("Task")

    cid = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("contests.cid"))
    contest = orm.relationship("Contest")

    verdicts = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    points = sqlalchemy.Column(sqlalchemy.REAL, nullable=True)

