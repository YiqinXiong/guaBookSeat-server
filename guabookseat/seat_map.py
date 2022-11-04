import os
import json
from guabookseat.constants import Constants


class SeatMap:
    def __init__(self) -> None:
        self.seat_map_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seat_map.json")
        try:
            with open(self.seat_map_file, 'r') as f:
                self.map = json.load(f)
        except FileNotFoundError:
            self.map = {}
            for content_id in Constants.valid_rooms.keys():
                self.map[str(content_id)] = {}

    def get_map(self):
        return self.map
