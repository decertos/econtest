UP, RIGHT, LEFT, DOWN = 0, 1, 2, 3


class MoveError(Exception):
    pass


class RobotImportError(Exception):
    pass


class Robot:
    def __init__(self, field, x, y):
        self.x, self.y = x, y
        self.field = field

    def move_up(self):
        if self.field.get_cell(self.x, self.y).walls[UP]:
            raise MoveError("Невозможно пройти: сверху стена")
        if 0 <= self.y - 1 < self.field.height:
            self.y = self.y - 1
            return
        raise MoveError("Невозможно пройти: сверху стена")

    def move_right(self):
        if self.field.get_cell(self.x, self.y).walls[RIGHT]:
            raise MoveError("Невозможно пройти: справа стена")
        if 0 <= self.x + 1 < self.field.width:
            self.x = self.x + 1
            return
        raise MoveError("Невозможно пройти: справа стена")

    def move_left(self):
        if self.field.get_cell(self.x, self.y).walls[LEFT]:
            raise MoveError("Невозможно пройти: слева стена")
        if 0 <= self.x - 1 < self.field.height:
            self.x = self.x - 1
            return
        raise MoveError("Невозможно пройти: слева стена")

    def move_down(self):
        if self.field.get_cell(self.x, self.y).walls[DOWN]:
            raise MoveError("Невозможно пройти: снизу стена")
        if 0 <= self.y + 1 < self.field.height:
            self.y = self.y + 1
            return
        raise MoveError("Невозможно пройти: снизу стена")

    def free_up(self):
        return not self.field.get_cell(self.x, self.y).walls[UP]

    def free_right(self):
        return not self.field.get_cell(self.x, self.y).walls[RIGHT]

    def free_left(self):
        return not self.field.get_cell(self.x, self.y).walls[LEFT]

    def free_down(self):
        return not self.field.get_cell(self.x, self.y).walls[DOWN]

    def paint(self):
        self.field.fill(self.x, self.y)

    def parse_code(self, code: str):
        """использовать Робот
алг
нач

кон"""
        # Основное
        code = code[code.find("нач") + 3:code.find("кон")]
        code = code.replace("|", "#")

        # Движение
        DIRS = {"вверх": "up", "вправо": "right", "влево": "left", "вниз": "down"}
        for i in DIRS:
            code = code.replace(i, f"robot.move_{DIRS[i]}()")

        # Проверки стен
        DIRS = {"сверху": "up", "справа": "right", "слева": "left", "снизу": "down"}
        for i in DIRS:
            code = code.replace(f"{i} свободно", f"robot.free_{DIRS[i]}()")

        # Условия
        code = code.replace("если", "if")
        code = code.replace("то", ":")
        code = code.replace("все", "")

        # Циклы
        code = code.replace("нц пока", "while")
        code = code.replace("кц", "")
        new_code = ""
        for i in code.split("\n"):
            if "while" in i:
                new_code += i + ":\n"
                continue
            new_code += i + "\n"
        code = new_code

        # Логическое
        code = code.replace(" не ", " not ")
        code = code.replace(" и ", " and ")
        code = code.replace(" или ", " or ")

        # Закрашивание
        code = code.replace("закрасить", "robot.paint()")

        # Индентация
        new_code = ""
        for i in code.split("\n"):
            new_code += i[4:] + "\n"
        code = new_code.strip("\n").rstrip("\n")
        return code

    def parse_code_new(self, code: str):
        if "| использовать Робот" in code:
            raise RobotImportError("Робот не использован")

        code = code.replace("нач", "")
        code = code.replace("кон", "")
        code = code.replace("|", "#")
        code = code.replace("\t", "")

        code = code.replace("использовать Робот", "")
        code = code.replace("алг", "")

        DIRS = {"вниз": "down", "влево": "left", "вправо": "right", "вверх": "up"}
        for direction in DIRS:
            code = code.replace(direction, f"robot.move_{DIRS[direction]}()")

        DIRS = {"снизу свободно": "down", "слева свободно": "left", "справа свободно": "right", "сверху свободно": "up"}
        for direction in DIRS:
            code = code.replace(direction, f"robot.free_{DIRS[direction]}()")

        code = code.replace("нц пока", "while")
        code = code.replace("если", "if")
        code = code.replace("то", ":")
        indentation_level = 0
        new_code = ""
        for line in code.split("\n"):
            new_code += "    " * indentation_level + line
            if "while" in line or "if" in line:
                if "while" in line:
                    new_code += ":"
                indentation_level += 1
            elif "кц" in line or "все" in line or "всё" in line:
                indentation_level -= 1
            new_code += "\n"

        code = new_code

        code = code.replace("кц", "")
        code = code.replace("все", "")
        code = code.replace("всё", "")

        code = code.replace(" не ", " not ")
        code = code.replace(" и ",  " and ")
        code = code.replace(" или ", " or ")

        code = code.replace("закрасить", "robot.paint()")

        code = code.strip().rstrip()
        code = code.replace(") :", "):")

        return code


