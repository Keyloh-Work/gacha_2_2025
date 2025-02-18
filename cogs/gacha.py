import discord
from discord.ext import commands
from discord import app_commands
import csv
import chardet
import random
import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

COOLDOWN = 10.0  # クールダウンが必要なら設定

class PaginatorView(discord.ui.View):
    def __init__(self, data, collected_cards, per_page=20):
        super().__init__(timeout=None)
        self.data = data
        self.collected_cards = collected_cards
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(data) + per_page - 1) // per_page

    def get_page_content(self):
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_content = []
        for item in self.data[start_idx:end_idx]:
            card_no = item["No."]
            title = item["title"]
            chname = item.get("chname", "")  # chnameを取得
            url = item.get("url", "")

            if card_no in self.collected_cards:
                # 取得済みの場合：アイコン + カード番号 + chname + タイトル + [🔗 Link]({url})
                line = f":ballot_box_with_check: **No.{card_no}** {chname} {title} [🔗 Link]({url})"
            else:
                # 未取得の場合：アイコン + カード番号 + chname + タイトル
                line = f":blue_square: **No.{card_no}** {chname} {title}"
            page_content.append(line)

        return page_content

    async def update_message(self, interaction):
        page_content = "\n".join(self.get_page_content())
        embed = discord.Embed(
            title=f"{interaction.user.name}のリスト\nPage {self.current_page + 1}/{self.total_pages}",
            description=page_content
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.danger)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.success)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages - 1
        await self.update_message(interaction)


class ChnamePaginatorView(discord.ui.View):
    """
    キャラ名(chname)ごとにページを分けるビュー
    1キャラ = 1ページ
    """
    def __init__(self, grouped_data, collected_cards):
        """
        grouped_data: [(chname, [items...]), (chname2, [items...]), ...]
        collected_cards: ユーザーが取得したカードNo.のリスト
        """
        super().__init__(timeout=None)
        self.grouped_data = grouped_data
        self.collected_cards = collected_cards
        self.current_index = 0
        self.total_pages = len(grouped_data)

    def build_page_content(self):
        """現在のchnameグループのページ内容を組み立て"""
        chname, items = self.grouped_data[self.current_index]
        lines = []
        for item in items:
            card_no = item["No."]
            title = item["title"]
            url = item.get("url", "")
            if card_no in self.collected_cards:
                line = f":ballot_box_with_check: **No.{card_no}** {title} [🔗 Link]({url})"
            else:
                line = f":blue_square: **No.{card_no}** {title}"
            lines.append(line)
        return chname, lines

    async def update_message(self, interaction: discord.Interaction):
        chname, lines = self.build_page_content()
        description = "\n".join(lines)
        embed = discord.Embed(
            title=f"{chname} のリスト\nPage {self.current_index + 1}/{self.total_pages}",
            description=description
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.danger)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = 0
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index > 0:
            self.current_index -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.success)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index < self.total_pages - 1:
            self.current_index += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = self.total_pages - 1
        await self.update_message(interaction)


