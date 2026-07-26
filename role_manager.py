import json
import logging
import os
from highrise.models import User, RoomPermissions

class RoleManager:
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "roles_data.json"
        self.AUTHOR_USERNAMES = ["chief._", "1.tobi.1"]
        self.user_roles = self.load_data()

    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading roles data: {e}")
        return {"Manager": [], "Admin": [], "VIP": []}

    def save_data(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.user_roles, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving roles data: {e}")

    async def is_author(self, user: User):
        return user.username.lower() in self.AUTHOR_USERNAMES

    async def get_user_roles(self, username):
        username_lower = username.lower()
        if username_lower in self.AUTHOR_USERNAMES:
            return ["Author", "Manager", "Admin", "VIP"]

        roles = []
        for role, users in self.user_roles.items():
            if username_lower in [u.lower() for u in users]:
                roles.append(role)
        return roles

    async def has_role(self, username, role_name):
        roles = await self.get_user_roles(username)
        return role_name in roles or "Author" in roles

    async def promote_user(self, username, role):
        username_lower = username.lower()
        role = role.capitalize()
        if role in self.user_roles:
            if username_lower not in self.user_roles[role]:
                self.user_roles[role].append(username_lower)
                self.save_data()
                return True
        return False

    async def handle_command(self, user: User, message: str):
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()

        if cmd == "!roles":
            user_roles = await self.get_user_roles(user.username)
            is_author = "Author" in user_roles
            def get_status(role):
                return "🔐" if (is_author or role in user_roles) else "🔒"
            response = f"\nManager {get_status('Manager')}\nAdmin {get_status('Admin')}\nVIP {get_status('VIP')}"
            await self.bot.highrise.send_whisper(user.id, response)

        elif cmd == "!role" and len(parts) >= 2 and parts[1].lower() == "list":
            roles_to_check = ["Manager", "Admin", "VIP"]
            response = "👥 Role Lists:\n"
            for role in roles_to_check:
                users = self.user_roles.get(role, [])
                if users:
                    response += f"• {role}: {', '.join(users)}\n"
                else:
                    response += f"• {role}: None\n"
            await self.bot.highrise.send_whisper(user.id, response)

        elif cmd == "!promote" and len(parts) >= 3:
            if not await self.is_author(user):
                return
            target_username = parts[1].replace("@", "").lower()
            role = parts[2].capitalize()
            if role in self.user_roles:
                if target_username in self.user_roles[role]:
                    await self.bot.highrise.send_whisper(user.id, f"⚠️ {target_username} already has {role}.")
                else:
                    self.user_roles[role].append(target_username)
                    self.save_data()
                    await self.bot.highrise.send_whisper(user.id, f"✅ Promoted {target_username} to {role}.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ Unknown role '{role}'. Use: Manager, Admin, VIP")

        elif cmd == "!demote" and len(parts) >= 2:
            if not await self.is_author(user):
                return
            target_username = parts[1].replace("@", "").lower()
            changed = False
            for role in self.user_roles:
                if target_username in self.user_roles[role]:
                    self.user_roles[role].remove(target_username)
                    changed = True
            if changed:
                self.save_data()
                await self.bot.highrise.send_whisper(user.id, f"✅ Demoted {target_username} from all roles.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ {target_username} has no roles to demote.")

        elif cmd == "!give" and len(parts) >= 3:
            if not await self.is_author(user):
                return
            target_username = parts[1].replace("@", "")
            target_role = parts[2].lower()

            response = await self.bot.highrise.get_room_users()
            target_user = next((u for u, _ in response.content if u.username.lower() == target_username.lower()), None)
            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return

            if target_role == "moderator":
                await self.bot.highrise.change_room_privilege(target_user.id, RoomPermissions(moderator=True))
                await self.bot.highrise.chat(f"✅ @{target_user.username} is now a Room Moderator!")
            elif target_role == "designer":
                await self.bot.highrise.change_room_privilege(target_user.id, RoomPermissions(designer=True))
                await self.bot.highrise.chat(f"✅ @{target_user.username} is now a Room Designer!")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ Unknown privilege '{target_role}'. Use: moderator, designer")

        elif cmd == "!remove" and len(parts) >= 3:
            if not await self.is_author(user):
                return
            target_username = parts[1].replace("@", "")
            target_role = parts[2].lower()

            response = await self.bot.highrise.get_room_users()
            target_user = next((u for u, _ in response.content if u.username.lower() == target_username.lower()), None)
            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return

            if target_role == "moderator":
                await self.bot.highrise.change_room_privilege(target_user.id, RoomPermissions(moderator=False))
                await self.bot.highrise.chat(f"✅ @{target_username} removed from Room Moderator.")
            elif target_role == "designer":
                await self.bot.highrise.change_room_privilege(target_user.id, RoomPermissions(designer=False))
                await self.bot.highrise.chat(f"✅ @{target_username} removed from Room Designer.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ Unknown privilege '{target_role}'. Use: moderator, designer")