import json


UP, RIGHT, LEFT, DOWN = 0, 1, 2, 3


class MoveError(Exception):
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

    def parse_code(self, code):
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

        # Логическое
        code = code.replace(" не ", " not ")
        code = code.replace(" и ", " and ")
        code = code.replace(" или ", " or ")

        # Закрашивание
        code = code.replace("закрасить", "robot.paint()")

        # Циклы и условия (индентация)
        new_code = """"""
        current_indentation_level = 0
        for line in code.split("\n"):
            new_code += "\t" * current_indentation_level + line + "\n"
            if "нц" in line or "если" in line:
                current_indentation_level += 1
            if "кц" in line or "все" in line or "всё" in line:
                current_indentation_level -= 1
        code = new_code

        # Условия
        code = code.replace("если", "if")
        code = code.replace("то", ":")
        code = code.replace("все", "")
        code = code.replace("всё", "")

        # Циклы
        code = code.replace("нц пока", "while")
        code = code.replace("кц", "")
        new_code = ""
        for i in code.split("\n"):
            if "while" in i:
                new_code += i.rstrip(" ") + ":\n"
                continue
            new_code += i + "\n"
        code = new_code

        # Индентация
        code = code.strip("\n").rstrip("\n")

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
    def __init__(self, string: str):
        data = json.loads(string)
        self.width = data["field_size_columns"]
        self.height = data["field_size_rows"]
        self.field = [[Cell(i, j) for i in range(self.width)] for j in range(self.height)]
        for wall in data["walls"]:
            x, y, direction = wall
            self.set_wall(x, y, direction)

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


if __name__ == "__main__":
    # Example
    field = Field(string='{"field_size_rows": 10, "field_size_columns": 10, "robot_pos_x": 5, "robot_pos_y": 5, "walls": [[1, 1, 1]]}')
    field.print_field()