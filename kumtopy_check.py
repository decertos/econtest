from kumtopy import Robot, Field, generate_field, get_field_answer
import sys


# Loading
f = sys.argv[1][0]
f1 = sys.argv[1][1]
with open(f, "r", encoding="UTF-8") as opened_file:
    code = opened_file.read()
with open(f1, "r", encoding="UTF-8") as opened_file:
    correct = opened_file.read()

# Checking
field, robot = generate_field(code)
exec(robot.parse_code_new(code))
if get_field_answer(field):
    print("OK")
else:
    print("WA")