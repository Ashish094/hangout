import asyncio
import json
import logging
import os
from highrise.models import User

class EmoteManager:
    def __init__(self, bot):
        self.bot = bot
        self.emotes_file = "emotes.json"
        self.emotes = self.load_emotes()
        self.active_loops = {}

    def load_emotes(self):
        if os.path.exists(self.emotes_file):
            try:
                with open(self.emotes_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading emotes: {e}")
        return []

    def save_emotes(self):
        try:
            with open(self.emotes_file, 'w') as f:
                json.dump(self.emotes, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving emotes: {e}")

    async def handle_command(self, user: User, message: str, is_dm=False):
        message = str(message).strip()
        message_lower = message.lower()
        parts = message.split()

        if message.startswith("!"):
            cmd = parts[0].lower()

            if cmd == "!help":
                await self.send_help(user, is_dm)
                return

            if cmd == "!emotelist":
                await self.send_emote_list(user)
                return

            if cmd in ("!addemote", "!removeemote", "!renameemote", "!duration"):
                is_author_manager = await self._is_author_manager(user)
                if not is_author_manager:
                    await self.send_response(user, "❌ Only Author/Manager can use this command.", is_dm)
                    return

                if cmd == "!addemote":
                    if len(parts) < 3:
                        await self.send_response(user, "❌ Usage: !addemote (emote_id) (command name)", is_dm)
                        return
                    emote_id = parts[1]
                    cmd_name = " ".join(parts[2:])
                    existing = next((e for e in self.emotes if e["emote"] == emote_id), None)
                    if existing:
                        await self.send_response(user, f"⚠️ Emote ID '{emote_id}' already exists as '{existing['command']}'.", is_dm)
                        return
                    self.emotes.append({"command": cmd_name, "emote": emote_id, "duration": 5.0, "auth": "public"})
                    self.save_emotes()
                    await self.send_response(user, f"✅ Emote added!\nName: {cmd_name}\nID: {emote_id}", is_dm)

                elif cmd == "!removeemote":
                    if len(parts) < 2:
                        await self.send_response(user, "❌ Usage: !removeemote (number or name)", is_dm)
                        return
                    query = " ".join(parts[1:]).lower()
                    emote = self.find_emote(query)
                    if emote:
                        self.emotes.remove(emote)
                        self.save_emotes()
                        await self.send_response(user, f"✅ Emote '{emote['command']}' removed!", is_dm)
                    else:
                        await self.send_response(user, f"❌ Emote '{query}' not found.", is_dm)

                elif cmd == "!renameemote":
                    if len(parts) < 3:
                        await self.send_response(user, "❌ Usage: !renameemote (number) (new name)", is_dm)
                        return
                    number = parts[1]
                    new_name = " ".join(parts[2:])
                    emote = self.find_emote(number)
                    if emote:
                        old_name = emote["command"]
                        emote["command"] = new_name
                        self.save_emotes()
                        await self.send_response(user, f"✅ Emote #{number} renamed from '{old_name}' to '{new_name}'!", is_dm)
                    else:
                        await self.send_response(user, f"❌ Emote #{number} not found.", is_dm)

                elif cmd == "!duration":
                    if len(parts) < 3:
                        await self.send_response(user, "❌ Usage: !duration (number) (seconds)", is_dm)
                        return
                    try:
                        number = parts[1]
                        duration = float(parts[2])
                        emote = self.find_emote(number)
                        if emote:
                            emote["duration"] = duration
                            self.save_emotes()
                            await self.send_response(user, f"✅ Duration for '{emote['command']}' (#{number}) set to {duration}s!", is_dm)
                        else:
                            await self.send_response(user, f"❌ Emote #{number} not found.", is_dm)
                    except ValueError:
                        await self.send_response(user, "❌ Duration must be a number. Example: !duration 5 3.5", is_dm)
                return

            if cmd in ("!loop", "!stoploop", "!all"):
                is_privileged = await self.bot.moderation_manager.has_mod_permission(user)
                if not is_privileged:
                    return

                if cmd == "!loop" and len(parts) >= 3:
                    target_username = parts[1].replace("@", "")
                    emote_query = " ".join(parts[2:])
                    target_user = await self.get_user_by_username(target_username)
                    if target_user:
                        await self.start_loop(target_user, emote_query)
                        await self.send_response(user, f"✅ Looping '{emote_query}' for @{target_username}", is_dm)
                    else:
                        await self.send_response(user, f"❌ User @{target_username} not found.", is_dm)

                elif cmd == "!stoploop" and len(parts) >= 2:
                    target_username = parts[1].replace("@", "")
                    target_user = await self.get_user_by_username(target_username)
                    if target_user:
                        await self.stop_loop(target_user.id)
                        await self.send_response(user, f"✅ Loop stopped for @{target_username}", is_dm)
                    else:
                        await self.send_response(user, f"❌ User @{target_username} not found.", is_dm)

                elif cmd == "!all" and len(parts) >= 2:
                    emote_query = " ".join(parts[1:])
                    room_users = await self.bot.highrise.get_room_users()
                    if hasattr(room_users, "content"):
                        for u, _ in room_users.content:
                            if u.id != self.bot.highrise.my_id:
                                await self.start_loop(u, emote_query)
                    await self.send_response(user, f"✅ Looping '{emote_query}' for all users", is_dm)
                return

            if cmd in ("!stop", "!0"):
                await self.stop_loop(user.id)
                await self.send_response(user, "✅ Your emote loop stopped.", is_dm)

        else:
            if message_lower == "0":
                await self.stop_loop(user.id)
                return

            if len(parts) >= 2:
                target_username = parts[-1].replace("@", "")
                emote_query = " ".join(parts[:-1])
                target_user = await self.get_user_by_username(target_username)
                if target_user:
                    emote = self.find_emote(emote_query)
                    if emote:
                        await self.bot.highrise.send_emote(emote["emote"], target_user.id)
                        return

            emote = self.find_emote(message_lower)
            if emote:
                await self.start_loop(user, message_lower)

    async def _is_author_manager(self, user):
        roles = await self.bot.role_manager.get_user_roles(user.username)
        return any(r in ("Author", "Manager") for r in roles)

    def find_emote(self, query):
        query = str(query).lower().strip()
        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(self.emotes):
                return self.emotes[idx]
        for e in self.emotes:
            if e["command"].lower() == query:
                return e
        return None

    async def start_loop(self, user, query):
        emote = self.find_emote(query)
        if not emote:
            return
        await self.stop_loop(user.id)
        task = asyncio.create_task(self.loop_task(user.id, emote))
        self.active_loops[user.id] = task

    async def stop_loop(self, user_id):
        if user_id in self.active_loops:
            self.active_loops[user_id].cancel()
            del self.active_loops[user_id]

    async def loop_task(self, user_id, emote):
        try:
            while True:
                await self.bot.highrise.send_emote(emote["emote"], user_id)
                await asyncio.sleep(emote["duration"])
        except asyncio.CancelledError:
            pass

    async def get_user_by_username(self, username):
        room_users = await self.bot.highrise.get_room_users()
        if hasattr(room_users, "content"):
            for u, _ in room_users.content:
                if u.username.lower() == username.lower():
                    return u
        return None

    async def send_help(self, user, is_dm):
        conv_id = self.bot.user_data.get_conv_id(user.id)
        if not conv_id:
            await self.bot.highrise.send_whisper(user.id, "⚠️ DM me any message first to get access!")
            return

        roles = await self.bot.role_manager.get_user_roles(user.username)
        is_privileged = any(r in ("Author", "Manager", "Admin") for r in roles)
        is_high = any(r in ("Author", "Manager") for r in roles)

        categories = []

        cat1 = (
            "🎭 EMOTES\n"
            "• !emotelist — List all emotes\n"
            "• (number) — Loop emote on yourself\n"
            "• (emote) @user — Do emote on user\n"
            "• !stop — Stop your emote loop\n"
            "• 0 — Stop loop (shortcut)"
        )
        if is_privileged:
            cat1 += (
                "\n• !loop @user (emote)\n"
                "• !stoploop @user\n"
                "• !all (emote) — Loop on everyone"
            )
        if is_high:
            cat1 += (
                "\n• !addemote (id) (name)\n"
                "• !removeemote (num/name)\n"
                "• !renameemote (num) (name)\n"
                "• !duration (num) (secs)"
            )
        categories.append(cat1)

        cat2 = (
            "🏠 ROOM & TIPPING\n"
            "• !buyvip — VIP info (Tip 200g)\n"
            "• !lb — Chat Leaderboard\n"
            "• !tipme (amount)\n"
            "• !tip @user (amount)\n"
            "• !tipall (amount)"
        )
        categories.append(cat2)

        if is_privileged:
            cat3 = (
                "🛡️ MODERATION\n"
                "• !kick @user\n"
                "• !ban @user (secs)\n"
                "• !mute @user (secs) / !unmute @user\n"
                "• !freeze @user / !unfreeze @user"
            )
            categories.append(cat3)

            cat4 = (
                "👤 ROLES\n"
                "• !role list\n"
                "• !promote @user (role)\n"
                "• !demote @user"
            )
            categories.append(cat4)

        if is_high:
            cat5 = (
                "⚙️ BOT & FITS\n"
                "• !setbot — Save bot position\n"
                "• !savefit (name)\n"
                "• !listfit / !removefit (name)\n"
                "• (fitname) — Change fit\n"
                "• !getfit @user — Copy user's fit"
            )
            categories.append(cat5)

            cat6 = (
                "💬 COMMUNICATION\n"
                "• !setjoin / !setleave (msg)\n"
                "• !setvipjoin / !setvipleave (msg)\n"
                "• !setmodjoin / !setmodleave (msg)\n"
                "• !loopmsg (message) (120s/2m)\n"
                "• !stoploopmsg — Stop loop msg\n"
                "• !spam (text) (times)\n"
                "• !announcement (text)\n"
                "• !room (url/id) — Move bot to room"
            )
            categories.append(cat6)

            cat7 = (
                "📍 LOCATIONS\n"
                "• !create tele (name) (role)\n"
                "  roles: manager/admin/mod/vip/public\n"
                "• !deltele (name) — Delete teleport\n"
                "• !tele (name) — Use a teleport\n"
                "• !listtele — List all teleports\n"
                "• !summon @user / !summon all\n"
                "• !swap @user"
            )
            categories.append(cat7)

            cat8 = (
                "💎 REACTIONS\n"
                "• !heart / !wink / !wave\n"
                "• !thumbs / !clap\n"
                "• !heartall / !winkall\n"
                "• !waveall / !clapall / !thumbsall\n"
                "• !heart @user (count)"
            )
            categories.append(cat8)

        for cat_msg in categories:
            await self.send_response(user, cat_msg, is_dm=True)
            await asyncio.sleep(0.6)

    async def send_emote_list(self, user):
        conv_id = self.bot.user_data.get_conv_id(user.id)
        if not conv_id:
            await self.bot.highrise.send_whisper(user.id, "⚠️ DM me any message first to get access!")
            return

        total_emotes = len(self.emotes)
        await self.bot.highrise.send_whisper(user.id, f"📋 Sending emote list ({total_emotes} emotes) to your DMs...")

        chunk_size = 15
        for i in range(0, total_emotes, chunk_size):
            chunk = self.emotes[i:i + chunk_size]
            lines = [f"{i+j+1}. {e['command']}" for j, e in enumerate(chunk)]
            if i == 0:
                msg = f"🎭 Emote List (Total: {total_emotes})\n" + "\n".join(lines)
            else:
                msg = "\n".join(lines)
            try:
                await self.bot.highrise.send_message(conv_id, msg)
            except Exception as e:
                logging.error(f"Error sending emote list chunk: {e}")
            await asyncio.sleep(1.0)

    async def send_response(self, user, text, is_dm):
        if is_dm:
            conv_id = self.bot.user_data.get_conv_id(user.id)
            if conv_id:
                try:
                    await self.bot.highrise.send_message(conv_id, text)
                except Exception as e:
                    logging.error(f"Error sending DM: {e}")
                    await self.bot.highrise.send_whisper(user.id, text)
        else:
            await self.bot.highrise.send_whisper(user.id, text)
