import asyncio
import logging
import random
from datetime import datetime
from highrise import BaseBot, __main__
from highrise.models import (
    User,
    SessionMetadata,
    Position,
    AnchorPosition,
    CurrencyItem,
    Item,
)
from teleport_manager import TeleportManager
from tipping_manager import TippingManager
from role_manager import RoleManager
from bot_settings_manager import BotSettingsManager
from moderation_manager import ModerationManager
from emote_manager import EmoteManager
from user_data_manager import UserDataManager
from room_manager import RoomManager
from getfit_command import GetfitCommand

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class MyBot(BaseBot):
    def __init__(self):
        super().__init__()
        self.teleport_manager = TeleportManager(self)
        self.tipping_manager = TippingManager(self)
        self.role_manager = RoleManager(self)
        self.bot_settings = BotSettingsManager(self)
        self.moderation_manager = ModerationManager(self)
        self.emote_manager = EmoteManager(self)
        self.user_data = UserDataManager(self)
        self.room_manager = RoomManager(self)
        self.getfit = GetfitCommand(self)
        self.following_user_id = None
        self.frozen_users = {}
        self.room_name = "Our Room"

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        try:
            room_info = getattr(session_metadata, "room_info", None)
            if room_info:
                name = getattr(room_info, "room_name", None) or getattr(
                    room_info, "name", None
                )
                if name:
                    self.room_name = name
        except Exception:
            pass

        saved_pos = self.bot_settings.settings.get("bot_position")
        if saved_pos:
            try:
                pos = Position(
                    x=float(saved_pos["x"]),
                    y=float(saved_pos["y"]),
                    z=float(saved_pos["z"]),
                    facing=saved_pos["facing"],
                )
                await self.highrise.teleport(self.highrise.my_id, pos)
            except Exception:
                pass

    async def _process_command(
        self, user: User, message: str, is_dm: bool = False
    ) -> None:
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()

        await self.teleport_manager.handle_command(user, message)
        await self.tipping_manager.handle_command(user, message)
        await self.role_manager.handle_command(user, message)
        await self.bot_settings.handle_command(user, message)
        await self.moderation_manager.handle_command(user, message)
        await self.emote_manager.handle_command(user, message, is_dm=is_dm)
        await self.room_manager.handle_command(user, message)

        if cmd == "!getfit":
            await self.getfit.execute(user, message)

        if cmd in ["!heartall", "!winkall", "!thumbsall", "!waveall", "!clapall"]:
            reaction_map = {
                "!heartall": "heart",
                "!winkall": "wink",
                "!thumbsall": "thumbs",
                "!waveall": "wave",
                "!clapall": "clap",
            }
            reaction_type = reaction_map[cmd]
            try:
                room_users_response = await self.highrise.get_room_users()
                content = getattr(room_users_response, "content", [])
                for u, _ in content:
                    if u.id != self.highrise.my_id:
                        await self.highrise.react(reaction_type, u.id)
                await self.highrise.chat(f"✅ Sending {reaction_type} to everyone!")
            except Exception as e:
                logging.error(f"Error in reaction all command: {e}")

        elif cmd[1:] in ["heart", "wink", "thumbs", "wave", "clap"] and len(parts) >= 3:
            reaction_str = cmd[1:]
            target_username = parts[1].replace("@", "")
            try:
                count = int(parts[2])
                room_users_response = await self.highrise.get_room_users()
                content = getattr(room_users_response, "content", [])
                target_user = next(
                    (
                        u
                        for u, _ in content
                        if u.username.lower() == target_username.lower()
                    ),
                    None,
                )
                if target_user:
                    for _ in range(min(count, 100)):
                        await self.highrise.react(reaction_str, target_user.id)
                        await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"Error in reaction command: {e}")

        elif cmd in ["!heart", "!wink", "!thumbs", "!wave", "!clap"]:
            reaction_str = cmd[1:]
            try:
                await self.highrise.react(reaction_str, user.id)
            except Exception as e:
                logging.error(f"Error in single reaction: {e}")

    async def on_whisper(self, user: User, message: str) -> None:
        try:
            message = str(message).strip()
            if not self.user_data.is_activated(user.id):
                await self.highrise.send_whisper(
                    user.id,
                    "⚠️ Please DM me any message to unlock your Commands Access!",
                )
                return

            if message.startswith("!"):
                await self._process_command(user, message, is_dm=False)
            else:
                await self.emote_manager.handle_command(user, message)
        except SwitchRoomSignal:
            raise
        except Exception as e:
            logging.error(f"Error in on_whisper: {e}")

    async def on_chat(self, user: User, message: str) -> None:
        try:
            message = str(message).strip()
            self.room_manager.increment_chat(user.id)

            if not message.startswith("!"):
                await self.emote_manager.handle_command(user, message)
                return

            if not self.user_data.is_activated(user.id):
                await self.highrise.send_whisper(
                    user.id,
                    "⚠️ Please DM me any message to unlock your Commands Access!",
                )
                return

            await self._process_command(user, message, is_dm=False)

        except SwitchRoomSignal:
            raise
        except Exception as e:
            logging.error(f"Error in on_chat: {e}")

    async def on_user_move(
        self, user: User, destination: Position | AnchorPosition
    ) -> None:
        if user.id in self.frozen_users:
            frozen_pos = self.frozen_users[user.id]
            await self.highrise.teleport(user.id, frozen_pos)
            return

        if self.following_user_id and user.id == self.following_user_id:
            try:
                if isinstance(destination, Position):
                    follow_position = Position(
                        x=destination.x,
                        y=destination.y,
                        z=destination.z - 1.0,
                        facing=destination.facing,
                    )
                    await self.highrise.walk_to(follow_position)
            except Exception as e:
                logging.error(f"Error following user: {e}")

    async def on_user_join(
        self, user: User, position: Position | AnchorPosition
    ) -> None:
        try:
            last_seen_str = self.user_data.get_last_seen_str(user.id)

            welcome_whisper = (
                f"<#FFB6C1>Welcome [👤] <#FFD700>@{user.username} "
                f"<#FFB6C1>to <#FFD700>{self.room_name} <#FF69B4>🎉\n"
                f"<#FFB6C1>Last Seen :- <#FFD700>{last_seen_str}"
            )
            await self.highrise.send_whisper(user.id, welcome_whisper)

            self.user_data.update_last_seen(user.id, user.username)

            if not self.user_data.is_activated(user.id):
                await self.highrise.send_whisper(
                    user.id, "👋 DM me any message to unlock bot commands!"
                )

            # Author join announcement
            if await self.role_manager.is_author(user):
                author_messages = [
                    f"𝙏𝙃𝙀 𝙎𝙐𝙋𝙀𝙍𝙎𝙏𝘼𝙍  @{user.username} 𝗵𝗮𝘀 𝗮𝗿𝗿𝗶𝘃𝗲𝗱! 𝗟𝗲𝘁 𝘁𝗵𝗲 𝗳𝘂𝗻 𝗯𝗲𝗴𝗶𝗻🎉!",
                    f"𝙇𝙤𝙤𝙠 𝙬𝙤'𝙨 𝙝𝙚𝙧𝙚! @{user.username} 𝙝𝙖𝙨 𝙟𝙤𝙞𝙣𝙚𝙙 𝙪𝙨! 𝙇𝙚𝙩'𝙨 𝙩𝙝𝙚 𝙛𝙪𝙣 𝙗𝙚𝙜𝙞𝙣𝙨 😼!",
                    f"@{user.username} 𝙞𝙨 𝙞𝙣 𝙩𝙝𝙚 𝙝𝙤𝙪𝙨𝙚! 𝙏𝙞𝙢𝙚 𝙛𝙤𝙧 𝙨𝙤𝙢𝙚 𝙛𝙪𝙣🥳!",
                    f"𝘼𝙩𝙩𝙚𝙣𝙩𝙞𝙤𝙣 𝙚𝙫𝙚𝙧𝙮𝙤𝙣𝙚! @{user.username} 𝙞𝙨 𝙣𝙤𝙬 𝙞𝙣 𝙩𝙝𝙚 𝙧𝙤𝙤𝙢🤫!",
                    f"𝙏𝙃𝙀 𝙍𝙊𝙊𝙈 𝙄𝙎 𝙎𝙃𝘼𝙆𝙄𝙉𝙂! @{user.username} 𝙄𝙎 𝙄𝙉 𝙏𝙃𝙀 𝙃𝙊𝙐𝙎𝙀🌪️!",
                    f"𝙏𝙃𝙀 𝙋𝙊𝙒𝙀𝙍𝙁𝙐𝙇 @{user.username} 𝙃𝘼𝙎 𝘼𝙍𝙍𝙄𝙑𝙀𝘿! 🚀",
                    f"𝙏𝙃𝙀 𝙍𝙊𝙊𝙈 𝙄𝙎 𝙀𝙇𝙀𝙲𝙏𝙍𝙄𝙁𝙔𝙄𝙉𝙂! @{user.username} 𝙄𝙎 𝙄𝙉 𝙏𝙃𝙀 𝙃𝙊𝙐𝙎𝙀⚡!",
                    f"𝙏𝙃𝙀 𝙎𝙐𝙋𝙀𝙍𝙄𝙊𝙍 @{user.username} 𝙃𝘼𝙎 𝘼𝙍𝙍𝙄𝙑𝙀𝘿! 👑",
                    f"𝙏𝙃𝙀 𝙍𝙊𝙊𝙈 𝙄𝙎 𝙎𝙃𝘼𝙆𝙄𝙉𝙂! @{user.username} 𝙄𝙎 𝙄𝙉 𝙏𝙃𝙀 𝙃𝙊𝙐𝙎𝙀🌪️!",
                    f"👑 𝙏𝙃𝙀 𝙇𝙀𝘿𝙀𝙍 𝙃𝘼𝙎 𝙀𝙉𝙏𝙀𝙍𝙀𝘿! @{user.username} 𝙄𝙎 𝙄𝙉 𝙏𝙃𝙀 𝙃𝙊𝙐𝙎𝙀👑!",
                ]
                await self.highrise.chat(random.choice(author_messages))

        except Exception:
            pass

    async def on_user_leave(self, user: User) -> None:
        try:
            self.user_data.update_last_seen(user.id, user.username)

            roles = await self.role_manager.get_user_roles(user.username)
            is_vip = "VIP" in roles
            is_mod = await self.moderation_manager.has_mod_permission(user)

            leave_msg = self.room_manager.settings.get("leave_msg", "")
            if is_mod:
                leave_msg = self.room_manager.settings.get("mod_leave_msg", "")
            elif is_vip:
                leave_msg = self.room_manager.settings.get("vip_leave_msg", "")

            if leave_msg.strip():
                formatted_msg = leave_msg.replace("{user}", f"@{user.username}")
                await self.highrise.chat(formatted_msg)
        except Exception:
            pass

    async def on_message(
        self, user_id: str, conversation_id: str, is_new_conversation: bool
    ) -> None:
        try:
            username = None
            try:
                room_users = await self.highrise.get_room_users()
                if hasattr(room_users, "content"):
                    user_obj = next(
                        (u for u, _ in room_users.content if u.id == user_id), None
                    )
                    if user_obj:
                        username = user_obj.username
            except Exception:
                pass

            if not username:
                saved = self.user_data.users.get(user_id, {})
                username = saved.get("username") or "User"

            self.user_data.update_user(user_id, username, conversation_id)

            try:
                conv_msgs = await self.highrise.get_messages(conversation_id)
                messages_list = []

                if hasattr(conv_msgs, "messages"):
                    messages_list = list(conv_msgs.messages)
                elif hasattr(conv_msgs, "content"):
                    content = getattr(conv_msgs, "content")
                    if isinstance(content, list):
                        messages_list = content
                    elif hasattr(content, "messages"):
                        messages_list = list(content.messages)
                elif isinstance(conv_msgs, list):
                    messages_list = conv_msgs

                if messages_list:
                    try:
                        messages_list.sort(
                            key=lambda x: getattr(x, "created_at", getattr(x, "id", 0)),
                            reverse=True,
                        )
                    except Exception:
                        pass

                    last_msg_obj = messages_list[0]

                    # Preserve original casing for command arguments
                    last_msg_original = ""
                    if hasattr(last_msg_obj, "content"):
                        last_msg_original = last_msg_obj.content.strip()
                    elif isinstance(last_msg_obj, dict) and "content" in last_msg_obj:
                        last_msg_original = last_msg_obj["content"].strip()

                    last_msg_lower = last_msg_original.lower()

                    user = User(id=user_id, username=username)
                    was_activated = self.user_data.is_activated(user_id)

                    if not was_activated:
                        self.user_data.activate_user(user_id)
                        await self.highrise.send_message(
                            conversation_id, "Verification Is Complete ✅"
                        )
                        return

                    if last_msg_lower in [
                        "hello",
                        "hi",
                        "hey",
                        "hi there",
                        "hii",
                        "helo",
                    ]:
                        await self.highrise.send_message(
                            conversation_id, "You Are Already Verified ✅"
                        )
                        return

                    if last_msg_original.startswith("!"):
                        await self._process_command(user, last_msg_original, is_dm=True)

            except SwitchRoomSignal:
                raise
            except Exception as e:
                logging.error(f"Error reading DM messages: {e}")

        except SwitchRoomSignal:
            raise
        except Exception as e:
            logging.error(f"Error in on_message: {e}")

    async def on_tip(
        self, sender: User, receiver: User, tip: CurrencyItem | Item
    ) -> None:
        try:
            if (
                receiver.id == self.highrise.my_id
                and isinstance(tip, CurrencyItem)
                and tip.amount >= 200
            ):
                if sender.id in self.tipping_manager.vip_purchases:
                    if datetime.now() <= self.tipping_manager.vip_purchases[sender.id]:
                        success = await self.role_manager.promote_user(
                            sender.username, "VIP"
                        )
                        if success:
                            await self.highrise.chat(
                                f"🎉 Thank you @{sender.username}! You are now a VIP!"
                            )
                            del self.tipping_manager.vip_purchases[sender.id]
                        else:
                            await self.highrise.chat(
                                f"❌ Error promoting @{sender.username} to VIP. Please contact Author."
                            )
        except Exception as e:
            logging.error(f"Error in on_tip: {e}")

    async def run(self, room_id, token):
        definitions = [__main__.BotDefinition(self, room_id, token)]
        await __main__.main(definitions)


from switch_signal import SwitchRoomSignal


def find_switch_room(exc):
    if isinstance(exc, SwitchRoomSignal):
        return exc.room_id
    if isinstance(exc, BaseExceptionGroup):
        for e in exc.exceptions:
            result = find_switch_room(e)
            if result:
                return result
    return None


if __name__ == "__main__":
    import os
    import time

    token = os.environ.get("HIGHRISE_TOKEN", "")
    if not token:
        raise ValueError("HIGHRISE_TOKEN environment variable must be set.")

    room_id = os.environ.get("HIGHRISE_ROOM_ID", "")
    if not room_id:
        raise ValueError("HIGHRISE_ROOM_ID environment variable must be set.")

    while True:
        logging.info(f"Starting bot in room: {room_id}")
        try:
            bot = MyBot()
            asyncio.run(bot.run(room_id, token))
        except BaseException as e:
            switch_to = find_switch_room(e)
            if switch_to:
                logging.info(f"Switching to room: {switch_to}")
                room_id = switch_to
            else:
                logging.error(f"Bot crashed: {e}. Restarting in 3s...")
                time.sleep(3)
