from flask import abort, Flask, redirect, render_template, request, jsonify
import flask

from data import db_session
from data.users import User
from data.submissions import Submission
from data.tasks import Task
from data.contests import Contest
from data.news import News

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FileField, SelectField, \
    DateTimeField
from wtforms.validators import EqualTo, DataRequired

from flask_login import LoginManager, current_user, login_user, logout_user, login_required

from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from collections import deque
import subprocess
import threading
import datetime
from zipfile import ZipFile
from random import randint
import time
import json
import sys
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import logging


MODE_FULL_CHECK = 0
MODE_PARTIAL_CHECK = 1


class Checker:
    def __init__(self):
        self.queue = deque()
        self.MAX_THREADS_COUNT = 2
        self.threads_count = 0

    def check_ended(self, submission_id, verdicts, max_execution_time, verdict):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        submission.verdict = verdict
        submission.verdicts = json.dumps(verdicts)
        submission.execution_time = max_execution_time
        db_sess.commit()
        if submission.language.startswith("py"):
            run_file = f"submissions/check{submission_id}.py"
            os.remove(run_file)
        elif submission.language == "cpp":
            if not verdict[:2] == "ce":
                run_file = f"submissions/check-cpp{submission_id}.exe"
                os.remove(run_file)
            run_file = f"submissions/check{submission_id}.cpp"
            os.remove(run_file)
        db_sess.close()

        self.threads_count -= 1

        if len(self.queue) > 0:
            self.run_check(self.queue[0])

    def check(self, code, language, submission_id):
        self.queue.popleft()
        # Получение тестов
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        test_cases = submission.task.get_test_cases()
        time_limit = submission.task.time_limit
        mode = submission.task.mode
        db_sess.close()

        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        verdicts = {i + 1: ("ig", 0) for i in range(len(test_cases))}
        submission.verdicts = json.dumps(verdicts)
        submission.points = 0
        db_sess.commit()
        db_sess.close()

        # Подготовка к подсчёту баллов
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        task = submission.task
        scoring = task.get_scoring()
        tests_points = [0 for i in range(len(test_cases))]
        for i in range(len(scoring)):
            test_points = scoring[i]["points"] / len(scoring[i]["required_tests"])
            for j in scoring[i]["required_tests"]:
                tests_points[int(j) - 1] = test_points
        points = 0

        check_code = " ".join(code.split(" "))
        if "import os" in check_code or "import subprocess" in check_code or "system" in check_code or "db_session" in check_code:
            verdicts["1"] = (
                "ce", 0, "restricted words. do not use import os, subprocess or anything to hack the testing system")
            self.check_ended(submission_id, verdicts, 0, "ce")
        # Подготовка к запуску
        code_language = language
        if language.startswith("py"):
            code_language = "py"
        elif language == "cpp":
            code_language = "cpp"
        with open(f"submissions/check{submission_id}.{code_language}", "w", encoding="UTF-8") as f:
            f.write(code)

        commands = []
        if language == "py3102":
            commands = ["python", f"submissions/check{submission_id}.py"]
        elif language == "py3123":
            commands = ["py", f"submissions/check{submission_id}.py"]
        elif language == "cpp":
            db_sess = db_session.create_session()
            submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
            submission.verdict = "co 0"
            verdicts["0"] = ("co", 0)
            submission.verdicts = json.dumps(verdicts)
            db_sess.commit()

            compile_process = subprocess.run(
                ["g++", f"check{submission_id}.{language}", "-o", f"submissions/check-cpp{submission_id}.exe", "-std=c++23"],
                stderr=subprocess.PIPE)
            if compile_process.returncode != 0:
                verdicts["1"] = ("ce", 0, str(compile_process.stderr))
                self.check_ended(submission_id, verdicts, 0, "ce")
                return
            verdicts["0"] = ("ok", 0)
            submission.verdicts = json.dumps(verdicts)
            db_sess.commit()
            db_sess.close()
            commands = [f"check-cpp{submission_id}.exe"]
        # Проверка на тестах
        max_execution_time = 0
        for index, test in enumerate(test_cases, start=1):
            i = str(index)
            db_sess = db_session.create_session()
            submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
            submission.verdict = f"te {i}"
            db_sess.commit()
            db_sess.close()

            t0 = time.time()
            in_data, out_data = test

            try:
                program_output = subprocess.check_output(commands,
                                                         input=in_data,
                                                         text=True,
                                                         timeout=time_limit,
                                                         stderr=subprocess.STDOUT).strip()
                max_execution_time = max(max_execution_time, self.get_time(t0))
                if program_output.strip().rstrip() != out_data:
                    verdicts[i] = ["wa", self.get_time(t0)]
                    if mode == MODE_FULL_CHECK:
                        self.check_ended(submission_id, verdicts, max_execution_time, f"wa {i}")
                        return
                    continue
            except subprocess.TimeoutExpired:
                max_execution_time = max(max_execution_time, self.get_time(t0))
                verdicts[i] = ("tl", self.get_time(t0))
                if mode == MODE_FULL_CHECK:
                    self.check_ended(submission_id, verdicts, max_execution_time, f"tl {i}")
                    return
                continue
            except Exception as e:
                max_execution_time = max(max_execution_time, self.get_time(t0))
                if index == 1:
                    verdicts[i] = ("re", self.get_time(t0), e.output)
                else:
                    verdicts[i] = ("re", self.get_time(t0))
                if mode == MODE_FULL_CHECK:
                    self.check_ended(submission_id, verdicts, max_execution_time, f"re {i}")
                    return
                continue
            max_execution_time = max(max_execution_time, self.get_time(t0))
            verdicts[int(i)] = ("ok", self.get_time(t0))
            points += tests_points[int(i) - 1]
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        if mode == MODE_PARTIAL_CHECK:
            if all(verdicts[i][0] == "ok" for i in range(1, len(test_cases) + 1)):
                submission.points = submission.task.points
        else:
            points = submission.task.points
        submission.points = round(points, 2)
        db_sess.commit()
        db_sess.close()

        if mode == MODE_PARTIAL_CHECK and points != 100:
            passed = 0
            for i in range(1, len(test_cases) + 1):
                if verdicts[i][0] == "ok":
                    passed += 1
            self.check_ended(submission_id, verdicts, max_execution_time, f"ps {passed}")
        else:
            self.check_ended(submission_id, verdicts, max_execution_time, f"ok")

    def get_time(self, t0):
        return round((time.time() - t0) * 1000)

    def run_check(self, submission_id):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        if self.threads_count < self.MAX_THREADS_COUNT:
            code, language = submission.code, submission.language
            thread = threading.Thread(target=self.check, args=(code, language, submission_id))
            thread.start()
            self.threads_count += 1
        db_sess.close()

    def add_submission(self, submission_id):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        if submission.language not in {"py3102", "py3123", "cpp"}:
            db_sess.close()
            return
        db_sess.close()
        self.queue.append(submission_id)
        self.run_check(submission_id)


