import aiohttp
import logging
from typing import Union
from highrise.models import User, Item

logger = logging.getLogger(__name__)


class GetfitCommand:
    def __init__(self, bot):
        self.bot = bot

    @property
    def highrise(self):
        return self.bot.highrise

    async def execute(self, user: User, message: str) -> None:
        roles = await self.bot.role_manager.get_user_roles(user.username)
        if not ("Author" in roles or "Manager" in roles):
            return

        parts = message.split()
        if len(parts) < 2:
            await self.highrise.send_whisper(user.id, "Usage: !getfit <user_id_or_username>")
            return

        target_input = parts[1]

        try:
            user_id = await self.get_user_id_from_username(target_input)

            if not user_id:
                user_id = target_input
                target_username = target_input
            else:
                target_username = target_input

            user_fit = await self.fetch_user_fit(user_id)
            if not user_fit:
                await self.highrise.send_whisper(user.id, f"❌ Could not find fit for @{target_username}")
                return

            await self.equip_fit_items(user, target_username, user_fit)

        except Exception as e:
            logger.error(f"Error in getfit command: {e}")
            await self.highrise.send_whisper(user.id, f"❌ Error getting fit: {str(e)}")

    async def get_user_id_from_username(self, username: str) -> Union[str, None]:
        try:
            room_users = await self.bot.highrise.get_room_users()
            for room_user, _ in room_users.content:
                if room_user.username.lower() == username.lower():
                    return room_user.id
        except Exception as e:
            logger.error(f"Error looking up user: {e}")
        return None

    async def fetch_user_fit(self, user_id: str) -> Union[dict, None]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://webapi.highrise.game/users/{user_id}"
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        logger.error(f"User not found: {user_id}")
                        return None
                    else:
                        logger.error(f"Failed to fetch fit for {user_id}: status {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching user fit: {e}")
            return None

    async def equip_fit_items(self, user: User, target_username: str, user_fit: dict) -> None:
        try:
            outfit_items = []

            if 'user' in user_fit and 'outfit' in user_fit['user']:
                items_data = user_fit['user']['outfit']
                if isinstance(items_data, list):
                    for item_obj in items_data:
                        try:
                            item_id = item_obj.get('item_id') if isinstance(item_obj, dict) else item_obj
                            if item_id:
                                active_palette = item_obj.get('active_palette', -1) if isinstance(item_obj, dict) else -1
                                item = Item(type='clothing', amount=1, id=item_id, account_bound=False, active_palette=active_palette)
                                outfit_items.append(item)
                        except Exception as e:
                            logger.error(f"Error creating item: {e}")

            if not outfit_items:
                await self.highrise.send_whisper(user.id, f"❌ No valid items found in @{target_username}'s fit")
                return

            await self.highrise.set_outfit(outfit=outfit_items)
            await self.highrise.send_whisper(user.id, "Bot is Successfully Changed ✅")

        except Exception as e:
            logger.error(f"Error equipping fit items: {e}")
            await self.highrise.send_whisper(user.id, f"❌ Error equipping fit: {str(e)}")
