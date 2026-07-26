import asyncio
import logging
from highrise.models import User

class ModerationManager:
    def __init__(self, bot):
        self.bot = bot

    async def has_mod_permission(self, user: User):
        if await self.bot.role_manager.is_author(user):
            return True

        roles = await self.bot.role_manager.get_user_roles(user.username)
        if "Manager" in roles or "Admin" in roles:
            return True

        try:
            privilege_response = await self.bot.highrise.get_room_privilege(user.id)
            return privilege_response.moderator
        except Exception:
            return False

    async def is_room_owner(self, user: User):
        try:
            room_perms = await self.bot.highrise.get_room_privileges()
            content = room_perms.content if hasattr(room_perms, "content") else room_perms
            for perm in content:
                if perm.user_id == user.id and perm.owner:
                    return True
        except Exception:
            pass
        return False

    async def handle_command(self, user: User, message: str):
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()

        if not await self.has_mod_permission(user):
            return

        # !kick @username
        if cmd == "!kick" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                try:
                    await self.bot.highrise.moderate_room(target_user.id, "kick")
                    await self.bot.highrise.chat(f"👢 @{target_username} has been kicked.")
                except Exception as e:
                    await self.bot.highrise.send_whisper(user.id, f"❌ Kick failed: {e}")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

        # !ban @username (seconds) — seconds optional; omit for permanent
        elif cmd == "!ban" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if not target_user:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
                return
            try:
                seconds = int(parts[2]) if len(parts) >= 3 else None
                await self.bot.highrise.moderate_room(target_user.id, "ban", seconds)
                duration_str = f"for {seconds}s" if seconds else "permanently"
                await self.bot.highrise.chat(f"🚫 @{target_username} has been banned {duration_str}.")
            except ValueError:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid seconds value.")
            except Exception as e:
                await self.bot.highrise.send_whisper(user.id, f"❌ Ban failed: {e}")

        # !mute @username (seconds)
        elif cmd == "!mute" and len(parts) >= 3:
            target_username = parts[1].replace("@", "")
            try:
                seconds = int(parts[2])
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    await self.bot.highrise.moderate_room(target_user.id, "mute", seconds)
                    await self.bot.highrise.chat(f"🔇 @{target_username} has been muted for {seconds}s.")
                else:
                    await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")
            except ValueError:
                await self.bot.highrise.send_whisper(user.id, "❌ Usage: !mute @user (seconds)")

        # !unban — requires user ID (Highrise limitation)
        elif cmd == "!unban" and len(parts) >= 2:
            await self.bot.highrise.send_whisper(user.id, "ℹ️ Unban requires the User ID, not username.")

        # !unmute @username — mute with 1 second to clear the mute (SDK limitation)
        elif cmd == "!unmute" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                try:
                    await self.bot.highrise.moderate_room(target_user.id, "mute", 1)
                    await self.bot.highrise.chat(f"🔊 @{target_username} has been unmuted.")
                except Exception as e:
                    await self.bot.highrise.send_whisper(user.id, f"❌ Unmute failed: {e}")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

        # !freeze @username
        elif cmd == "!freeze" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                room_users = await self.bot.highrise.get_room_users()
                content = getattr(room_users, 'content', [])
                pos = next((p for u, p in content if u.id == target_user.id), None)
                if pos:
                    self.bot.frozen_users[target_user.id] = pos
                    await self.bot.highrise.moderate_room(target_user.id, "mute", 3600)
                    await self.bot.highrise.chat(f"❄️ @{target_username} has been frozen and muted.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

        # !unfreeze @username
        elif cmd == "!unfreeze" and len(parts) >= 2:
            target_username = parts[1].replace("@", "")
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                if target_user.id in self.bot.frozen_users:
                    del self.bot.frozen_users[target_user.id]
                    await self.bot.highrise.moderate_room(target_user.id, "mute", 1)
                    await self.bot.highrise.chat(f"🔥 @{target_username} has been unfrozen and unmuted.")
                else:
                    await self.bot.highrise.send_whisper(user.id, f"⚠️ @{target_username} is not frozen.")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ User @{target_username} not found.")

    async def get_user_by_username(self, username):
        room_users = await self.bot.highrise.get_room_users()
        content = getattr(room_users, 'content', [])
        for u, _ in content:
            if u.username.lower() == username.lower():
                return u
        return None