app = Flask(__name__)
app.config["SECRET_KEY"] = "301f9c4c690b99e45d0e9504f3656d654a2710c549428e601e609cddf2614ef5"
login_manager = LoginManager()
login_manager.init_app(app)

limiter = Limiter(
    get_remote_address,
    app=app
)

checker = Checker()

blueprint = flask.Blueprint("econtest_api", __name__, template_folder="templates")


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    ans = db_sess.query(User).get(user_id)
    db_sess.close()
    return ans


class LoginForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(message="Это обязательное поле.")])
    password = PasswordField("Пароль", validators=[DataRequired(message="Это обязательное поле.")])
    remember_me = BooleanField("Не выходить")
    submit = SubmitField("Войти")


class RegisterForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(message="Это обязательное поле.")])
    password = PasswordField("Пароль", validators=[DataRequired(message="Это обязательное поле.")])
    password_again = PasswordField("Пароль ещё раз", validators=[DataRequired(message="Это обязательное поле."),
                                                                 EqualTo("password",
                                                                         message="Пароли должны совпадать")])
    submit = SubmitField("Зарегистрироваться")


class SubmissionForm(FlaskForm):
    task = StringField("Задача", validators=[DataRequired("Это обязательное поле.")])
    language = SelectField("Язык", choices=[("py3102", "Python 3.10.2"), ("py3123", "Python 3.12.3"),
                                            ("cpp", "GNU G++23 (64 bit, msys2)")])
    code = TextAreaField("Код", validators=[DataRequired("Это обязательное поле.")])
    submit = SubmitField("Отправить")


class TaskEditForm(FlaskForm):
    title = StringField("Название")
    statement = TextAreaField("Условие")
    in_data = TextAreaField("Формат входных данных")
    out_data = TextAreaField("Формат выходных данных")
    time_limit = StringField("Ограничение по времени исполнения")
    memory_limit = StringField("Ограничение по памяти")
    contest = StringField("ID контеста")
    mode = BooleanField("Частичное оценивание")
    submit1 = SubmitField("Сохранить")


class TestDeleteForm(FlaskForm):
    submit = SubmitField("Удалить")


class TaskDeleteForm(FlaskForm):
    title = StringField("Название")
    submit2 = SubmitField("Удалить")


class AddContestForm(FlaskForm):
    submit = SubmitField("Добавить контест")


class ContestEditForm(FlaskForm):
    title = StringField("Название")
    start_time = DateTimeField("Дата начала")
    end_time = DateTimeField("Дата конца")
    submit1 = SubmitField("Сохранить")


class ContestDeleteForm(FlaskForm):
    title = StringField("Название контеста")
    submit2 = SubmitField("Удалить")


class NewsEditForm(FlaskForm):
    title = StringField("Заголовок")
    author = StringField("Автор")
    content = StringField("Содержание")
    cid = StringField("ID контеста")
    submit1 = SubmitField("Сохранить")


class NewsCreateForm(FlaskForm):
    submit = SubmitField("Добавить новость")


class NewsDeleteForm(FlaskForm):
    submit2 = SubmitField("Удалить")


class GroupAddForm(FlaskForm):
    submit = SubmitField("Добавить группу")


class GroupEditForm(FlaskForm):
    points = StringField("Баллы")
    tests = TextAreaField("Тесты")
    submit1 = SubmitField("Сохранить")


class GroupDeleteForm(FlaskForm):
    submit2 = SubmitField("Удалить")


class ManualTestForm(FlaskForm):
    in_data = TextAreaField("Входные данные")
    out_data = TextAreaField("Выходные данные")
    submit = SubmitField("Отправить")


