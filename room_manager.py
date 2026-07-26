import json
import logging
import os
import asyncio
from datetime import datetime
from highrise.models import User
from switch_signal import SwitchRoomSignal

class RoomManager:
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "room_settings.json"
        self.rooms_file = "rooms.json"
        self.settings = self.load_data()
        self.rooms = self.load_rooms()
        self.chat_counts = {}
        self.loop_msgs = {}

    def load_rooms(self):
        if os.path.exists(self.rooms_file):
            try:
                with open(self.rooms_file, 'r') as f:
                    data = json.load(f)
                    return data.get("rooms", {})
            except Exception as e:
                logging.error(f"Error loading rooms.json: {e}")
        return {}

    def save_rooms(self):
        try:
            with open(self.rooms_file, 'w') as f:
                json.dump({"rooms": self.rooms}, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving rooms.json: {e}")

    def extract_room_id(self, raw):
        from urllib.parse import urlparse, parse_qs
        raw = raw.strip()
        # Standard room URL: highrise.game/room/<id> or high.rs/room/<id>
        if "/room/" in raw:
            return raw.rstrip("/").split("/room/")[-1].split("?")[0].strip()
        # World URL with ownedRoomId param: high.rs/world?id=...&ownedRoomId=<id>
        if "?" in raw:
            try:
                parsed = urlparse(raw)
                params = parse_qs(parsed.query)
                if "ownedRoomId" in params:
                    return params["ownedRoomId"][0].strip()
                if "id" in params:
                    return params["id"][0].strip()
            except Exception:
                pass
        # Plain room ID (no slashes or params)
        return raw.strip()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading room settings: {e}")
        return {
            "join_msg": "",
            "leave_msg": "",
            "vip_join_msg": "",
            "vip_leave_msg": "",
            "mod_join_msg": "",
            "mod_leave_msg": "",
            "loop_messages": []
        }

    def save_data(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving room settings: {e}")

    def parse_duration(self, duration_str):
        duration_str = duration_str.strip().lower()
        try:
            if duration_str.endswith("m"):
                return int(float(duration_str[:-1]) * 60)
            elif duration_str.endswith("s"):
                return int(float(duration_str[:-1]))
            else:
                return int(duration_str)
        except Exception:
            return None

    async def handle_command(self, user: User, message: str):
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()

        is_privileged = await self.bot.moderation_manager.has_mod_permission(user) or \
                        await self.bot.role_manager.is_author(user)

        if cmd == "!lb":
            sorted_users = sorted(self.chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            lb_text = "🏆 Chat Leaderboard:\n"
            for i, (u_id, count) in enumerate(sorted_users):
                uname = self.bot.user_data.users.get(u_id, {}).get("username", u_id)
                lb_text += f"{i+1}. @{uname}: {count} msgs\n"
            await self.bot.highrise.send_whisper(user.id, lb_text)

        elif cmd == "!announcement" and is_privileged:
            text = " ".join(parts[1:])
            if text:
                await self.bot.highrise.chat(f"📢 ANNOUNCEMENT: {text}")

        elif cmd == "!loopmsg" and is_privileged and len(parts) >= 3:
            last_part = parts[-1]
            duration_secs = self.parse_duration(last_part)
            if duration_secs and duration_secs > 0:
                text = " ".join(parts[1:-1])
                if not text:
                    await self.bot.highrise.send_whisper(user.id, "❌ Usage: !loopmsg (message) (120s or 2m)")
                    return
            else:
                text = " ".join(parts[1:])
                duration_secs = 300
            msg_key = text[:20]
            await self.start_loop_msg(msg_key, text, duration_secs)
            await self.bot.highrise.send_whisper(user.id, f"✅ Loop message started every {duration_secs}s: {text[:50]}")

        elif cmd == "!stoploopmsg" and is_privileged:
            if len(parts) >= 2:
                key = " ".join(parts[1:])[:20]
                if key in self.loop_msgs:
                    self.loop_msgs[key]["task"].cancel()
                    del self.loop_msgs[key]
                    await self.bot.highrise.send_whisper(user.id, "✅ Loop message stopped.")
                else:
                    await self.bot.highrise.send_whisper(user.id, "❌ No loop message found with that text.")
            else:
                for key in list(self.loop_msgs.keys()):
                    self.loop_msgs[key]["task"].cancel()
                self.loop_msgs.clear()
                await self.bot.highrise.send_whisper(user.id, "✅ All loop messages stopped.")

        elif cmd == "!spam" and is_privileged and len(parts) >= 2:
            try:
                times = int(parts[-1])
                text = " ".join(parts[1:-1])
                if not text:
                    text = parts[1]
                    times = 5
                for _ in range(min(times, 20)):
                    await self.bot.highrise.chat(text)
                    await asyncio.sleep(0.5)
            except Exception:
                text = " ".join(parts[1:])
                for _ in range(5):
                    await self.bot.highrise.chat(text)
                    await asyncio.sleep(0.5)

        elif cmd == "!setjoin" and is_privileged:
            self.settings["join_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ Join message set.")

        elif cmd == "!setleave" and is_privileged:
            self.settings["leave_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ Leave message set.")

        elif cmd == "!setvipjoin" and is_privileged:
            self.settings["vip_join_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ VIP join message set.")

        elif cmd == "!setvipleave" and is_privileged:
            self.settings["vip_leave_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ VIP leave message set.")

        elif cmd == "!setmodjoin" and is_privileged:
            self.settings["mod_join_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ Mod join message set.")

        elif cmd == "!setmodleave" and is_privileged:
            self.settings["mod_leave_msg"] = " ".join(parts[1:])
            self.save_data()
            await self.bot.highrise.send_whisper(user.id, "✅ Mod leave message set.")

        elif cmd == "!rooms":
            if not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only the Author or Manager can use !rooms.")
                return
            if not self.rooms:
                await self.bot.highrise.send_whisper(user.id, "📋 No saved rooms yet. Use !addroom <name> <url>")
            else:
                lines = ["📋 Saved Rooms:"]
                for name, url in self.rooms.items():
                    lines.append(f"• {name} → {url}")
                await self.bot.highrise.send_whisper(user.id, "\n".join(lines))

        elif cmd == "!addroom" and len(parts) >= 3:
            if not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only the Author or Manager can use !addroom.")
                return
            name = parts[1].lower()
            url = parts[2]
            self.rooms[name] = url
            self.save_rooms()
            await self.bot.highrise.send_whisper(user.id, f"✅ Room '{name}' saved.")

        elif cmd == "!removeroom" and len(parts) >= 2:
            if not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only the Author or Manager can use !removeroom.")
                return
            name = parts[1].lower()
            if name in self.rooms:
                del self.rooms[name]
                self.save_rooms()
                await self.bot.highrise.send_whisper(user.id, f"✅ Room '{name}' removed.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ No room named '{name}' found.")

        elif cmd == "!room" and len(parts) >= 2:
            if not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only the Author or Manager can use !room.")
                return
            raw = parts[1].strip()
            lookup = raw.lower()
            if lookup in self.rooms:
                raw = self.rooms[lookup]
            room_id = self.extract_room_id(raw)
            if not room_id:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid room name, URL or ID.")
                return
            try:
                await self.bot.highrise.send_whisper(user.id, f"🚀 Switching to room {room_id}...")
                await asyncio.sleep(1)
                raise SwitchRoomSignal(room_id)
            except SwitchRoomSignal:
                raise
            except Exception as e:
                logging.error(f"Error switching room: {e}")
                await self.bot.highrise.send_whisper(user.id, f"❌ Could not switch room: {e}")

    async def start_loop_msg(self, msg_key, text, interval_secs):
        if msg_key in self.loop_msgs:
            self.loop_msgs[msg_key]["task"].cancel()
        task = asyncio.create_task(self.loop_msg_task(text, interval_secs))
        self.loop_msgs[msg_key] = {"text": text, "task": task, "interval": interval_secs}

    async def loop_msg_task(self, text, interval_secs):
        try:
            while True:
                await self.bot.highrise.chat(text)
                await asyncio.sleep(interval_secs)
        except asyncio.CancelledError:
            pass

    def increment_chat(self, user_id):
        self.chat_counts[user_id] = self.chat_counts.get(user_id, 0) + 1
