from flask import abort, Flask, redirect, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from data import db_session
from data.users import User
from data.submissions import Submission
from data.tasks import Task
from data.contests import Contest

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField
from wtforms.validators import EqualTo, DataRequired

from flask_login import LoginManager, current_user, login_user, logout_user, login_required

from werkzeug.security import check_password_hash, generate_password_hash

from collections import deque
import subprocess
import threading
import datetime
from random import randint
import time
import json
import sys
import os


MODE_FULL_CHECK = 0
MODE_PARTIAL_CHECK = 1


class Checker:
    def __init__(self):
        self.queue = deque()
        self.MAX_THREADS_COUNT = 2
        self.threads_count = 0

    def check_ended(self, submission_id, verdict, test, execution_time):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        submission.verdict = f"{verdict} {test}"
        submission.execution_time = round(execution_time * 1000, 0)
        db_sess.commit()
        db_sess.close()
        os.remove(f"check{submission_id}.py")

    def check(self, submission_id):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        with open(f"check{submission.s_id}.py", "w", encoding="UTF-8") as f:
            f.write(submission.code)
        test_cases = submission.task.get_test_cases()
        verdicts = {i + 1: ("ig", 0) for i in range(len(test_cases))}
        submission.points = 0
        max_execution_time = 0
        for i, t in enumerate(test_cases, start=1):
            t0 = time.time()
            submission.verdict = f"te {i}"
            db_sess.commit()
            in_data, out_data = t
            try:
                program_output = subprocess.check_output(["python", f"check{submission.s_id}.py"],
                                                         input=in_data,
                                                         text=True,
                                                         timeout=submission.task.time_limit,
                                                         stderr=subprocess.STDOUT).strip()
                if out_data != program_output:
                    verdicts[i] = ("wa", round((time.time() - t0) * 1000))
                    submission.verdicts = json.dumps(verdicts)
                    submission.verdict = f"wa {i}"
                    db_sess.commit()
                    self.check_ended(submission.s_id, "wa", i, max(max_execution_time, time.time() - t0))
                    db_sess.close()
                    self.threads_count -= 1
                    if self.queue:
                        self.threads_count += 1
                        db_sess = db_session.create_session()
                        submission1 = db_sess.query(Submission).filter(Submission.s_id == self.queue.popleft()).first()
                        if submission1.task.mode == MODE_FULL_CHECK:
                            thread = threading.Thread(target=self.check, args=(submission1.s_id,))
                        elif submission1.task.mode == MODE_PARTIAL_CHECK:
                            thread = threading.Thread(target=self.check_partial, args=(submission1.s_id,))
                        db_sess.close()
                        thread.start()
                    return
            except subprocess.TimeoutExpired:
                verdicts[i] = ("tl", round((time.time() - t0) * 1000))
                submission.verdicts = json.dumps(verdicts)
                submission.verdict = f"tl {i}"
                db_sess.commit()
                self.check_ended(submission.s_id, "tl", i, max(max_execution_time, time.time() - t0))
                db_sess.close()
                self.threads_count -= 1
                if self.queue:
                    self.threads_count += 1
                    db_sess = db_session.create_session()
                    submission1 = db_sess.query(Submission).filter(Submission.s_id == self.queue.popleft()).first()
                    if submission1.task.mode == MODE_FULL_CHECK:
                        thread = threading.Thread(target=self.check, args=(submission1.s_id,))
                    elif submission1.task.mode == MODE_PARTIAL_CHECK:
                        thread = threading.Thread(target=self.check_partial, args=(submission1.s_id,))
                    db_sess.close()
                    thread.start()
                return
            except Exception as e:
                verdicts[i] = ("re", round((time.time() - t0) * 1000))
                submission.verdicts = json.dumps(verdicts)
                submission.verdict = f"re {i}"
                db_sess.commit()
                self.check_ended(submission.s_id, "re", i, max(max_execution_time, time.time() - t0))
                db_sess.close()
                self.threads_count -= 1
                if self.queue:
                    self.threads_count += 1
                    db_sess = db_session.create_session()
                    submission1 = db_sess.query(Submission).filter(Submission.s_id == self.queue.popleft()).first()
                    if submission1.task.mode == MODE_FULL_CHECK:
                        thread = threading.Thread(target=self.check, args=(submission1.s_id,))
                    elif submission1.task.mode == MODE_PARTIAL_CHECK:
                        thread = threading.Thread(target=self.check_partial, args=(submission1.s_id,))
                    db_sess.close()
                    thread.start()
                return
            verdicts[i] = ("ok", round((time.time() - t0) * 1000))
            max_execution_time = max(max_execution_time, time.time() - t0)
        submission.points = 100
        submission.verdicts = json.dumps(verdicts)
        db_sess.commit()
        self.check_ended(submission.s_id, "ok", "", max_execution_time)
        db_sess.close()
        self.threads_count -= 1
        if self.queue:
            self.threads_count += 1
            db_sess = db_session.create_session()
            submission1 = db_sess.query(Submission).filter(Submission.s_id == self.queue.popleft()).first()
            if submission1.task.mode == MODE_FULL_CHECK:
                thread = threading.Thread(target=self.check, args=(submission1.s_id,))
            elif submission1.task.mode == MODE_PARTIAL_CHECK:
                thread = threading.Thread(target=self.check_partial, args=(submission1.s_id,))
            db_sess.close()
            thread.start()

    def check_partial(self, submission_id):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        test_cases = submission.task.get_test_cases()
        verdicts = {i + 1: ("te", 0) for i in range(len(test_cases))}
        points = 0
        add_points = 100 / len(test_cases)
        passed = 0
        with open(f"check{submission.s_id}.py", "w", encoding="UTF-8") as f:
            f.write(submission.code)
        max_execution_time = 0
        for i, t in enumerate(test_cases, start=1):
            t0 = time.time()
            submission.verdict = f"te {i}"
            db_sess.commit()
            in_data, out_data = t
            try:
                program_output = subprocess.check_output(["python", f"check{submission.s_id}.py"],
                                                         input=in_data,
                                                         text=True,
                                                         timeout=submission.task.time_limit,
                                                         stderr=subprocess.STDOUT).strip()
                if out_data != program_output:
                    verdicts[i] = ("wa", round((time.time() - t0) * 1000))
            except subprocess.TimeoutExpired:
                verdicts[i] = ("tl", round((time.time() - t0) * 1000))
            except Exception as e:
                verdicts[i] = ("re", round((time.time() - t0) * 1000))
            max_execution_time = max(max_execution_time, time.time() - t0)
            if verdicts[i] == ("te", 0):
                passed += 1
                verdicts[i] = ("ok", round((time.time() - t0) * 1000))
                points += add_points
        points = round(points, 2)
        if passed == len(test_cases):
            points = 100
        submission.verdicts = json.dumps(verdicts)
        submission.points = points
        db_sess.commit()
        self.threads_count -= 1
        if passed == len(test_cases):
            self.check_ended(submission_id, "ok", "", max_execution_time)
        else:
            self.check_ended(submission_id, "ps", passed, max_execution_time)
        db_sess.close()
        if self.queue:
            self.threads_count += 1
            db_sess = db_session.create_session()
            submission1 = db_sess.query(Submission).filter(Submission.s_id == self.queue.popleft()).first()
            if submission1.task.mode == MODE_FULL_CHECK:
                thread = threading.Thread(target=self.check, args=(submission1.s_id,))
            elif submission1.task.mode == MODE_PARTIAL_CHECK:
                thread = threading.Thread(target=self.check_partial, args=(submission1.s_id,))
            db_sess.close()
            thread.start()

    def add_submission(self, submission_id):
        db_sess = db_session.create_session()
        submission = db_sess.query(Submission).filter(Submission.s_id == submission_id).first()
        self.queue.append(submission.s_id)
        print("ADDED")
        if self.threads_count < self.MAX_THREADS_COUNT:
            self.threads_count += 1
            if submission.task.mode == MODE_FULL_CHECK:
                thread = threading.Thread(target=self.check, args=(self.queue.popleft(),))
            elif submission.task.mode == MODE_PARTIAL_CHECK:
                thread = threading.Thread(target=self.check_partial, args=(self.queue.popleft(), ))
            db_sess.close()
            thread.start()