class ArchiveTestForm(FlaskForm):
    archive = FileField("Файл архива")
    submit = SubmitField("Отправить")


class EditTestForm(FlaskForm):
    in_data = TextAreaField("Входные данные")
    out_data = TextAreaField("Выходные данные")
    delete = BooleanField("Удалить задачу", default=False)
    submit = SubmitField("Отправить")


class AddTaskForm(FlaskForm):
    submit = SubmitField("Добавить задачу")


@app.route("/")
@app.route("/index")
def main_page():
    return redirect("/contests")


CODES = {"404 Not Found": ("404 Не найдено", "Запрашиваемый URL-адрес не был найден на сервере.",
                           "Запрашиваемый URL-адрес не был найден на сервере. Если Вы ввели URL-адрес вручную, проверьте свое правописание и попробуйте еще раз."),
         "401 Unauthorized": ("401 Не авторизован",
                              "Сервер не смог убедиться, что Вам разрешено получить доступ к запрашиваемому URL-адресу",
                              "Сервер не смог убедиться, что Вам разрешено получить доступ к запрошенному URL-адресу. Вы либо предоставили неправильные учетные данные (например, неправильный пароль), либо Ваш браузер не понимает, как предоставить необходимые учетные данные."),
         "403 Forbidden": ("403 Доступ запрещён", "У вас нет разрешения на доступ к запрошенному ресурсу",
                           "У вас нет разрешения на доступ к запрошенному ресурсу. Он либо защищен от чтения, либо не читается сервером."),
         "500 Internal Server Error": (
             "500 Внутренняя ошибка сервера",
             "На сервере произошла внутренняя ошибка и не удалось выполнить ваш запрос.",
             "На сервере произошла внутренняя ошибка, и он не смог выполнить ваш запрос. Либо сервер перегружен, либо в приложении ошибка.")}


@app.errorhandler(HTTPException)
def error_handler(code):
    code = str(code)
    if code.startswith("401"):
        return redirect("/login")
    if code.startswith("429"):
        rate_limit = code[code.find(":") + 2:]
        return f'<p>Too many requests. Wait for a minute and try again.<br>Rate limit for this pages is {rate_limit}.</p> <p>Слишком много запросов. Подождите минуту и попробуйте ещё раз.<br>Ограничение запросов на эту страницу: {rate_limit.replace("per", "в").replace("minute", "минуту")}.</p>'
    if "/api/" in request.full_path:
        return jsonify({"status": "error", "error": code})
    if "ru" in request.accept_languages:
        title, text, text1 = CODES.get(code[:code.find(":")], (
            code[:code.find(":")], code[code.find(":") + 2:code.find(".")], code[code.find(":") + 2:]))
    else:
        title, text, text1 = code[:code.find(":")], code[code.find(":") + 2:code.find(".")], code[code.find(":") + 2:]
    return render_template("/files/server/error_handler.html", title=title, text=text, text1=text1, request=request,
                           http_code=code[:code.find(":")], now_time=datetime.datetime.now())


# API
@app.route("/api/")
def api():
    return render_template("/files/client/api.html", title="Главная страница", contest_title="EContest API",
                           now_time=datetime.datetime.now())


@blueprint.route("/api/contest/", methods=["GET", "POST"])
def api_contests():
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    contests = db_sess.query(Contest).all()
    data = {"status": "ok", "response": {}}
    for contest in contests:
        data["response"][str(contest.cid)] = contest.to_dict(only=("cid", "title", "start_time", "end_time"))
    db_sess.close()
    return jsonify(data)


@blueprint.route("/api/contest/<int:contest_id>/", methods=["GET", "POST"])
def api_contests_id(contest_id):
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
    if not contest:
        return jsonify({"status": "error", "error": "not found"})
    data = {}
    data["response"] = contest.to_dict(only=("cid", "title", "start_time", "end_time"))
    data["status"] = "ok"
    return jsonify(data)


@blueprint.route("/api/task/", methods=["GET", "POST"])
def api_tasks():
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    tasks = db_sess.query(Task).all()
    data = {"status": "ok", "response": {}}
    for task in tasks:
        data["response"][str(task.tid)] = task.to_dict(only=(
            "tid", "title", "statement", "input_spec", "output_spec", "time_limit", "memory_limit", "mode",
            "contest_id"))
    db_sess.close()
    return jsonify(data)


@blueprint.route("/api/task/<int:task_id>", methods=["GET", "POST"])
def api_tasks_id(task_id):
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    if not task:
        return jsonify({"status": "error", "error": "not found"})
    data = {"status": "ok", "response": task.to_dict(only=(
        "tid", "title", "statement", "input_spec", "output_spec", "time_limit", "memory_limit", "mode", "contest_id"))}
    db_sess.close()
    return data


@blueprint.route("/api/admin/task_test_cases/<int:task_id>/")
def api_admin_task_test_cases(task_id):
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"status": "error", "error": "you are not allowed to enter this resource"})
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    if not task:
        return jsonify({"status": "error", "error": "not found"})
    data = {"status": "ok", "response": task.to_dict(only=("test_cases",))}
    db_sess.close()
    return data


@blueprint.route("/api/user/")
def api_user():
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    users = db_sess.query(User).all()
    data = {"status": "ok", "response": {}}
    for user in users:
        data["response"][str(user.uid)] = user.to_dict(only=("uid", "login"))
    db_sess.close()
    return jsonify(data)


