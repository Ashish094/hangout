class SwitchRoomSignal(Exception):
    def __init__(self, room_id):
        self.room_id = room_id