class Cell:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.walls = {UP: False, RIGHT: False, LEFT: False, DOWN: False}
        self.filled = False

    def set_wall(self, direction):
        self.walls[direction] = True

    def remove_wall(self, direction):
        self.walls[direction] = False


class Field:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.field = [[Cell(i, j) for i in range(self.width)] for j in range(self.height)]

    def get_cell(self, x: int, y: int):
        return self.field[y][x]

    def fill(self, x, y):
        self.get_cell(x, y).filled = True

    def set_wall(self, x, y, direction):
        self.get_cell(x, y).set_wall(direction)
        if direction == UP and y != 0:
            self.get_cell(x, y - 1).set_wall(DOWN)
        if direction == RIGHT and x != self.width - 1:
            self.get_cell(x + 1, y).set_wall(LEFT)
        if direction == LEFT and x != 0:
            self.get_cell(x - 1, y).set_wall(RIGHT)
        if direction == DOWN and y != self.height - 1:
            self.get_cell(x, y + 1).set_wall(UP)

    def remove_wall(self, x, y, direction):
        self.get_cell(x, y).remove_wall(direction)
        if direction == UP and y != 0:
            self.get_cell(x, y - 1).remove_wall(DOWN)
        if direction == RIGHT and x != self.width - 1:
            self.get_cell(x + 1, y).remove_wall(LEFT)
        if direction == LEFT and x != 0:
            self.get_cell(x - 1, y).remove_wall(RIGHT)
        if direction == DOWN and y != self.height - 1:
            self.get_cell(x, y + 1).remove_wall(UP)

    def print_field(self, robot: Robot):
        for i in range(self.height):
            for j in range(self.width):
                if self.field[i][j].filled:
                    print("#", end="")
                    continue
                if robot.x == j and robot.y == i:
                    print("P", end="")
                    continue
                print(".", end="")
            print()


def generate_field(code):
    """5 5
wall 1 1 0
robot 2 2
wall 1 1"""
    code_lines = code.split("\n")
    width, height = map(int, code_lines[0].split())
    field = Field(width, height)
    robot = Robot(field, 0, 0)
    for line in code_lines:
        args = line.split()
        x, y = int(args[1]), int(args[2])
        x, y = x - 1, y - 1
        action = args[0]
        if action == "wall":
            direction = int(args[3])
            field.set_wall(x, y, direction)
        elif action == "robot":
            robot.x = x
            robot.y = y
    return field, robot


def get_field_answer(field):
    ans = ""
    for i in range(field.height):
        for j in range(field.width):
            if field.get_cell(j, i).filled:
                ans += f"{i} {j}\n"
    return ans


if __name__ == "__main__":
    field = Field(8, 8)
    for i in range(4):
        field.set_wall(i, 0, UP)
    for i in range(5, 7):
        field.set_wall(i, 0, UP)
    for i in range(3):
        field.set_wall(6, i, RIGHT)
    for i in range(5, 7):
        field.set_wall(6, i, RIGHT)
    robot = Robot(field, 0, 0)
    code = robot.parse_code_new("""использовать Робот
    алг
    нач
    нц пока не сверху свободно
    закрасить
    вправо
    кц
    нц пока сверху свободно
    вправо
    кц
    нц пока справа свободно
    закрасить 
    вправо
    кц
    нц пока не справа свободно 
    закрасить
    вниз
    кц
    нц пока справа свободно 
    вниз
    кц
    нц пока не справа свободно 
    закрасить
    вниз
    кц
    кон""")
    print(code)
    exec(code)
    field.print_field(robot)