@blueprint.route("/api/user/<int:user_id>/")
def api_user_id(user_id):
    if request.method == "POST":
        return jsonify({"status": "error", "error": "method not realized"})
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.uid == user_id).first()
    if not user:
        return jsonify({"status": "error", "error": "not found"})
    data = {"status": "ok", "response": user.to_dict(only=("uid", "login"))}
    db_sess.close()
    return data


# Content Management System
@app.route("/cms/")
def cms_main_page():
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    return render_template("/cms/pages/cms_index.html", now_time=datetime.datetime.now())


@app.route("/cms/tasks/", methods=["GET", "POST"])
def cms_tasks():
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    tasks = db_sess.query(Task).all()
    form = AddTaskForm()
    template = render_template("/cms/pages/cms_tasks.html", tasks=tasks, now_time=datetime.datetime.now(), form=form)
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = Task()
        task.title = "Новая задача"
        task.statement = "Введите условие задачи"
        task.input_spec = "Введите формат входных данных"
        task.output_spec = "Введите формат выходных данных"
        task.contest_id = 1
        task.test_cases = json.dumps([])
        db_sess.add(task)
        db_sess.commit()
        db_sess.close()
        return redirect("/cms/tasks/")
    return template


@app.route("/cms/task/<int:task_id>/index/", methods=["GET", "POST"])
def task_index(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    form = TaskEditForm(title=task.title,
                        in_data=task.input_spec,
                        out_data=task.output_spec,
                        contest=task.contest_id,
                        time_limit=task.time_limit,
                        memory_limit=task.memory_limit,
                        statement=task.statement,
                        mode=True if task.mode else False)
    form1 = TaskDeleteForm()
    template = render_template("/cms/task/pages/task_index.html", form=form, form1=form1, task=task, task_id=task.tid,
                               now_time=datetime.datetime.now())
    db_sess.close()
    if form.submit1.data and form.validate():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        task.title = form.title.data
        task.input_spec = form.in_data.data
        task.output_spec = form.out_data.data
        task.contest_id = int(form.contest.data)
        task.time_limit = int(form.time_limit.data)
        task.memory_limit = int(form.memory_limit.data)
        task.statement = form.statement.data
        task.mode = form.mode.data
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/index/")
    if form1.submit2.data and form1.validate():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        if form1.title.data != task.title:
            return redirect(f"/cms/task/{task_id}/index/")
        db_sess.query(Task).filter(Task.tid == task_id).delete()
        db_sess.commit()
        db_sess.close()
        return redirect("/cms/tasks/")
    return template


@app.route("/cms/task/<int:task_id>/tests/manual/", methods=["GET", "POST"])
def cms_manual_test(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    form = ManualTestForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        tests = task.get_test_cases()
        tests.append((form.in_data.data.replace("\r", "").strip("\n").rstrip("\n"),
                      form.out_data.data.replace("\r", "").strip("\n").rstrip("\n")))
        task.test_cases = json.dumps(tests)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/tests/manual/")
    return render_template("/cms/task/pages/test/add_tests/add_test_manual.html", task_id=task_id, form=form, now_time=datetime.datetime.now())


@app.route("/cms/task/<int:task_id>/test_groups/", methods=["GET", "POST"])
def cms_task_test_groups(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    # {"scoring": [{"required_tests": []", "points": int}]}

    scoring = task.get_scoring()
    groups = [[1, 0, 0, 0] for i in range(len(scoring))]
    form = GroupAddForm()
    for i in range(len(scoring)):
        try:
            points = scoring[i]["points"] / len(scoring[i]["required_tests"])
        except ZeroDivisionError:
            points = 0
        groups[i][0] = i + 1
        groups[i][1] = scoring[i]["points"]
        groups[i][2] = points
        if scoring[i]["required_tests"]:
            groups[i][3] = ", ".join(scoring[i]["required_tests"][:5])
        else:
            groups[i][3] = "нет"
    template = render_template("/cms/task/pages/test/test_groups/test_groups.html", form=form, groups=groups, task_id=task_id,
                               now_time=datetime.datetime.now())
    db_sess.close()

    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        scoring = task.get_scoring()
        scoring.append({"required_tests": [], "points": 0})
        task.scoring = json.dumps({"scoring": scoring})
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/test_groups")

    return template


@app.route("/cms/news/<int:news_id>/index/", methods=["GET", "POST"])
def cms_news_index(news_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    news = db_sess.query(News).filter(News.nid == news_id).first()
    form1 = NewsEditForm(title=news.title,
                         author=news.author,
                         content=news.content,
                         cid=news.cid)
    form2 = NewsDeleteForm()
    template = render_template("/cms/news/pages/news_index.html", news_id=news_id, form1=form1, form2=form2, now_time=datetime.datetime.now())
    db_sess.close()
    if form1.submit1.data and form1.validate():
        db_sess = db_session.create_session()
        news = db_sess.query(News).filter(News.nid == news_id).first()
        news.title = form1.title.data
        news.author = form1.author.data
        news.content = form1.content.data
        news.cid = int(form1.cid.data)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/news/{news_id}/index/")
    if form2.submit2.data and form2.validate():
        db_sess = db_session.create_session()
        db_sess.query(News).filter(News.nid == news_id).delete()
        db_sess.commit()
        db_sess.close()
        return redirect("/cms/news/")
    return template


@app.route("/cms/news/")
def cms_news():
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    all_news = db_sess.query(News).all()
    template = render_template("/cms/pages/cms_news.html", all_news=all_news, now_time=datetime.datetime.now())
    db_sess.close()
    return template


def set_admin(username):
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(username == User.login).first()
    user.is_admin = True
    db_sess.commit()
    db_sess.close()


@app.route("/cms/task/<int:task_id>/test_groups/<int:test_group_id>/", methods=["GET", "POST"])
def cms_task_test_group_edit(task_id, test_group_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    group_data = task.get_scoring()[test_group_id - 1]
    form = GroupEditForm(points=group_data["points"],
                         tests="\n".join(group_data["required_tests"]))
    form1 = GroupDeleteForm()
    template = render_template("/cms/task/pages/test/test_groups/test_group_view.html", form=form, form1=form1, task_id=task_id,
                               now_time=datetime.datetime.now())

    db_sess.close()
    if form.submit1.data and form.validate():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        group_data = {"points": int(form.points.data),
                      "required_tests": list(map(str.rstrip, form.tests.data.split("\n")))}
        scoring = task.get_scoring()
        scoring[test_group_id - 1] = group_data
        task.scoring = json.dumps({"scoring": scoring})
        task.points += int(form.points.data)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/test_groups/{test_group_id}/")
    if form1.submit2.data and form1.validate():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        scoring = task.get_scoring()
        task.points -= int(scoring[test_group_id - 1]["points"])
        scoring.pop(test_group_id - 1)
        task.scoring = json.dumps({"scoring": scoring})
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/test_groups/")
    return template


@app.route("/cms/task/<int:task_id>/tests/")
def cms_task_tests(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    if task.test_cases:
        tests = task.get_test_cases()
    db_sess.close()
    return render_template("/cms/task/pages/task_tests.html", task_id=task_id, tests=tests, length=len(tests),
                           now_time=datetime.datetime.now())


@app.route("/cms/task/<int:task_id>/tests/<int:test_id>/", methods=["GET", "POST"])
def cms_task_tests_view(task_id, test_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    tests = task.get_test_cases()
    test = tests[test_id - 1]
    form = TestDeleteForm()
    template = render_template("/cms/task/pages/test/tests/test_page.html", form=form, in_data=test[0][:256], out_data=test[1][:256],
                               now_time=datetime.datetime.now())
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        tests = task.get_test_cases()
        tests.pop(test_id - 1)
        task.test_cases = json.dumps(tests)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/tests/")
    return template


@app.route("/cms/task/<int:task_id>/tests/archive/", methods=["GET", "POST"])
def cms_archive_test(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    form = ArchiveTestForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == task_id).first()
        tests = task.get_test_cases()
        file_data = request.files[form.archive.name]
        with open(os.path.join(app.instance_path, file_data.filename), "wb") as f:
            f.write(file_data.read())
        with ZipFile(os.path.join(app.instance_path, file_data.filename)) as zip_file:
            add_tests = [["", ""] for i in range(len(zip_file.namelist()) // 2)]
            for file in zip_file.namelist():
                if file.endswith(".in"):
                    test_number = int(file[:file.find(".")])
                    with zip_file.open(file, "r") as opened_file:
                        add_tests[test_number - 1][0] = "\n".join(
                            [line.decode("UTF-8").rstrip() for line in opened_file.readlines()])
                elif file.endswith(".out"):
                    test_number = int(file[:file.find(".")])
                    with zip_file.open(file, "r") as opened_file:
                        add_tests[test_number - 1][1] = "\n".join(
                            [line.decode("UTF-8").rstrip() for line in opened_file.readlines()])
        os.remove(os.path.join(app.instance_path, file_data.filename))
        tests += add_tests
        task.test_cases = json.dumps(tests)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/task/{task_id}/tests/")
    return render_template("/cms/task/pages/test/add_tests/add_test_archive.html", task_id=task_id, now_time=datetime.datetime.now(), form=form)


@app.route("/cms/task/<int:task_id>/tests/<int:test_id>/")
def cms_test_data(task_id, test_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    tests = task.get_test_cases()
    cur_test = tests[test_id - 1]
    form = EditTestForm(in_data=cur_test[0],
                        out_data=cur_test[1])
    db_sess.close()
    if form.validate_on_submit():
        if form.delete.data:
            tests.pop(cur_test - 1)
            return redirect("/cms/task/<int:task_id>/tests/")


@app.route("/cms/task/<int:task_id>/tests/add_test/")
def cms_add_test(task_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    return render_template("/cms/task/pages/add_test.html", task_id=task_id, now_time=datetime.datetime.now())


@app.route("/cms/contests/", methods=["GET", "POST"])
def cms_contests():
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    form = AddContestForm()
    db_sess = db_session.create_session()
    contests = db_sess.query(Contest).all()
    template = render_template("/cms/pages/cms_contests.html", title="Контесты", form=form, contests=contests,
                               now_time=datetime.datetime.now())
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        contest = Contest()
        contest.title = "Новый контест"
        contest.start_time = datetime.datetime.now()
        contest.end_time = datetime.datetime.now()
        db_sess.add(contest)
        db_sess.commit()
        db_sess.close()
        return redirect("/cms/contests/")
    return template


@app.route("/cms/contest/<int:contest_id>/index/", methods=["GET", "POST"])
def cms_contest_index(contest_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
    form = ContestEditForm(title=contest.title,
                           start_time=contest.start_time,
                           end_time=contest.end_time)
    form1 = ContestDeleteForm()
    template = render_template("/cms/contest/pages/contest_index.html", title="Главная", form=form, form1=form1,
                               contest_id=contest_id, now_time=datetime.datetime.now())
    db_sess.close()
    if form.submit1.data and form.validate():
        db_sess = db_session.create_session()
        contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
        contest.title = form.title.data
        contest.start_time = form.start_time.data
        contest.end_time = form.end_time.data
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/contest/{contest_id}/index/")
    if form1.submit2.data and form1.validate:
        db_sess = db_session.create_session()
        contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
        if form1.title.data != contest.title:
            db_sess.close()
            return redirect(f"/cms/contest/{contest_id}/index/")
        contest = db_sess.query(Contest).filter(Contest.cid == contest_id).delete()
        db_sess.commit()
        db_sess.close()
        return redirect("/cms/contests/")
    return template


@app.route("/cms/contest/<int:contest_id>/tasks/")
def cms_contest_tasks(contest_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
    tasks = contest.tasks
    template = render_template("/cms/contest/pages/contest_tasks.html", title="Задачи", tasks=tasks, contest_id=contest_id,
                               now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/cms/contest/<int:contest_id>/news/", methods=["GET", "POST"])
def cms_contest_news(contest_id):
    if not current_user.is_authenticated or (current_user.is_authenticated and not current_user.is_admin):
        return abort(403)
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest_id).first()
    form = NewsCreateForm()
    all_news = contest.news
    template = render_template("/cms/contest/pages/contest_news.html", form=form, title="Новости", all_news=all_news, contest_id=contest_id,
                               now_time=datetime.datetime.now())
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        news = News()
        news.title = "Заголовок новости"
        news.author = "Автор новости"
        news.content = "Содержание новости"
        news.cid = contest_id
        db_sess.add(news)
        db_sess.commit()
        db_sess.close()
        return redirect(f"/cms/contest/{contest_id}/news/")
    return template


@app.route("/contest/<int:contest>/index/")
@limiter.limit("50 per minute")
def index_page(contest):
    db_sess = db_session.create_session()
    contest_data = db_sess.query(Contest).filter(contest == Contest.cid).first()
    contest_title = db_sess.query(Contest).filter(Contest.cid == contest).first().title
    if not contest_data:
        db_sess.close()
        return abort(404)
    start_time = contest_data.start_time
    end_time = contest_data.end_time
    now_time = datetime.datetime.now()
    status = "Не начат"
    if start_time > now_time:
        delta_time = start_time - now_time
    elif start_time <= now_time <= end_time:
        status = "Идёт"
        delta_time = now_time - start_time
    else:
        status = "Завершён"
        delta_time = end_time - start_time
    seconds = delta_time.seconds
    days = delta_time.days
    runs_string = ""
    if days:
        runs_string += f"{days}:"
    runs_string += f"{seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"

    all_news = db_sess.query(News).all()
    template = render_template("/files/contest/pages/index.html", title="EContest", start_time=start_time, end_time=end_time, status=status, all_news=all_news[::-1],
                               runs_string=runs_string, contest=contest, contest_title=contest_title,
                               now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def login_form():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.login == form.username.data).first()
        db_sess.close()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/contests")
    return render_template("/files/client/login.html", title="Вход", form=form, contest_title="EContest",
                           now_time=datetime.datetime.now())


@app.route("/logout")
@limiter.limit("20 per minute")
def logout():
    logout_user()
    return redirect("/contests")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def register_form():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User()
        user.login = form.username.data
        user.password = generate_password_hash(form.password.data)
        db_sess = db_session.create_session()
        user_found = db_sess.query(User).filter(User.login == form.username.data).first()
        if user_found is not None:
            db_sess.close()
            return render_template("/files/client/register.html", title="Регистрация", form=form)
        db_sess.add(user)
        db_sess.commit()
        db_sess.close()
        return redirect("/contests")
    return render_template("register.html", title="Регистрация", form=form, contest_title="EContest",
                           now_time=datetime.datetime.now())


@app.route("/task/<int:task_id>")
@limiter.limit("70 per minute")
def get_task_data(task_id):
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    contest = task.contest
    if datetime.datetime.now() < task.contest.start_time and not (current_user.is_authenticated and current_user.is_admin):
        db_sess.close()
        return render_template("contest_access_denied", title="Доступ запрещён", contest=contest.cid,
                               contest_title=contest.title, now_time=datetime.datetime.now())
    if not task:
        db_sess.close()
        return abort(404)
    template = render_template("/files/contest/pages/task.html", task=task, title=task.title, contest=contest.cid,
                               contest_title=contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/submit", methods=["GET", "POST"])
@limiter.limit("30 per minute")
@login_required
def submit(contest):
    form = SubmissionForm()
    if request.args.get("task_id", ""):
        form.task.data = request.args.get("task_id", "")
    db_sess = db_session.create_session()
    contest_object = db_sess.query(Contest).filter(Contest.cid == contest).first()
    contest_title = contest_object.title
    if datetime.datetime.now() < contest_object.start_time or contest_object.end_time < datetime.datetime.now() and not (current_user.is_authenticated and current_user.is_admin):
        db_sess.close()
        return render_template("/files/server/contest_access_denied.html", title="Доступ запрещён", contest=contest,
                               contest_title=contest_object.title, now_time=datetime.datetime.now())
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == form.task.data).first()
        if not task:
            db_sess.close()
            return render_template("/files/contest/pages/submit.html", title="Отослать", form=form, errors=True, contest=contest,
                                   contest_title=contest_title, now_time=datetime.datetime.now())
        cur_us = db_sess.merge(current_user)
        if contest != task.contest_id:
            return abort(406)
        submission = Submission()
        submission.code = form.code.data
        submission.language = form.language.data
        submission.uid = cur_us.uid
        submission.user = cur_us
        submission.tid = task.tid
        submission.task = task
        submission.cid = contest
        db_sess.add(submission)
        db_sess.commit()
        checker.add_submission(submission.s_id)
        db_sess.close()
        return redirect(f"/contest/{contest}/submissions")
    return render_template("/files/contest/pages/submit.html", title="Отослать", form=form, errors=False, contest=contest,
                           contest_title=contest_title, now_time=datetime.datetime.now())


@app.route("/contest/<int:contest>/submissions")
@limiter.limit("100 per minute")
@login_required
def get_submissions(contest):
    COLORS = {"ok": "#157002", "wa": "#6b0111", "tl": "#828003", "qu": "#000000", "te": "#116bfa", "ps": "#000000",
              "ce": "#0083b1", "co": "#116bfa"}
    BCOLORS = {"ok": "#b0eba4", "wa": "#f57d8f", "tl": "#f7f44a", "qu": "#ffffff", "te": "#94bdff", "ps": "#cfd0d1",
               "ce": "#bdeeff", "co": "#94bdff"}
    VERDICTS = {"ok": "Полное решение", "qu": "В очереди", "te": "Выполняется", "wa": "Неправильный ответ",
                "tl": "Превышено ограничение по времени", "re": "Ошибка исполнения",
                "ml": "Превышено ограничение по памяти", "se": "Ошибка тестирующей системы", "ps": "Частичное решение",
                "ce": "Ошибка компиляции", "co": "Компилируется"}
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.uid == current_user.uid).first()
    submissions = tuple(filter(lambda x: x.cid == contest, user.submissions))
    contest_title = db_sess.query(Contest).filter(Contest.cid == contest).first().title
    template = render_template("/files/contest/pages/submissions.html", user=user, colors=COLORS, bcolors=BCOLORS, verdicts=VERDICTS,
                               threads_count=checker.threads_count, max_threads_count=checker.MAX_THREADS_COUNT,
                               queued_count=len(checker.queue), submissions=submissions, contest=contest,
                               contest_title=contest_title, title="Мои посылки", now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/tasks")
@limiter.limit("40 per minute")
def tasks_function(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest).first()
    if datetime.datetime.now() < contest.start_time and not (current_user.is_authenticated and current_user.is_admin):
        db_sess.close()
        return render_template("/files/server/contest_access_denied.html", title="Доступ запрещён", contest=contest.cid,
                               contest_title=contest.title, now_time=datetime.datetime.now())
    if datetime.datetime.now() < contest.start_time:
        return abort(403)
    all_tasks = contest.tasks
    accs = {}
    for task in all_tasks:
        cnt = 0
        for submission in task.submissions:
            if submission.verdict.startswith("ok"):
                cnt += 1
        accs[task.tid] = cnt
    template = render_template("/files/contest/pages/tasks.html", title="Задачи", tasks=all_tasks, accs=accs, contest=contest.cid,
                               contest_title=contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contests")
@limiter.limit("20 per minute")
def contests():
    db_sess = db_session.create_session()
    contests = db_sess.query(Contest).all()
    template = render_template("/files/client/contests.html", title="Контесты", contests=contests, now_time=datetime.datetime.now(),
                               contest_title="EContest")
    db_sess.close()
    return template


@app.route("/submission_view/<int:submission_id>")
@limiter.limit("30 per minute")
@login_required
def submission_view(submission_id):
    db_sess = db_session.create_session()
    submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
    if not submission:
        db_sess.close()
        return abort(404)
    if submission.user != current_user:
        db_sess.close()
        return abort(401)
    all_verdicts = json.loads(submission.verdicts)
    all_groups = submission.task.get_scoring()
    points = [0.0 for i in range(len(submission.task.get_test_cases()))]
    group_points_all = [0.0 for i in range(len(all_groups))]
    for i, group in enumerate(all_groups):
        group_points = group["points"] / len(group["required_tests"])
        for group_test in group["required_tests"]:
            if all_verdicts[str(int(group_test))][0] == "ok":
                group_points_all[i] += group_points
                points[int(group_test) - 1] = round(group_points, 2)
        group["required_tests"] = list(map(int, group["required_tests"]))
        group_points_all[i] = round(group_points_all[i], 2)
    print(list(all_verdicts.values()), file=sys.stderr)
    template = render_template("/files/contest/pages/submission_view.html", submission=submission, all_groups=all_groups,
                               len_groups=len(all_groups), points=points, group_points_all=group_points_all,
                               verdicts=list(all_verdicts.values()), title=f"Посылка #{submission_id}",
                               contest=submission.cid, contest_title=submission.contest.title,
                               now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/standings")
@limiter.limit("15 per minute")
def standings(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()

    start_time = contest.start_time
    end_time = contest.end_time
    now_time = datetime.datetime.now()
    status = "не начат"
    if start_time > now_time:
        delta_time = start_time - now_time
    elif start_time <= now_time <= end_time:
        status = "идёт"
        delta_time = now_time - start_time
    else:
        status = "завершён"
        delta_time = end_time - start_time
    seconds = delta_time.seconds
    days = delta_time.days
    all_time = days * 86400 + seconds
    runs_string = ""
    if days:
        runs_string += f"{days}:"
    runs_string += f"{seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"

    delta_time = end_time - start_time
    seconds = delta_time.seconds
    days = delta_time.days
    all_delta = ""
    if days:
        all_delta += f"{days}:"
    all_delta += f"{seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"

    if status == "завершён":
        percent = 100
    elif status == "не начат":
        percent = 0
    else:
        percent = round(all_time / (days * 86400 + seconds) * 100)

    data = {}
    for submission in contest.submissions:
        user = submission.user.login
        data[user] = data.get(user, {})
        data[user][submission.tid] = max(data[user].get(submission.tid, 0.0), submission.points)
    items = list(data.items())
    new_items = [(username, sum(points.values())) for username, points in items]
    new_items.sort(key=lambda x: x[1], reverse=True)
    template = render_template("/files/contest/pages/standings.html", title="Положение", items=new_items, status=status,
                               runs_string=runs_string, all_delta=all_delta, percent=percent, contest=contest.cid,
                               contest_title=contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/full_standings")
@limiter.limit("10 per minute")
def full_standings(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()

    start_time = contest.start_time
    end_time = contest.end_time
    now_time = datetime.datetime.now()
    status = "не начат"
    if start_time > now_time:
        delta_time = start_time - now_time
    elif start_time <= now_time <= end_time:
        status = "идёт"
        delta_time = now_time - start_time
    else:
        status = "завершён"
        delta_time = end_time - start_time
    seconds = delta_time.seconds
    days = delta_time.days
    all_time = days * 86400 + seconds
    runs_string = ""
    if days:
        runs_string += f"{days}:"
    runs_string += f"{seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"

    delta_time = end_time - start_time
    seconds = delta_time.seconds
    days = delta_time.days
    all_delta = ""
    if days:
        all_delta += f"{days}:"
    all_delta += f"{seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"

    if status == "завершён":
        percent = 100
    elif status == "не начат":
        percent = 0
    else:
        percent = round(all_time / (days * 86400 + seconds) * 100)

    data = {}
    for submission in contest.submissions:
        user = submission.user.login
        data[user] = data.get(user, {})
        data[user][submission.tid] = max(data[user].get(submission.tid, 0.0), submission.points)
    new_items = [(user, sum(points.values())) for user, points in data.items()]
    new_items.sort(key=lambda x: x[1], reverse=True)
    all_tasks = db_sess.query(Task).filter(Task.contest_id == contest.cid)
    template = render_template("/files/contest/pages/full_standings.html", title="Полное положение", status=status, runs_string=runs_string,
                               all_delta=all_delta, percent=percent, items=data, new_items=new_items,
                               contest=contest.cid, contest_title=contest.title, now_time=datetime.datetime.now(),
                               all_tasks=all_tasks)
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/status")
@limiter.limit("20 per minute")
def status(contest):
    COLORS = {"ok": "#157002", "wa": "#6b0111", "tl": "#828003", "qu": "#000000", "te": "#116bfa", "ps": "#000000",
              "ce": "#0083b1", "co": "#116bfa"}
    BCOLORS = {"ok": "#b0eba4", "wa": "#f57d8f", "tl": "#f7f44a", "qu": "#ffffff", "te": "#94bdff", "ps": "#cfd0d1",
               "ce": "#bdeeff", "co": "#94bdff"}
    VERDICTS = {"ok": "Полное решение", "qu": "В очереди", "te": "Выполняется", "wa": "Неправильный ответ",
                "tl": "Превышено ограничение по времени", "re": "Ошибка исполнения",
                "ml": "Превышено ограничение по памяти", "se": "Ошибка тестирующей системы", "ps": "Частичное решение",
                "ce": "Ошибка компиляции", "co": "Компилируется"}
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()
    submissions = db_sess.query(Submission).filter(Submission.cid == contest.cid).all()
    template = render_template("/files/contest/pages/status.html", title="Статус", submissions=submissions, contest=contest.cid,
                               contest_title=contest.title, threads_count=checker.threads_count,
                               max_threads_count=checker.MAX_THREADS_COUNT, queued_count=len(checker.queue),
                               now_time=datetime.datetime.now(), bcolors=BCOLORS, colors=COLORS, verdicts=VERDICTS)
    db_sess.close()
    return template


@app.route("/verdicts_info")
@limiter.limit("30 per minute")
def verdicts_info():
    return render_template("/files/client/verdicts_info.html", title="Пояснение вердиктов чекера", contest_title="EContest Help",
                           now_time=datetime.datetime.now())


if __name__ == "__main__":
    db_session.global_init("db/econtest.db")
    app.register_blueprint(blueprint)
    set_admin("admin")
    app.run(host="0.0.0.0", port=8080)
