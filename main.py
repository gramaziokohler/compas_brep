if __name__ == "__main__":
    from compas.data import json_dumps, json_loads

    from compas_brep.data_example import Brick, BrickStructure

    a, b, c = Brick("a"), Brick("b"), Brick("c")
    structure = BrickStructure(width=10, height=5, depth=3)

    structure.bricks.extend([a, b, c])
    structure.bricks.append(Brick("d"))

    structure.calculate_brick_names()

    print("calculated_brick_names:", structure.calculated_brick_names)

    new_structure = structure.copy()

    # new_structure.calculate_brick_names()
    print("new_structure, calculated_brick_names:", new_structure.bricks)