app = Flask(__name__)
app.config["SECRET_KEY"] = "301f9c4c690b99e45d0e9504f3656d654a2710c549428e601e609cddf2614ef5"
limiter = Limiter(get_remote_address, app=app, default_limits=["10 per minute"])
login_manager = LoginManager()
login_manager.init_app(app)

checker = Checker()


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    ans = db_sess.query(User).get(user_id)
    db_sess.close()
    return ans


class LoginForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired(message="Это обязательное поле.")])
    password = PasswordField("Пароль", validators=[DataRequired(message="Это обязательное поле.")])
    remember_me = BooleanField("Запомнить меня")
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
    code = TextAreaField("Код", validators=[DataRequired("Это обязательное поле.")])
    submit = SubmitField("Отправить")


class CreateTaskForm(FlaskForm):
    title = StringField("Название")
    statement = TextAreaField("Условие")
    in_data = TextAreaField("Формат входных данных")
    out_data = TextAreaField("Формат выходных данных")
    time_limit = StringField("Ограничение по времени исполнения")
    memory_limit = StringField("Ограничение по памяти")
    tests = TextAreaField("Тесты (через -)")
    contest = StringField("ID Контеста")
    mode = StringField("Режим (0 - все тесты, 1 - с частичным)")
    submit = SubmitField("Отправить")