class GachaButtonView(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="ガチャを回す！", style=discord.ButtonStyle.primary)
    async def gacha_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        user_id = interaction.user.id
        self.bot.ensure_user_points(user_id)
        points = self.bot.user_points[user_id]
        if points <= 0:
            await interaction.followup.send("ポイントが不足しています。", ephemeral=True)
            return

        # ポイント消費
        self.bot.user_points[user_id] = points - 1
        remaining_points = self.bot.user_points[user_id]

        # エフェメラルメッセージの残りポイント更新
        await interaction.edit_original_response(
            content=f"下のボタンを押してガチャを回してください。\n残りポイント: {remaining_points} pt"
        )

        # 抽選
        url_info = await self.get_random_url(user_id)
        if url_info is None:
            await interaction.followup.send("ガチャデータの読み込みに失敗しました。", ephemeral=True)
            return

        logger.info(f"User {interaction.user.name} (ID: {user_id}) drew card {url_info['no']} - {url_info['title']} (rarity: {url_info['rarity']})")

        # 未取得ならカード追加
        is_new = url_info["no"] not in self.bot.user_cards.get(user_id, [])
        if is_new:
            self.bot.user_cards.setdefault(user_id, []).append(url_info["no"])

        # ガチャ結果をアニメーション風に表示
        await self.animate_embed(interaction, url_info, remaining_points, is_new)

    def add_emoji_to_rarity(self, rarity):
        if rarity == "N":
            return "🌈 N"
        elif rarity == "R":
            return "💫 R 💫"
        elif rarity == "SR":
            return "✨ 🌟 SR 🌟 ✨"
        elif rarity == "SSR":
            return "🎉✨✨👑 SSR 👑✨✨🎉"
        return rarity

    async def get_random_url(self, user_id):
        gacha_data = []
        try:
            with open(self.bot.gacha_data_path, 'rb') as f:
                result = chardet.detect(f.read())
            encoding = result['encoding']
            with open(self.bot.gacha_data_path, newline='', encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    gacha_data.append({
                        "url": row["url"],
                        "chname": row["chname"],
                        "rarity": self.add_emoji_to_rarity(row["rarity"]),
                        "rate": float(row["rate"]),
                        "no": row["No."],
                        "title": row["title"]
                    })
        except FileNotFoundError as e:
            logger.error(f"CSVファイルが見つかりません: {e}")
            return None
        except Exception:
            logger.exception("CSV読み込み中にエラーが発生しました:")
            return None

        if not gacha_data:
            return None

        total_rate = sum(item["rate"] for item in gacha_data)
        random_value = random.uniform(0, total_rate)
        current_rate = 0
        for item in gacha_data:
            current_rate += item["rate"]
            if random_value <= current_rate:
                return item
        return gacha_data[-1]

    async def animate_embed(self, interaction, url_info, remaining_points, is_new):
        message = await interaction.followup.send("ガチャ中…", ephemeral=False)
        await asyncio.sleep(1)
        embed = discord.Embed(title="バレンタインガチャ")
        await message.edit(content=None, embed=embed)
        await asyncio.sleep(1)

        embed.add_field(name="キャラ", value=url_info['chname'], inline=True)
        await message.edit(embed=embed)
        await asyncio.sleep(1)

        embed.add_field(name="レア度", value=url_info['rarity'], inline=True)
        embed.add_field(name="イラストNo.", value=f"No.{url_info['no']}", inline=True)
        if is_new:
            embed.add_field(name="\u200b", value="✨NEW✨", inline=True)
        embed.add_field(name="タイトル", value=url_info['title'], inline=True)
        await message.edit(embed=embed)
        await asyncio.sleep(1)

        embed.add_field(name="URL", value=url_info['url'], inline=False)
        embed.set_image(url=url_info['url'])
        await message.edit(embed=embed)
        await asyncio.sleep(1)

        embed.add_field(name="残りポイント", value=f"**{remaining_points} pt**", inline=False)
        await message.edit(embed=embed)


class GachaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="gacha", description="ガチャを回します")
    async def gacha_cmd(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        now = time.time()
        last_time = self.bot.last_gacha_usage.get(user_id, 0)
        if now - last_time < COOLDOWN:
            remain = int(COOLDOWN - (now - last_time))
            await interaction.response.send_message(
                f"クールダウン中です。あと {remain} 秒お待ちください。",
                ephemeral=True
            )
            return
        self.bot.last_gacha_usage[user_id] = now

        self.bot.ensure_user_points(user_id)

        if isinstance(interaction.channel, discord.Thread) and interaction.channel.name.startswith('gacha-thread-'):
            points = self.bot.user_points[user_id]
            view = GachaButtonView(self.bot, user_id)
            await interaction.response.send_message(
                f"下のボタンを押してガチャを回してください。\n残りポイント: {points} pt",
                view=view,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "このコマンドは専用のガチャスレッド内でのみ使用できます。",
                ephemeral=True
            )

    @app_commands.command(name="creategachathread", description="専用ガチャスレッドを作成します")
    async def create_gacha_thread(self, interaction: discord.Interaction):
        if interaction.channel.name != "gacha-channel":
            await interaction.response.send_message("このコマンドは専用のガチャチャンネルでのみ使用できます。", ephemeral=True)
            return

        existing_thread = discord.utils.get(interaction.channel.threads, name=f'gacha-thread-{interaction.user.name}')
        if existing_thread:
            await interaction.response.send_message("すでにあなたのためのgacha-threadが存在します。", ephemeral=True)
        else:
            gacha_thread = await interaction.channel.create_thread(
                name=f'gacha-thread-{interaction.user.name}',
                type=discord.ChannelType.private_thread,
                auto_archive_duration=10080,
                invitable=False
            )
            await gacha_thread.add_user(interaction.user)
            await gacha_thread.edit(slowmode_delay=10)
            await gacha_thread.send(
                f"{interaction.user.mention}\nここはあなた専用のガチャスレッドです。`/gacha`でガチャボタンが表示されます。\n"
                "それを押すとガチャ結果が表示されます。\n"
                "**注意：このスレッドからは退出しないでください。**"
            )
            await interaction.response.send_message("専用ガチャスレッドを作成しました。", ephemeral=True)

    # /artlistnum: カードNo.順
    @app_commands.command(name="artlistnum", description="取得したカードの一覧をNo.順で表示します")
    async def artlist_num(self, interaction: discord.Interaction):
        self.bot.ensure_user_points(interaction.user.id)
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.name.startswith('gacha-thread-'):
            user_id = interaction.user.id
            collected_cards = self.bot.user_cards.get(user_id, [])
            gacha_data = []
            try:
                with open(self.bot.gacha_data_path, 'rb') as f:
                    result = chardet.detect(f.read())
                encoding = result['encoding']
                with open(self.bot.gacha_data_path, newline='', encoding=encoding) as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        # chnameも取得
                        gacha_data.append({
                            "No.": row["No."],
                            "title": row["title"],
                            "url": row.get("url", ""),
                            "chname": row.get("chname", "")
                        })
            except FileNotFoundError as e:
                logger.error(f"CSVファイルが見つかりません: {e}")
                await interaction.response.send_message("データファイルが見つかりません。管理者に連絡してください。", ephemeral=True)
                return
            except Exception:
                logger.exception("CSV読み込み中にエラーが発生しました:")
                await interaction.response.send_message("内部エラーが発生しました。管理者に連絡してください。", ephemeral=True)
                return

            if not gacha_data:
                await interaction.response.send_message("データが見つかりません。", ephemeral=True)
                return

            # No.順にソート
            def safe_int(x):
                try:
                    return int(x)
                except:
                    return 999999
            gacha_data.sort(key=lambda item: safe_int(item["No."]))

            view = PaginatorView(gacha_data, collected_cards)
            embed = discord.Embed(
                title=f"{interaction.user.name}のリスト(No.順)\nPage 1",
                description="\n".join(view.get_page_content())
            )
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("このコマンドは専用のガチャスレッド内でのみ使用できます。", ephemeral=True)

    # /artlistch: キャラ名ごと
    @app_commands.command(name="artlistch", description="取得したカードをキャラごとにページを分けて表示します")
    async def artlist_ch(self, interaction: discord.Interaction):
        self.bot.ensure_user_points(interaction.user.id)
        if isinstance(interaction.channel, discord.Thread) and interaction.channel.name.startswith('gacha-thread-'):
            user_id = interaction.user.id
            collected_cards = self.bot.user_cards.get(user_id, [])
            gacha_data = []
            try:
                with open(self.bot.gacha_data_path, 'rb') as f:
                    result = chardet.detect(f.read())
                encoding = result['encoding']
                with open(self.bot.gacha_data_path, newline='', encoding=encoding) as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        gacha_data.append({
                            "No.": row["No."],
                            "title": row["title"],
                            "url": row.get("url", ""),
                            "chname": row.get("chname", "")
                        })
            except FileNotFoundError as e:
                logger.error(f"CSVファイルが見つかりません: {e}")
                await interaction.response.send_message("データファイルが見つかりません。管理者に連絡してください。", ephemeral=True)
                return
            except Exception:
                logger.exception("CSV読み込み中にエラーが発生しました:")
                await interaction.response.send_message("内部エラーが発生しました。管理者に連絡してください。", ephemeral=True)
                return

            if not gacha_data:
                await interaction.response.send_message("データが見つかりません。", ephemeral=True)
                return

            # chname でグループ化
            grouped = defaultdict(list)
            for item in gacha_data:
                ch = item["chname"]
                grouped[ch].append(item)

            # chname順にソート
            grouped_data = sorted(grouped.items(), key=lambda x: x[0])  # [(chname, [items...]), ...]

            view = ChnamePaginatorView(grouped_data, collected_cards)
            # 最初のページ
            chname, lines = view.build_page_content()
            description = "\n".join(lines)
            embed = discord.Embed(
                title=f"{interaction.user.name}のリスト(chname順) - {chname}\nPage 1/{view.total_pages}",
                description=description
            )
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("このコマンドは専用のガチャスレッド内でのみ使用できます。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GachaCog(bot))
