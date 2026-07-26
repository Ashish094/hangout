import json
import logging
import os
from highrise import Position
from highrise.models import User

ROLE_HIERARCHY = ["manager", "admin", "mod", "vip", "public"]

class TeleportManager:
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "teleport_data.json"
        self.positions = self.load_data()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    if "teleports" not in data:
                        migrated = {}
                        for name, pos in data.get("public", {}).items():
                            pos["role"] = "public"
                            migrated[name] = pos
                        for name, pos in data.get("private", {}).items():
                            pos["role"] = "manager"
                            migrated[name] = pos
                        return {"teleports": migrated}
                    return data
            except Exception as e:
                logging.error(f"Error loading teleport data: {e}")
        return {"teleports": {}}

    def save_data(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.positions, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving teleport data: {e}")

    async def get_user_role_level(self, user: User):
        roles = await self.bot.role_manager.get_user_roles(user.username)
        if "Author" in roles or "Manager" in roles:
            return "manager"
        if "Admin" in roles:
            return "admin"
        try:
            priv = await self.bot.highrise.get_room_privilege(user.id)
            if priv.moderator:
                return "mod"
        except Exception:
            pass
        if "VIP" in roles:
            return "vip"
        return "public"

    def can_access(self, user_role: str, required_role: str) -> bool:
        if required_role not in ROLE_HIERARCHY:
            required_role = "public"
        user_idx = ROLE_HIERARCHY.index(user_role) if user_role in ROLE_HIERARCHY else len(ROLE_HIERARCHY)
        req_idx = ROLE_HIERARCHY.index(required_role)
        return user_idx <= req_idx

    async def handle_command(self, user: User, message: str):
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()
        location_name = cmd[1:]

        teleports = self.positions.get("teleports", {})

        if location_name in teleports:
            tele = teleports[location_name]
            required_role = tele.get("role", "public")
            user_role = await self.get_user_role_level(user)
            if self.can_access(user_role, required_role):
                pos = Position(tele["x"], tele["y"], tele["z"], tele["facing"])
                await self.bot.highrise.teleport(user.id, pos)
            else:
                role_display = required_role.capitalize()
                await self.bot.highrise.send_whisper(user.id, f"🔒 This teleport requires {role_display} or above.")
            return

        if cmd == "!create" and len(parts) >= 3 and parts[1].lower() == "tele":
            if not await self.bot.role_manager.is_author(user) and \
               not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only Author/Manager can create teleports.")
                return

            if len(parts) >= 4:
                pos_name = parts[2].lower()
                role_input = parts[3].lower()
            else:
                pos_name = parts[2].lower()
                role_input = "public"

            if role_input not in ROLE_HIERARCHY:
                roles_str = ", ".join(ROLE_HIERARCHY)
                await self.bot.highrise.send_whisper(user.id, f"❌ Invalid role. Use: {roles_str}")
                return

            user_pos = await self.get_user_position(user.id)
            if not user_pos:
                await self.bot.highrise.send_whisper(user.id, "❌ Could not get your position.")
                return

            teleports[pos_name] = {
                "x": user_pos.x,
                "y": user_pos.y,
                "z": user_pos.z,
                "facing": user_pos.facing,
                "role": role_input
            }
            self.positions["teleports"] = teleports
            self.save_data()

            role_label = role_input.capitalize()
            await self.bot.highrise.send_whisper(
                user.id,
                f"✅ Teleport '{pos_name}' created!\n"
                f"🔒 Access: {role_label} and above\n"
                f"Usage: !{pos_name}"
            )

        elif cmd == "!deltele" and len(parts) >= 2:
            if not await self.bot.role_manager.is_author(user) and \
               not await self.bot.role_manager.has_role(user.username, "Manager"):
                await self.bot.highrise.send_whisper(user.id, "❌ Only Author/Manager can delete teleports.")
                return

            pos_name = parts[1].lower()
            if pos_name in teleports:
                del teleports[pos_name]
                self.positions["teleports"] = teleports
                self.save_data()
                await self.bot.highrise.send_whisper(user.id, f"✅ Teleport '{pos_name}' deleted!")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ Teleport '{pos_name}' not found.")

        elif cmd == "!tele" and len(parts) == 2:
            pos_name = parts[1].lower()
            if pos_name not in teleports:
                await self.bot.highrise.send_whisper(user.id, f"❌ Teleport '{pos_name}' not found.")
                return
            tele = teleports[pos_name]
            required_role = tele.get("role", "public")
            user_role = await self.get_user_role_level(user)
            if self.can_access(user_role, required_role):
                pos = Position(tele["x"], tele["y"], tele["z"], tele["facing"])
                await self.bot.highrise.teleport(user.id, pos)
                await self.bot.highrise.send_whisper(user.id, f"🚀 Teleported to {pos_name}")
            else:
                role_display = required_role.capitalize()
                await self.bot.highrise.send_whisper(user.id, f"🔒 This teleport requires {role_display} or above.")

        elif cmd == "!tele" and len(parts) >= 3:
            if not await self.bot.moderation_manager.has_mod_permission(user):
                await self.bot.highrise.send_whisper(user.id, "❌ No permission.")
                return
            target_username = parts[1].replace("@", "")
            pos_name = parts[2].lower()
            target_user = await self.get_user_by_username(target_username)
            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return
            if pos_name not in teleports:
                await self.bot.highrise.send_whisper(user.id, f"❌ Teleport '{pos_name}' not found.")
                return
            tele = teleports[pos_name]
            pos = Position(tele["x"], tele["y"], tele["z"], tele["facing"])
            await self.bot.highrise.teleport(target_user.id, pos)
            await self.bot.highrise.send_whisper(user.id, f"🚀 Teleported @{target_username} to {pos_name}")

        elif cmd == "!listtele":
            if not teleports:
                await self.bot.highrise.send_whisper(user.id, "📍 No teleports saved yet.")
                return
            user_role = await self.get_user_role_level(user)
            lines = []
            for name, tele in teleports.items():
                required = tele.get("role", "public")
                lock = "🔓" if self.can_access(user_role, required) else "🔒"
                lines.append(f"{lock} !{name} — {required.capitalize()} +")
            await self.bot.highrise.send_whisper(user.id, "📍 Teleports:\n" + "\n".join(lines))

        elif cmd == "!follow" and len(parts) == 1:
            if self.bot.following_user_id == user.id:
                self.bot.following_user_id = None
                await self.bot.highrise.send_whisper(user.id, "🚶 Stopped following you.")
            else:
                self.bot.following_user_id = user.id
                await self.bot.highrise.send_whisper(user.id, "🚶 Following you now!")

        elif cmd == "!follow" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                self.bot.following_user_id = target_user.id
                await self.bot.highrise.send_whisper(user.id, f"🚶 Following {target_username} now!")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

        elif cmd == "!unfollow":
            self.bot.following_user_id = None
            await self.bot.highrise.send_whisper(user.id, "🚶 Stopped following.")

        elif cmd == "!summon" and len(parts) >= 2:
            if not await self.bot.moderation_manager.has_mod_permission(user):
                return
            target = parts[1].lower()
            my_pos = await self.get_user_position(user.id)
            if not my_pos:
                return
            if target == "all":
                room_users = await self.bot.highrise.get_room_users()
                for u, _ in room_users.content:
                    if u.id != self.bot.highrise.my_id:
                        await self.bot.highrise.teleport(u.id, my_pos)
            else:
                target_username = target.replace("@", "")
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    await self.bot.highrise.teleport(target_user.id, my_pos)
                else:
                    await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

        elif cmd == "!swap" and len(parts) >= 2:
            if not await self.bot.moderation_manager.has_mod_permission(user):
                return
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return
            my_pos = await self.get_user_position(user.id)
            target_pos = await self.get_user_position(target_user.id)
            if my_pos and target_pos:
                await self.bot.highrise.teleport(user.id, target_pos)
                await self.bot.highrise.teleport(target_user.id, my_pos)

    async def get_user_position(self, user_id):
        room_users = await self.bot.highrise.get_room_users()
        for u, pos in room_users.content:
            if u.id == user_id:
                return pos
        return None

    async def get_user_by_username(self, username):
        room_users = await self.bot.highrise.get_room_users()
        for u, _ in room_users.content:
            if u.username.lower() == username.lower():
                return u
        return None
