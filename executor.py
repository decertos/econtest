from data import db_session
from data.users import User
from app import set_admin, remove_admin, check_user
import sys


db_session.global_init("db/econtest.db")
commands = sys.argv[1:]

if len(commands) == 0:
    print("no command given")
    exit(0)

if commands[0] == "help" or commands[0] == "-h":
    if len(commands) > 1:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 0")
        exit(0)
    print("EContest Commands Executor Help")
    print("Commands")
    print("set-admin <username> - Add a user with username <username> to administrators")
    print("remove-admin <username> - Remove a user with username <username> from administrators")
    print("check-user <username> - Check if a user with username <username> exists")
    print("remove-user <username> - Remove a user with username <username>")
    print("ban-user <username> <reason> - Ban a user with username <username> with reason <reason>")
    print("unban-user <username> - Unban a user with username <username>")
    print("userlist - Get a list of users")
if commands[0] == "set-admin":
    if len(commands) == 1:
        print("error: this command requires a 'user' argument")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 1")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"error: no such user: '{username}'")
        exit(0)
    set_admin(username)
    print(f"successfully set '{username}' as an administrator")
    exit(0)
elif commands[0] == "remove-admin":
    if len(commands) == 1:
        print("error: this command requires a 'user' argument")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 1")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"error: no such user: '{username}'")
        exit(0)
    remove_admin(username)
    print(f"successfully removed '{username}' from administrators")
elif commands[0] == "check-user":
    if len(commands) == 1:
        print("error: this command requires a 'user' argument")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 1")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"user '{username}' does not exits")
        exit(0)
    print(f"user '{username}' exists")
elif commands[0] == "remove-user":
    if len(commands) == 1:
        print("error: this command requires a 'user' argument")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 1")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"error: no such user: '{username}'")
        exit(0)
    db_sess = db_session.create_session()
    db_sess.query(User).filter(User.login == username).delete()
    print(f"successfully deleted user with username '{username}'")
elif commands[0] == "ban-user":
    if len(commands) < 3:
        print(f"not enough arguments for this command: {len(commands) - 1} instead of 2")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 2")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"error: no such user: '{username}'")
        exit(0)
    reason = commands[2:]
    db_sess = db_session.create_session()
    db_sess.query(User).filter(User.login == username).first().banned = " ".join(reason)
    db_sess.commit()
    db_sess.close()
    print(f"successfully banned user with username '{username}'")
elif commands[0] == "unban-user":
    if len(commands) == 1:
        print("error: this command requires a 'user' argument")
        exit(0)
    if len(commands) > 2:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 1")
        exit(0)
    username = commands[1]
    if not check_user(username):
        print(f"error: no such user: '{username}'")
        exit(0)
    db_sess = db_session.create_session()
    db_sess.query(User).filter(User.login == username).first().banned = ""
    db_sess.commit()
    db_sess.close()
    print(f"successfully unbanned user with username '{username}'")
elif commands[0] == "userlist":
    if len(commands) > 1:
        print(f"too much arguments for this command: {len(commands) - 1} instead of 0")
        exit(0)
    db_sess = db_session.create_session()
    users = db_sess.query(User).all()
    for user in users:
        print(f"ID {user.uid} | login: {user.login} | is_admin: {user.is_admin} | banned: ", end="")
        if user.banned:
            print(f"True, with reason: {user.banned}")
        else:
            print("False")
    db_sess.close()