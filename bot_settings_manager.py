import json
import logging
import os
import aiohttp
from urllib.parse import urlparse, parse_qs
from highrise import Position
from highrise.models import User, AnchorPosition, Item

class BotSettingsManager:
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "bot_settings.json"
        self.api_base_url = "https://webapi.highrise.game"
        self.settings = self.load_settings()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Error loading bot settings: {e}")
        return {"bot_position": None, "saved_fits": {}}

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving bot settings: {e}")

    async def handle_command(self, user: User, message: str):
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()
        message_lower = message.lower()

        # !setbot - author/manager only
        if cmd == "!setbot":
            if not (await self.bot.role_manager.is_author(user) or await self.bot.role_manager.has_role(user.username, "Manager")):
                return
            
            room_users_response = await self.bot.highrise.get_room_users()
            user_pos = next((pos for u, pos in room_users_response.content if u.id == user.id), None)
            
            if user_pos and isinstance(user_pos, Position):
                await self.bot.highrise.walk_to(user_pos)
                self.settings["bot_position"] = {
                    "x": user_pos.x, "y": user_pos.y, "z": user_pos.z, "facing": user_pos.facing
                }
                self.save_settings()
                await self.bot.highrise.send_whisper(user.id, "✅ Bot position saved!")

        # !savefit (fit_name)
        elif cmd == "!savefit" and len(parts) >= 2:
            if not await self.bot.role_manager.is_author(user): return
            fit_name = parts[1].lower()
            try:
                my_outfit_resp = await self.bot.highrise.get_my_outfit()
                # Fix for 'GetUserOutfitResponse' object has no attribute 'content'
                outfit_content = getattr(my_outfit_resp, 'outfit', [])
                if not outfit_content:
                    outfit_content = getattr(my_outfit_resp, 'content', [])
                
                # Serializing Item objects to dictionaries for JSON storage
                serialized_outfit = []
                for item in outfit_content:
                    serialized_outfit.append({
                        "type": item.type,
                        "amount": item.amount,
                        "id": item.id,
                        "account_bound": item.account_bound,
                        "active_palette": item.active_palette
                    })
                
                if "saved_fits" not in self.settings:
                    self.settings["saved_fits"] = {}
                self.settings["saved_fits"][fit_name] = serialized_outfit
                self.save_settings()
                await self.bot.highrise.send_whisper(user.id, f"✅ Fit '{fit_name}' saved!")
            except Exception as e:
                logging.error(f"Error saving fit: {e}")
                await self.bot.highrise.send_whisper(user.id, f"❌ Error saving fit: {e}")

        # !removefit (fit_name)
        elif cmd == "!removefit" and len(parts) >= 2:
            if not await self.bot.role_manager.is_author(user): return
            fit_name = parts[1].lower()
            if "saved_fits" in self.settings and fit_name in self.settings["saved_fits"]:
                del self.settings["saved_fits"][fit_name]
                self.save_settings()
                await self.bot.highrise.send_whisper(user.id, f"✅ Fit '{fit_name}' removed!")
            else:
                await self.bot.highrise.send_whisper(user.id, f"❌ Fit '{fit_name}' not found.")

        # !listfit
        elif cmd == "!listfit":
            fits = list(self.settings.get("saved_fits", {}).keys())
            if fits:
                await self.bot.highrise.send_whisper(user.id, f"👗 Saved fits: {', '.join(fits)}")
            else:
                await self.bot.highrise.send_whisper(user.id, "❌ No fits saved.")

        # !(fit_name) - change to saved fit
        elif cmd[1:] in self.settings.get("saved_fits", {}):
            fit_name = cmd[1:]
            fit_data = self.settings["saved_fits"][fit_name]
            try:
                outfit = [Item(type=i["type"], amount=i["amount"], id=i["id"], account_bound=i["account_bound"], active_palette=i.get("active_palette")) for i in fit_data]
                await self.bot.highrise.set_outfit(outfit)
                await self.bot.highrise.chat(f"👗 Changed to fit: {fit_name}")
            except Exception as e:
                logging.error(f"Error changing fit: {e}")

        # !additem (item_id or URL)
        elif cmd == "!additem" and len(parts) >= 2:
            is_privileged = await self.bot.role_manager.is_author(user) or await self.bot.role_manager.has_role(user.username, "Manager")
            if not is_privileged: return
            item_query = parts[1]
            url_type_hint = None

            if "highrise.game/main/items/" in item_query or "highrise.game/items/" in item_query:
                # https://highrise.game/items/<item_id>
                item_id = item_query.split("/")[-1].split("?")[0]
            elif "?" in item_query and ("high.rs" in item_query or "highrise" in item_query):
                # https://high.rs/item?id=<item_id>&type=clothing
                try:
                    params = parse_qs(urlparse(item_query).query)
                    item_id = params.get("id", [item_query])[0].strip()
                    url_type_hint = params.get("type", [None])[0]
                except Exception:
                    item_id = item_query
            else:
                item_id = item_query

            try:
                # Use web API to detect item type and validate existence
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://webapi.highrise.game/items/{item_id}") as resp:
                        item_type = url_type_hint or "clothing"
                        if resp.status == 200:
                            item_data = await resp.json()
                            item_type = item_data.get("item", {}).get("type", item_type)
                        else:
                            logging.warning(f"Item API returned {resp.status} for '{item_id}', using type='{item_type}'")

                my_outfit_resp = await self.bot.highrise.get_my_outfit()
                outfit_content = getattr(my_outfit_resp, 'outfit', None) or getattr(my_outfit_resp, 'content', [])
                current_outfit = list(outfit_content)

                if not current_outfit:
                    logging.warning("!additem: get_my_outfit returned empty outfit — adding item to blank outfit")

                # Remove any existing item with same ID to avoid duplicates
                current_outfit = [i for i in current_outfit if i.id != item_id]
                new_item = Item(type=item_type, amount=1, id=item_id, account_bound=False, active_palette=-1)
                current_outfit.append(new_item)

                await self.bot.highrise.set_outfit(current_outfit)
                await self.bot.highrise.send_whisper(user.id, f"✅ Added {item_type} item: {item_id} (outfit now has {len(current_outfit)} items)")
            except Exception as e:
                logging.error(f"Error in additem: {e}")
                await self.bot.highrise.send_whisper(user.id, f"❌ Error adding item: {e}")

        # !removeitem (item_id or URL)
        elif cmd == "!removeitem" and len(parts) >= 2:
            is_privileged = await self.bot.role_manager.is_author(user) or await self.bot.role_manager.has_role(user.username, "Manager")
            if not is_privileged: return
            item_query = parts[1]
            if "highrise.game/main/items/" in item_query or "highrise.game/items/" in item_query:
                item_id = item_query.split("/")[-1].split("?")[0]
            else:
                item_id = item_query
            
            try:
                my_outfit_resp = await self.bot.highrise.get_my_outfit()
                outfit_content = getattr(my_outfit_resp, 'outfit', None) or getattr(my_outfit_resp, 'content', [])
                current_outfit = list(outfit_content)
                new_outfit = [item for item in current_outfit if item.id != item_id]
                if len(new_outfit) < len(current_outfit):
                    await self.bot.highrise.set_outfit(new_outfit)
                    await self.bot.highrise.send_whisper(user.id, f"✅ Removed item {item_id}!")
                else:
                    await self.bot.highrise.send_whisper(user.id, f"❌ Item {item_id} not found in current outfit.")
            except Exception as e:
                logging.error(f"Error in removeitem: {e}")
                await self.bot.highrise.send_whisper(user.id, f"❌ Error removing item: {e}")
