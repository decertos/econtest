import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy_serializer import SerializerMixin
from flask_login import UserMixin
from werkzeug.security import check_password_hash
from sqlalchemy import orm


class User(SqlAlchemyBase, UserMixin, SerializerMixin):
    __tablename__ = "users"

    uid = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True, index=True)
    login = sqlalchemy.Column(sqlalchemy.String, unique=True, index=True)
    password = sqlalchemy.Column(sqlalchemy.String)
    is_admin = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    banned = sqlalchemy.Column(sqlalchemy.String, default="")
    submissions = orm.relationship("Submission", back_populates="user")

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_id(self):
        return self.uid