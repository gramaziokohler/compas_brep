from __future__ import annotations

from copy import deepcopy

from compas.data import Data


class Brick(Data):
    @property
    def __data__(self):
        return {"name": self.name}

    def __init__(self, name):
        super().__init__()
        self.name = name

    def __repr__(self):
        return f"Brick(name={self.name})"


# Problem scenario
# class BrickStructure(Data):
#     @property
#     def __data__(self) -> dict:
#         return {"width": self.width, "height": self.height, "depth": self.depth}

#     def __init__(self, width, height, depth):
#         super().__init__()
#         self.width = width
#         self.height = height
#         self.depth = depth
#         self.bricks = []
#         self.calculated_brick_names = None

#     def calculate_brick_names(self):
#         self.calculated_brick_names = "-".join([b.name for b in self.bricks if self.bricks])

#     def __repr__(self):
#         return f"BrickStructure(width={self.width}, height={self.height}, depth={self.depth}, brick={self.bricks})"


# ALT #1 - add bricks to __data__ and accept it in __init__
# class BrickStructure(Data):
#     @property
#     def __data__(self) -> dict:
#         return {"width": self.width, "height": self.height, "depth": self.depth, "bricks": self.bricks}

#     def __init__(self, width, height, depth, bricks=None):
#         super().__init__()
#         self.width = width
#         self.height = height
#         self.depth = depth
#         self.bricks = bricks or []
#         self.calculated_brick_names = None

#     def calculate_brick_names(self):
#         self.calculated_brick_names = "-".join([b.name for b in self.bricks if self.bricks])

#     def __repr__(self):
#         return f"BrickStructure(width={self.width}, height={self.height}, depth={self.depth}, brick={self.bricks})"


# ALT #2 - if bricks are internally calculated from data that's owned by BrickStructure (shouln't serialize bricks)
# class BrickStructure(Data):
#     @property
#     def __data__(self) -> dict:
#         return {"width": self.width, "height": self.height, "depth": self.depth}

#     @classmethod
#     def __from_data__(cls, data):
#         instance = cls(**data)

#         instance.create_bricks()

#         return instance

#     def __init__(self, width, height, depth):
#         super().__init__()
#         self.width = width
#         self.height = height
#         self.depth = depth
#         self.bricks = []
#         self.calculated_brick_names = None

#     def create_bricks(self):
#         pass

#     def calculate_brick_names(self):
#         self.calculated_brick_names = "-".join([b.name for b in self.bricks if self.bricks])

#     def __repr__(self):
#         return f"BrickStructure(width={self.width}, height={self.height}, depth={self.depth}, brick={self.bricks})"


# ALT #3 - if bricks are internally calculated from data that's owned by BrickStructure (shouln't serialize bricks)
class BrickStructure(Data):
    @property
    def __data__(self) -> dict:
        return {"width": self.width, "height": self.height, "depth": self.depth}

    def copy(self, *args, **kwargs):
        instance = BrickStructure(self.width, self.height, self.depth)
        instance.bricks = deepcopy(self.bricks)
        return instance

    def __init__(self, width, height, depth):
        super().__init__()
        self.width = width
        self.height = height
        self.depth = depth
        self.bricks = []
        self.calculated_brick_names = None

    def create_bricks(self):
        pass

    def calculate_brick_names(self):
        self.calculated_brick_names = "-".join([b.name for b in self.bricks if self.bricks])

    def __repr__(self):
        return f"BrickStructure(width={self.width}, height={self.height}, depth={self.depth}, brick={self.bricks})"
