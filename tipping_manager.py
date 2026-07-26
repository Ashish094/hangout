import asyncio
import logging
import random
from highrise.models import User, CurrencyItem, Item

class TippingManager:
    def __init__(self, bot):
        self.bot = bot
        self.highrise = None
        self.is_autotip_running = False
        self.autotip_task = None
        self.vip_purchases = {}

        self.TIP_CHARGES = {
            "1": {"cost": 2, "bar": "gold_bar_1"},
            "5": {"cost": 6, "bar": "gold_bar_5"},
            "10": {"cost": 11, "bar": "gold_bar_10"},
            "50": {"cost": 55, "bar": "gold_bar_50"},
            "100": {"cost": 110, "bar": "gold_bar_100"},
            "500": {"cost": 550, "bar": "gold_bar_500"},
            "1000": {"cost": 1100, "bar": "gold_bar_1k"},
            "5000": {"cost": 5500, "bar": "gold_bar_5k"},
            "10000": {"cost": 11000, "bar": "gold_bar_10k"}
        }

    async def handle_command(self, user: User, message: str):
        self.highrise = self.bot.highrise
        if not message.startswith("!"):
            return

        parts = message.split()
        cmd = parts[0].lower()

        if cmd == "!buyvip":
            from datetime import datetime, timedelta
            self.vip_purchases[user.id] = datetime.now() + timedelta(minutes=2)
            await self.bot.highrise.chat(f"💎 @{user.username} Tip 200Gold to the bot within 2 minutes for VIP membership!")
            return

        if cmd in ["!roles", "!assign"]:
            return

        if not (await self.bot.role_manager.is_author(user) or await self.bot.role_manager.has_role(user.username, "Manager")):
            return

        if cmd == "!wallet":
            wallet = await self.bot.highrise.get_wallet()
            amount = wallet.content[0].amount if wallet.content else 0
            await self.bot.highrise.send_whisper(user.id, f"💰 Bot Wallet: {amount} gold")

        elif cmd == "!tipme" and len(parts) >= 2:
            amount_str = parts[1]
            await self.tip_user(user.id, amount_str, user.id)

        elif cmd == "!tip" and len(parts) >= 3 and parts[1].lower() != "random":
            target_username = parts[1].replace("@", "")
            amount_str = parts[2]
            target_user = await self.get_user_by_username(target_username)
            if target_user:
                await self.tip_user(target_user.id, amount_str, user.id)

        elif cmd == "!tipall" and len(parts) >= 2:
            amount_str = parts[1]
            room_users = await self.bot.highrise.get_room_users()
            for u, _ in room_users.content:
                if u.id != self.bot.highrise.my_id:
                    success = await self.tip_user_internal(u.id, amount_str, user.id, silent=True)
                    if success:
                        await self.bot.highrise.chat(f"💰 Tipped {amount_str} @{u.username}")
                        await asyncio.sleep(0.5)
            await self.bot.highrise.chat(f"✅ Tipping all users {amount_str} gold completed!")

        elif cmd == "!tip" and len(parts) >= 3 and parts[1].lower() == "random":
            amount_str = parts[2]
            room_users = await self.bot.highrise.get_room_users()
            users = [u for u, _ in room_users.content if u.id != self.bot.highrise.my_id]
            if users:
                random_users = random.sample(users, min(len(users), 5))
                for u in random_users:
                    await self.tip_user_internal(u.id, amount_str, user.id, silent=True)
                await self.bot.highrise.chat(f"💰 Tipped 5 random users {amount_str} gold!")

        elif cmd == "!autotip" and len(parts) >= 3:
            amount_str = parts[1]
            try:
                seconds = int(parts[2])
                if self.is_autotip_running:
                    self.is_autotip_running = False
                    if self.autotip_task:
                        self.autotip_task.cancel()
                    await self.bot.highrise.send_whisper(user.id, "🛑 Autotip stopped.")
                else:
                    self.is_autotip_running = True
                    self.autotip_task = asyncio.create_task(self.autotip_loop(amount_str, seconds))
                    await self.bot.highrise.send_whisper(user.id, f"🔄 Autotip started every {seconds} seconds.")
            except ValueError:
                await self.bot.highrise.send_whisper(user.id, "❌ Invalid seconds value.")

    async def tip_user(self, target_id: str, amount_str: str, author_id: str, silent=False):
        await self.tip_user_internal(target_id, amount_str, author_id, silent)

    async def tip_user_internal(self, target_id: str, amount_str: str, author_id: str, silent=False):
        if amount_str not in self.TIP_CHARGES:
            if not silent:
                await self.bot.highrise.send_whisper(author_id, f"❌ Invalid amount. Choose: {', '.join(self.TIP_CHARGES.keys())}")
            return False

        charge = self.TIP_CHARGES[amount_str]
        try:
            wallet = await self.bot.highrise.get_wallet()
            bot_balance = wallet.content[0].amount if wallet.content else 0

            if bot_balance < charge["cost"]:
                if not silent:
                    await self.bot.highrise.send_whisper(author_id, f"❌ Insufficient bot balance. Needs {charge['cost']} gold.")
                return False

            await self.bot.highrise.tip_user(target_id, charge["bar"])
            if not silent:
                await self.bot.highrise.chat(f"💰 Tipped {amount_str} gold! (Total cost: {charge['cost']} gold)")
            return True
        except Exception as e:
            logging.error(f"Error tipping: {e}")
            return False

    async def autotip_loop(self, amount_str, seconds):
        while self.is_autotip_running:
            room_users = await self.bot.highrise.get_room_users()
            users = [u for u, _ in room_users.content if u.id != self.bot.highrise.my_id]
            if users:
                target = random.choice(users)
                await self.tip_user(target.id, amount_str, "", silent=True)
            await asyncio.sleep(seconds)

    async def get_user_by_username(self, username):
        room_users = await self.bot.highrise.get_room_users()
        for u, _ in room_users.content:
            if u.username.lower() == username.lower():
                return u
        return None