@app.route("/")
def main_page():
    return redirect("/index")


@app.route("/contest/<int:contest>/index")
@limiter.limit("20 per minute")
def index_page(contest):
    db_sess = db_session.create_session()
    contest_data = db_sess.query(Contest).filter(contest == Contest.cid).first()
    contest_title = db_sess.query(Contest).filter(Contest.cid == contest).first().title
    print(db_sess.query(Contest).all(), file=sys.stderr)
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
    runs_string += f"{days * 24 + seconds // 3600}:{str((seconds // 60) % 60).zfill(2)}:{str(seconds % 60).zfill(2)}"
    template = render_template("index.html", title="EContest", start_time=start_time, end_time=end_time, status=status, runs_string=runs_string, contest=contest, contest_title=contest_title, now_time=datetime.datetime.now())
    return template


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login_form():
    form = LoginForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.login == form.username.data).first()
        db_sess.close()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/index")
    return render_template("login.html", title="Вход", form=form, contest_title="EContest", now_time=datetime.datetime.now())


@app.route("/logout")
@limiter.limit("10 per minute")
def logout():
    logout_user()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
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
            return render_template("register.html", title="Регистрация", form=form)
        db_sess.add(user)
        db_sess.commit()
        db_sess.close()
        return redirect("/index")
    return render_template("register.html", title="Регистрация", form=form, contest_title="EContest", now_time=datetime.datetime.now())


