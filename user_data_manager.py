import json
import logging
import os
from datetime import datetime

class UserDataManager:
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "users_data.json"
        self.users = self.load_data()
        self.data = {"users": self.users}

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading users data: {e}")
        return {}

    def save_data(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.users, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving users data: {e}")

    def update_user(self, user_id, username, conv_id):
        user_info = self.users.get(user_id, {})
        user_info.update({"username": username, "conv_id": conv_id})
        self.users[user_id] = user_info
        self.save_data()

    def update_last_seen(self, user_id, username, conv_id=None):
        if user_id not in self.users:
            self.users[user_id] = {}
        self.users[user_id]["username"] = username
        self.users[user_id]["last_seen"] = datetime.now().isoformat()
        if conv_id:
            self.users[user_id]["conv_id"] = conv_id
        self.save_data()

    def get_last_seen_str(self, user_id):
        user = self.users.get(user_id, {})
        last_seen = user.get("last_seen")
        if not last_seen:
            return "First Visit!"
        try:
            last_dt = datetime.fromisoformat(last_seen)
            delta = datetime.now() - last_dt
            days = delta.days
            hours = (delta.seconds // 3600)
            mins = (delta.seconds % 3600) // 60
            if days == 0 and hours == 0 and mins < 2:
                return "Just Now"
            parts = []
            if days > 0:
                parts.append(f"{days}D")
            if hours > 0:
                parts.append(f"{hours}H")
            parts.append(f"{mins}M")
            return ", ".join(parts)
        except Exception:
            return "Unknown"

    def activate_user(self, user_id):
        if user_id not in self.users:
            self.users[user_id] = {}
        self.users[user_id]["activated"] = True
        self.save_data()

    def is_activated(self, user_id):
        return self.users.get(user_id, {}).get("activated", False)

    def get_conv_id(self, user_id):
        user_data = self.users.get(user_id)
        return user_data.get("conv_id") if user_data else None