@app.route("/task/<int:task_id>")
@limiter.limit("50 per minute")
def get_task_data(task_id):
    db_sess = db_session.create_session()
    task = db_sess.query(Task).filter(Task.tid == task_id).first()
    if not task:
        db_sess.close()
        return abort(404)
    template = render_template("task.html", task=task, title=task.title, contest=task.contest_id, contest_title=task.contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/add_task", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def add_task():
    if current_user.login != "admin":
        return abort(403)
    form = CreateTaskForm()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = Task()
        task.title = form.title.data
        task.statement = form.statement.data
        task.input_spec = form.in_data.data
        task.output_spec = form.out_data.data
        task.time_limit = int(form.time_limit.data)
        task.memory_limit = int(form.memory_limit.data)
        task.mode = int(form.mode.data)
        task.contest_id = int(form.contest.data)
        test_cases = []
        j = 0
        test_case = []
        for i in form.tests.data.split("-"):
            test_case.append(i.replace("\r", "").strip("\n").rstrip("\n"))
            if j % 2 == 1:
                test_cases.append(tuple(test_case))
                test_case.clear()
            j += 1
        task.test_cases = json.dumps(test_cases)
        db_sess.add(task)
        db_sess.commit()
        db_sess.close()
        return "TASK ADDED"
    return render_template("addtask.html", form=form, now_time=datetime.datetime.now())


@app.route("/add_submission")
@limiter.limit("5 per minute")
def add_submission():
    if current_user.login != "admin":
        return abort(403)
    db_sess = db_session.create_session()
    user = db_sess.query(User).first()
    submission = Submission()
    submission.verdict = "ok None"
    submission.code = "print()"
    submission.time = datetime.datetime.now()
    submission.task = db_sess.query(Task).first()
    user.submissions.append(submission)
    db_sess.add(submission)
    db_sess.commit()
    db_sess.close()
    return redirect("/submissions")


@app.route("/add_contest")
@limiter.limit("5 per minute")
def add_contest():
    db_sess = db_session.create_session()
    contest = Contest()
    contest.start_time = datetime.datetime(2025, 3, 27, 15, 0, 0)
    contest.end_time = contest.start_time + datetime.timedelta(days=365)
    contest.title = "Test Contest"
    db_sess.add(contest)
    db_sess.commit()
    db_sess.close()
    return redirect("/")


@app.route("/contest/<int:contest>/submit", methods=["GET", "POST"])
@limiter.limit("50 per minute")
@login_required
def submit(contest):
    form = SubmissionForm()
    if request.args.get("task_id", ""):
        form.task.data = request.args.get("task_id", "")
    db_sess = db_session.create_session()
    contest_object = db_sess.query(Contest).filter(Contest.cid == contest).first()
    contest_title = contest_object.title
    if datetime.datetime.now() < contest_object.start_time or contest_object.end_time < datetime.datetime.now():
        return abort(403)
    db_sess.close()
    if form.validate_on_submit():
        db_sess = db_session.create_session()
        task = db_sess.query(Task).filter(Task.tid == form.task.data).first()
        if not task:
            db_sess.close()
            return render_template("submit.html", title="Отослать", form=form, errors=True, contest=contest, contest_title=contest_title)
        cur_us = db_sess.merge(current_user)
        if contest != task.contest_id:
            return abort(406)
        submission = Submission()
        submission.code = form.code.data
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
    return render_template("submit.html", title="Отослать", form=form, errors=False, contest=contest, contest_title=contest_title, now_time=datetime.datetime.now())


@app.route("/contest/<int:contest>/submissions")
@limiter.limit("100 per minute")
@login_required
def get_submissions(contest):
    COLORS = {"ok": "#157002", "wa": "#6b0111", "tl": "#828003", "qu": "#000000", "te": "#116bfa", "ps": "#000000"}
    BCOLORS = {"ok": "#b0eba4", "wa": "#f57d8f", "tl": "#f7f44a", "qu": "#ffffff", "te": "#94bdff", "ps": "#cfd0d1"}
    VERDICTS = {"ok": "Полное решение", "qu": "В очереди", "te": "Выполняется", "wa": "Неправильный ответ", "tl": "Превышено ограничение по времени", "re": "Ошибка исполнения", "ml": "Превышено ограничение по памяти", "se": "Ошибка тестирующей системы", "ps": "Частичное решение"}
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.uid == current_user.uid).first()
    submissions = tuple(filter(lambda x: x.cid == contest, user.submissions))
    contest_title = db_sess.query(Contest).filter(Contest.cid == contest).first().title
    template = render_template("submissions.html", user=user, colors=COLORS, bcolors=BCOLORS, verdicts=VERDICTS, threads_count=checker.threads_count, max_threads_count=checker.MAX_THREADS_COUNT, queued_count=len(checker.queue), submissions=submissions, contest=contest, contest_title=contest_title, title="Мои посылки", now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/tasks")
@limiter.limit("50 per minute")
def tasks_function(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(Contest.cid == contest).first()
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
    template = render_template("tasks.html", title="Задачи", tasks=all_tasks, accs=accs, contest=contest.cid, contest_title=contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contests")
@limiter.limit("20 per minute")
def contests():
    db_sess = db_session.create_session()
    contests = db_sess.query(Contest).all()
    template = render_template("contests.html", title="Контесты", contests=contests, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/submission_view/<int:submission_id>")
@limiter.limit("50 per minute")
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
    template = render_template("submission_view.html", submission=submission, verdicts=all_verdicts.items(), title=f"Посылка #{submission_id}", contest=submission.cid, contest_title=submission.contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/standings")
@limiter.limit("5 per minute")
def standings(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()
    data = {}
    for submission in contest.submissions:
        user = submission.user.login
        data[user] = data.get(user, {})
        data[user][submission.tid] = max(data[user].get(submission.tid, 0.0), submission.points)
    items = list(data.items())
    new_items = [(username, sum(points.values())) for username, points in items]
    new_items.sort(key=lambda x: x[1], reverse=True)
    template = render_template("standings1.html", title="Положение", items=new_items, contest=contest.cid, contest_title=contest.title, now_time=datetime.datetime.now())
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/full_standings")
@limiter.limit("10 per minute")
def full_standings(contest):
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()
    data = {}
    for submission in contest.submissions:
        user = submission.user.login
        data[user] = data.get(user, {})
        data[user][submission.tid] = max(data[user].get(submission.tid, 0.0), submission.points)
    new_items = [(user, sum(points.values())) for user, points in data.items()]
    new_items.sort(key=lambda x: x[1], reverse=True)
    all_tasks = db_sess.query(Task).filter(Task.contest_id == contest.cid)
    template = render_template("full_standings.html", title="Полное положение", items=data, new_items=new_items, contest=contest.cid, contest_title=contest.title, now_time=datetime.datetime.now(), all_tasks=all_tasks)
    db_sess.close()
    return template


@app.route("/contest/<int:contest>/status")
def status(contest):
    COLORS = {"ok": "#157002", "wa": "#6b0111", "tl": "#828003", "qu": "#000000", "te": "#116bfa", "ps": "#000000"}
    BCOLORS = {"ok": "#b0eba4", "wa": "#f57d8f", "tl": "#f7f44a", "qu": "#ffffff", "te": "#94bdff", "ps": "#cfd0d1"}
    VERDICTS = {"ok": "Полное решение", "qu": "В очереди", "te": "Выполняется", "wa": "Неправильный ответ", "tl": "Превышено ограничение по времени", "re": "Ошибка исполнения", "ml": "Превышено ограничение по памяти", "se": "Ошибка тестирующей системы", "ps": "Частичное решение"}
    db_sess = db_session.create_session()
    contest = db_sess.query(Contest).filter(contest == Contest.cid).first()
    submissions = db_sess.query(Submission).filter(Submission.cid == contest.cid).all()
    template = render_template("status.html", title="Статус", submissions=submissions, contest=contest.cid, contest_title=contest.title, threads_count=checker.threads_count, max_threads_count=checker.MAX_THREADS_COUNT, queued_count=len(checker.queue), now_time=datetime.datetime.now(), bcolors=BCOLORS, colors=COLORS, verdicts=VERDICTS)
    db_sess.close()
    return template


@app.route("/verdicts_info")
@limiter.limit("150 per minute")
def verdicts_info():
    return render_template("verdicts_info.html", now_time=datetime.datetime.now())


if __name__ == "__main__":
    db_session.global_init("db/econtest.db")
    app.run(host="0.0.0.0", port=8080)
