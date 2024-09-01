# ----- Imports ---- #
import discord
import json
import os
import requests
import re
import chat_exporter
import io

# ----- From imports ----- #
from datetime import datetime, timedelta, timezone
from discord.ext import commands, tasks
from discord.ui import Modal, TextInput, View, Button

# ----- Config -----#
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

# ----- Bot variables ----- #
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# ----- Json loading ----- #
def load_json(file):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

def format_color(color):
    if color.startswith('#'):
        color = '0x' + color[1:]
    elif not color.startswith('0x'):
        color = '0x' + color
    return int(color, 16)

embed_color = format_color(config["EMBED_COLOR"])

def create_embed(title, description, color=embed_color):
    return discord.Embed(
        title=title,
        description=description,
        color=color
    ).set_thumbnail(url=config["THUMBNAIL_URL"]).set_footer(
        text=f"{config['FOOTER']} • {datetime.now().strftime('%H:%M:%S')}",
        icon_url=config["THUMBNAIL_URL"]
    )

def is_admin_or_owner():
    def predicate(ctx):
        return ctx.author.guild_permissions.administrator or ctx.author.id == config['OWNER_ID']
    return commands.check(predicate)

def extract_warranty_duration(title):
    match = re.search(r'(\d+\s*[mdy]|lifetime)', title.lower())
    if match:
        duration = match.group(0).strip()
        if duration == 'lifetime':
            return "150y" # Or any special handling needed
        return duration
    return None


class ReplaceModal(Modal):
    def __init__(self):
        super().__init__(title="Replacement Request")
        self.order_id = TextInput(label="Order ID", placeholder="Enter the Order ID", required=True)
        self.email = TextInput(label="Delivery Email", placeholder="Enter the delivery email used to pay", required=True)
        self.add_item(self.order_id)
        self.add_item(self.email)

    async def on_submit(self, interaction: discord.Interaction):
        order_id = self.order_id.value
        email = self.email.value

        await interaction.response.defer(ephemeral=True)

        try:
            headers = {
                'Authorization': f'Bearer {config["SELLIX_API_KEY"]}',
                'Content-Type': 'application/json',
            }
            url = f'https://dev.sellix.io/v1/orders/{order_id}'
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 404:
                    error_embed = create_embed("Error", f"**The order ID `{order_id}` was not found.** Please check the order ID and try again.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                order_data = response_data.get('data', {}).get('order', {})
                product_title = order_data.get('product_title', 'Unknown Product')
                product_id = order_data.get('uniqid', 'Unknown ID')
                quantity = order_data.get('quantity', 'Unknown Quantity')
                total_price = float(order_data.get('total', 0.0))
                currency = order_data.get('currency', '$')
                stored_email = order_data.get('customer_email', '')

                created_at_timestamp = order_data.get('created_at')
                completed_at = datetime.fromtimestamp(created_at_timestamp, tz=timezone.utc)

                if email.lower() != stored_email.lower():
                    error_embed = create_embed("Email Mismatch", f"**The provided email `{email}` does not match the one used to pay** for the order ID `{order_id}`.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                review_url = 'https://dev.sellix.io/v1/feedback'
                review_response = requests.get(review_url, headers=headers)

                if review_response.status_code == 200:
                    feedback_data = review_response.json().get('data', {}).get('feedback', [])
                    five_star_review = any(feedback.get('invoice_id') == order_id and feedback.get('score') == 5 for feedback in feedback_data)
                else:
                    five_star_review = False

                vouch_channel = interaction.guild.get_channel(int(config["VOUCH_CHANNEL_ID"]))
                if not vouch_channel:
                    error_embed = create_embed("Error", "Vouch channel not found.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                vouch_found = False
                async for message in vouch_channel.history(limit=1000):
                    if message.author == interaction.user and f"<@{config['OWNER_ID']}>" in message.content:
                        vouch_content = message.content.lower()
                        vouch_price_match = re.search(r'\$\d+(\.\d{1,2})?', vouch_content)
                        if vouch_price_match:
                            vouch_price = float(vouch_price_match.group()[1:])
                            if abs(vouch_price - total_price) <= 1.0:
                                vouch_words = vouch_content.split()
                                title_words = product_title.lower().split()
                                matches = [word for word in title_words if word in vouch_words]
                                if len(matches) >= 2:
                                    vouch_found = True
                                    break

                if not vouch_found and not five_star_review:
                    error_embed = create_embed("Action Required", f"You did not vouch or leave a 5-star review on Sellix. Please do both within 24 hours to activate your warranty:\n\n"
                                                                   f"1. **Vouch** with the following message in the designated channel:\n"
                                                                   f"```+rep <@{config['OWNER_ID']}> {product_title} {quantity}x ${total_price}```\n"
                                                                   f"2. **Leave a 5-star review** [here](https://{config['SHOP_LINK']}/invoice/{order_id})", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return
                elif not vouch_found:
                    error_embed = create_embed("Vouch Required", f"You left a 5-star review on Sellix, but did not vouch in the proper format. "
                                                                 f"Please vouch with the following message within 24 hours to activate your warranty:\n\n"
                                                                 f"```+rep <@{config['OWNER_ID']}> {product_title} {quantity}x ${total_price}```\n", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return
                elif not five_star_review:
                    error_embed = create_embed("Review Required", f"You vouched in the proper format, but did not leave a 5-star review on Sellix. "
                                                                  f"Please leave a 5-star review within 24 hours to activate your warranty:\n\n"
                                                                  f"[Leave a 5-star review](https://{config['SHOP_LINK']}/invoice/{order_id})", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                warranty_duration = extract_warranty_duration(product_title)
                if not warranty_duration:
                    error_embed = create_embed("Error", "Could not determine warranty duration for this product.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                duration_amount, duration_type = int(warranty_duration[:-1]), warranty_duration[-1]
                now = datetime.now(timezone.utc)
                if duration_type == 'd':
                    warranty_end = completed_at + timedelta(days=duration_amount)
                elif duration_type == 'm':
                    warranty_end = completed_at + timedelta(days=duration_amount * 30)
                elif duration_type == 'y':
                    warranty_end = completed_at + timedelta(days=duration_amount * 365)
                else:
                    warranty_end = completed_at

                if now > warranty_end:
                    error_embed = create_embed("Warranty Expired", f"Your warranty for the order ID `{order_id}` has expired. Warranty duration was `{warranty_duration}` and the order was completed on `{completed_at.strftime('%Y-%m-%d %H:%M:%S')}`.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                embed = discord.Embed(
                    title="Replacement Request",
                    description=f"<:shield:1272633951151718410> **Order ID:** `{order_id}`\n <:user:1263827156723826770> **User:** {interaction.user.mention}",
                    color=embed_color
                )
                embed.add_field(name="<:world:1263827158397227061> Product", value=product_title, inline=False)
                embed.add_field(name="<:tool:1263827165737254933> Quantity", value=f"{quantity}x", inline=False)
                embed.add_field(name="<:check:1263827108581605427> Total Price", value=f"{total_price} {currency}", inline=False)
                embed.set_thumbnail(url=config["THUMBNAIL_URL"])
                embed.set_image(url=config["IMAGE_URL"])
                embed.set_footer(text=f" Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

                ticket_channel_name = f"🔁〢pending-{order_id}"
                existing_channel = discord.utils.get(interaction.guild.channels, name=ticket_channel_name)

                if existing_channel:
                    error_embed = create_embed("Ticket Exists", f"A ticket for Order ID `{order_id}` already exists: {existing_channel.mention}", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                ticket_category = discord.utils.get(interaction.guild.categories, id=int(config["TICKET_CATEGORY_ID"]))
                if not ticket_category:
                    error_embed = create_embed("Error", "Ticket category not found.", discord.Color.red())
                    await interaction.followup.send(embed=error_embed, ephemeral=True)
                    return

                ticket_channel = await ticket_category.create_text_channel(
                    ticket_channel_name,
                    overwrites={
                        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        interaction.user: discord.PermissionOverwrite(read_messages=True),
                        interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
                        interaction.guild.get_member(config["OWNER_ID"]): discord.PermissionOverwrite(read_messages=True)
                    }
                )

                tickets = load_json(config["TICKET_DIR"])
                tickets[order_id] = {
                    "channel_id": ticket_channel.id,
                    "user_id": interaction.user.id,
                    "order_id": order_id,
                    "product": product_title,
                    "quantity": quantity,
                    "total_price": total_price,
                    "currency": currency,
                    "created_at": created_at_timestamp
                }
                save_json(config["TICKET_DIR"], tickets)

                await ticket_channel.send(embed=embed)

                owner = interaction.guild.get_member(config["OWNER_ID"])
                ping_message = await ticket_channel.send(f"{owner.mention}")
                await ping_message.delete()

                success_embed = create_embed("Ticket Created", f"Your ticket has been created: {ticket_channel.mention}")
                await interaction.followup.send(embed=success_embed, ephemeral=True)

            else:
                error_embed = create_embed("Error", "An unexpected error occurred while checking the order ID. Please try again later.", discord.Color.red())
                await interaction.followup.send(embed=error_embed, ephemeral=True)

        except discord.errors.NotFound:
            print("Interaction expired before response could be sent.")
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            error_embed = create_embed("Error", f"An unexpected error occurred: {str(e)}", discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True)

class ReplaceView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Replacement", emoji="🔁", style=discord.ButtonStyle.primary, custom_id="replace_button")
    async def replace_button_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ReplaceModal())

@bot.command()
@is_admin_or_owner()
async def replace_message(ctx):
    replace_channel = bot.get_channel(int(config["REPLACE_CHANNEL_ID"]))
    if replace_channel:
        async for message in replace_channel.history(limit=100):
            if message.author == bot.user:
                await message.delete()

        view = ReplaceView()
        embed = create_embed("Replacement System", "Click the button below to request a replacement.")
        embed.set_image(url=config["IMAGE_URL"])
        await replace_channel.send(embed=embed, view=view)

@bot.command()
@is_admin_or_owner()
async def help(ctx, command_name: str = None):
    try:
        if command_name and command_name.lower() == "set":
            embed = create_embed(".set Command Help", "Usage and details for the `.set` command").add_field(
                name=".set token <value>", value="Set the bot token.", inline=False
            ).add_field(
                name=".set owner_id <value>", value="Set the owner ID.", inline=False
            ).add_field(
                name=".set image_url <value>", value="Set the image URL used in embeds.", inline=False
            ).add_field(
                name=".set thumbnail_url <value>", value="Set the thumbnail URL used in embeds.", inline=False
            ).add_field(
                name=".set footer <value>", value="Set the footer text used in embeds.", inline=False
            ).add_field(
                name=".set bot_status <value>", value="Set the bot status text.", inline=False
            ).add_field(
                name=".set embed_color <value>", value="Set the embed color (hex format).", inline=False
            ).add_field(
                name=".set excluded_dir <value>", value="Set the file path for the excluded products list.", inline=False
            ).add_field(
                name=".set product_dir <value>", value="Set the file path for the products JSON file.", inline=False
            ).add_field(
                name=".set replace_channel_id <value>", value="Set the channel id of the replace channel", inline=False
            ).add_field(
                name=".set ticket_category_id <value>", value="Set the category id of the replace tickets", inline=False
            ).add_field(
                name=".set vouch_channel_id <value>", value="Set the vouch channel id", inline=False
            ).add_field(
                name=".set ticket_dir <value>", value="Set the file path for the ticket database", inline=False
            )
            await ctx.send(embed=embed)
        else:
            embed = create_embed("Help", "List of commands and their usage").add_field(
                name=".warr", value="Displays an embed with the warranty duration of all products.", inline=False
            ).add_field(
                name=".create_warr <product_id> <duration>", value="Create a new warranty for a product.", inline=False
            ).add_field(
                name=".stock <product> <file>", value="Saves product to a stock file under stock/<product>.txt", inline=False
            ).add_field(
                name=".replace <user> [amount] <product> [file/string]", value="Sends a replacement embed to a user. It can be sent from stock (using the amount parameter) or a file/string (no amount parameter needed)", inline=False
            ).add_field(
                name=".remove_product <product_id>", value="Removes and excludes a product by its ID in json ", inline=False
            ).add_field(
                name=".set <setting> <value>", value="Set various bot configurations. Use `.set help` for details.", inline=False
            ).add_field(
                name=".replace_message", value="Initiates a replacement request system.", inline=False
            ).add_field(
                name=".help", value="List all available commands", inline=False
            ).add_field(
                name=".check_warr <user> <order_id>", value="Checks if the user has vouched, left a web review, and if their warranty has not expired.",inline=False
)

            await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
async def warr(ctx):
    try:
        products = load_json(config["PRODUCT_DIR"])
        if not products:
            await ctx.send(embed=create_embed("No Products", "There are no products with warranties registered."))
            return

        embeds = []
        embed = create_embed("Warranty Information", "")

        for product_id, product_info in products.items():
            if len(embed.fields) >= 25:
                embeds.append(embed)
                embed = create_embed("Warranty Information (cont.)", "")

            embed.add_field(
                name=f"{product_info['title']}",
                value=f"Warranty Duration: `{product_info['warranty_duration']}`",
                inline=False
            )

        embeds.append(embed)

        for embed in embeds:
            await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
@is_admin_or_owner()
async def create_warr(ctx, product_id: str = None, duration: str = None):
    try:
        if not product_id or not duration:
            raise commands.MissingRequiredArgument(None)

        products = load_json(config["PRODUCT_DIR"])
        product_name = f"Product {product_id}"

        products[product_id] = {
            "title": product_name,
            "warranty_duration": duration
        }
        save_json(config["PRODUCT_DIR"], products)

        embed = create_embed("Warranty Created", f"Warranty for **{product_name}** with duration **{duration}** has been created.")
        embed.set_image(url=config["IMAGE_URL"])
        await ctx.send(embed=embed)
    except commands.MissingRequiredArgument:
        await ctx.send(embed=create_embed("Error", "Missing required arguments. Usage: `.create_warr <product_id> <duration>`", discord.Color.red()))
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
@is_admin_or_owner()
async def stock(ctx, product: str = None, file: discord.Attachment = None):
    try:
        if not product or not file:
            raise commands.MissingRequiredArgument(None)

        stock_folder = os.path.join("stock", f"{product}.txt")
        os.makedirs("stock", exist_ok=True)

        content = await file.read()
        content_str = content.decode('utf-8')

        with open(stock_folder, 'a') as f:
            f.write(content_str + "\n")

        embed = create_embed("Stock Updated", f"Stock for **{product}** has been updated.")
        embed.set_image(url=config["IMAGE_URL"])
        await ctx.send(embed=embed)
    except commands.MissingRequiredArgument:
        await ctx.send(embed=create_embed("Error", "Missing required arguments. Usage: `.stock <product> <file>`", discord.Color.red()))
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
@is_admin_or_owner()
async def transcribe(ctx, user: discord.User = None):
    try:
        if not user:
            await ctx.send(embed=create_embed("Error", "You must mention a user to transcribe their DMs. Usage: `.transcribe @user`", discord.Color.red()))
            return
        
        dm_channel = user.dm_channel
        if dm_channel is None:
            dm_channel = await user.create_dm()
        transcript = await chat_exporter.export(dm_channel, limit=100)

        if transcript is None:
            await ctx.send(embed=create_embed("Error", "Could not export the chat. No messages found or an error occurred.", discord.Color.red()))
            return

        transcript_file = discord.File(io.BytesIO(transcript.encode()), filename=f"{user.name}_transcript.html")
        await ctx.send(file=transcript_file)

    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
@is_admin_or_owner()
async def replace(ctx, user: discord.User = None, amount_or_product: str = None, *args):
    try:
        if not user or not amount_or_product:
            raise commands.MissingRequiredArgument(None)

        try:
            amount = int(amount_or_product)
            product = args[0] if args else None
            additional_content = " ".join(args[1:]) if len(args) > 1 else None
        except ValueError:
            amount = None
            product = amount_or_product
            additional_content = " ".join(args) if args else None

        if not product:
            await ctx.send(embed=create_embed("Error", "Missing product name. Usage: `.replace <user> [amount] <product> [file/string]`", discord.Color.red()))
            return

        if amount is None:
            dm_embed = create_embed("Replacement Order", f"You have received a replacement for **{product}**.").add_field(
                name="Replacement Details", value=f"```{additional_content}```" if additional_content else "No specific replacement details provided.", inline=False
            ).set_image(url=config["IMAGE_URL"])

            try:
                await user.send(embed=dm_embed)

                if ctx.message.attachments:
                    for attachment in ctx.message.attachments:
                        await user.send(file=await attachment.to_file())

                await ctx.send(embed=create_embed("Replacement Sent", f"Replacement for **{product}** sent to {user.mention}."))
            except discord.Forbidden:
                await ctx.send(embed=create_embed("Error", f"Failed to send DM to {user.mention}. The user might have DMs disabled.", discord.Color.red()))
        else:
            product_file = os.path.join("stock", f"{product}.txt")
            if not os.path.exists(product_file):
                await ctx.send(embed=create_embed("Error", f"No stock found for **{product}**.", discord.Color.red()))
                return

            with open(product_file, 'r') as f:
                lines = f.readlines()

            if len(lines) < amount:
                await ctx.send(embed=create_embed("Error", f"Not enough stock available for **{product}**. Only {len(lines)} available.", discord.Color.red()))
                return

            replacement_lines = lines[:amount]
            remaining_lines = lines[amount:]

            with open(product_file, 'w') as f:
                f.writelines(remaining_lines)

            dm_embed = create_embed("Replacement Order", f"You have received **{amount}x {product}** replacement.").set_image(url=config["IMAGE_URL"])

            for line in replacement_lines:
                dm_embed.add_field(name="Replacement", value=f"```{line.strip()}```", inline=False)

            try:
                await user.send(embed=dm_embed)

                if ctx.message.attachments:
                    for attachment in ctx.message.attachments:
                        await user.send(file=await attachment.to_file())

                await ctx.send(embed=create_embed("Replacement Sent", f"Replacement for **{product}** sent to {user.mention}."))
            except discord.Forbidden:
                await ctx.send(embed=create_embed("Error", f"Failed to send DM to {user.mention}. The user might have DMs disabled.", discord.Color.red()))

        tickets = load_json(config["TICKET_DIR"])
        ticket_info = next((info for oid, info in tickets.items() if info['user_id'] == user.id), None)

        if ticket_info:
            ticket_channel_name = f"🔁〢pending-{ticket_info['order_id']}"
            ticket_channel = discord.utils.get(ctx.guild.channels, id=ticket_info['channel_id'])

            if ticket_channel:
                await ticket_channel.delete()
                await ctx.send(embed=create_embed("Ticket Closed", f"The ticket channel `{ticket_channel_name}` has been closed."))

                tickets.pop(ticket_info['order_id'], None)
                save_json(config["TICKET_DIR"], tickets)
            else:
                await ctx.send(embed=create_embed("Error", f"No ticket channel found with the name `{ticket_channel_name}`.", discord.Color.red()))
        else:
            await ctx.send(embed=create_embed("Error", "No ticket found for this user or order ID.", discord.Color.red()))

    except commands.MissingRequiredArgument:
        await ctx.send(embed=create_embed("Error", "Missing required arguments. Usage: `.replace <user> [amount] <product> [file/string]`", discord.Color.red()))
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.command()
@is_admin_or_owner()
async def set(ctx, setting: str = None, *, value: str = None):
    try:
        if not setting or not value:
            raise commands.MissingRequiredArgument(None)

        setting = setting.lower()
        valid_settings = {
            "token": "TOKEN",
            "owner_id": "OWNER_ID",
            "image_url": "IMAGE_URL",
            "thumbnail_url": "THUMBNAIL_URL",
            "footer": "FOOTER",
            "bot_status": "BOT_STATUS",
            "embed_color": "EMBED_COLOR",
            "excluded_dir": "EXCLUDED_DIR",
            "product_dir": "PRODUCT_DIR",
            "replace_channel_id": "REPLACE_CHANNEL_ID",
            "ticket_category_id": "TICKET_CATEGORY_ID",
            "vouch_channel_id": "VOUCH_CHANNEL_ID",
            "ticket_dir": "TICKET_DIR"
        }

        if setting not in valid_settings:
            await ctx.send(embed=create_embed("Error", f"Invalid setting: `{setting}`. Use `.help set` to see valid settings.", discord.Color.red()))
            return

        config_key = valid_settings[setting]

        try:
            if config_key == "embed_color":
                config[config_key] = format_color(value)
            else:
                config[config_key] = value
            save_json('config.json', config)
            await ctx.send(embed=create_embed("Configuration Updated", f"Setting `{config_key}` has been updated to `{value}`."))
        except ValueError:
            await ctx.send(embed=create_embed("Error", f"Invalid value for `{setting}`. Ensure the input is correct.", discord.Color.red()))
    except commands.MissingRequiredArgument:
        await ctx.send(embed=create_embed("Error", "Missing required arguments. Usage: `.set <setting> <value>`", discord.Color.red()))
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))


@bot.command()
@is_admin_or_owner()
async def check_warr(ctx, user: discord.User, order_id: str):
    try:
        headers = {
            'Authorization': f'Bearer {config["SELLIX_API_KEY"]}',
            'Content-Type': 'application/json',
        }
        url = f'https://dev.sellix.io/v1/orders/{order_id}'
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 404:
                await ctx.send(embed=create_embed("Error", f"**The order ID `{order_id}` was not found.** Please check the order ID and try again.", discord.Color.red()))
                return

            order_data = response_data.get('data', {}).get('order', {})
            product_id = order_data.get('product_id')
            product_title = order_data.get('product_title', 'Unknown Product')
            quantity = order_data.get('quantity', 'Unknown Quantity')
            total_price = float(order_data.get('total', 0.0))
            currency = order_data.get('currency', '$')
            stored_email = order_data.get('customer_email', '')

            created_at_timestamp = order_data.get('created_at')
            completed_at = datetime.fromtimestamp(created_at_timestamp, tz=timezone.utc)

            # Load product data
            products = load_json(config["PRODUCT_DIR"])

            if product_id not in products:
                await ctx.send(embed=create_embed("Error", f"Product ID `{product_id}` not found in the product list.", discord.Color.red()))
                return

            # Get warranty duration from product.json
            product_info = products.get(product_id, {})
            warranty_duration = product_info.get('warranty_duration')

            if not warranty_duration:
                await ctx.send(embed=create_embed("Error", "Could not determine warranty duration for this product.", discord.Color.red()))
                return

            duration_amount, duration_type = int(warranty_duration[:-1]), warranty_duration[-1]
            now = datetime.now(timezone.utc)
            if duration_type == 'd':
                warranty_end = completed_at + timedelta(days=duration_amount)
            elif duration_type == 'm':
                warranty_end = completed_at + timedelta(days=duration_amount * 30)
            elif duration_type == 'y':
                warranty_end = completed_at + timedelta(days=duration_amount * 365)
            else:
                warranty_end = completed_at  # Handle lifetime or other cases as needed

            # Check Vouch
            vouch_channel = ctx.guild.get_channel(int(config["VOUCH_CHANNEL_ID"]))
            vouch_found = False
            async for message in vouch_channel.history(limit=1000):
                if message.author == user and f"<@{config['OWNER_ID']}>" in message.content:
                    vouch_content = message.content.lower()
                    vouch_price_match = re.search(r'\$\d+(\.\d{1,2})?', vouch_content)
                    if vouch_price_match:
                        vouch_price = float(vouch_price_match.group()[1:])
                        if abs(vouch_price - total_price) <= 1.0:
                            vouch_words = vouch_content.split()
                            title_words = product_title.lower().split()
                            matches = [word for word in title_words if word in vouch_words]
                            if len(matches) >= 2:
                                vouch_found = True
                                break

            # Check Web Review
            review_url = 'https://dev.sellix.io/v1/feedback'
            review_response = requests.get(review_url, headers=headers)

            if review_response.status_code == 200:
                feedback_data = review_response.json().get('data', {}).get('feedback', [])
                five_star_review = any(feedback.get('invoice_id') == order_id and feedback.get('score') == 5 for feedback in feedback_data)
            else:
                five_star_review = False

            # Intelligent Messaging
            if now > warranty_end:
                await ctx.send(embed=create_embed("Warranty Expired", f"Your warranty for the order ID `{order_id}` has expired. Warranty duration was `{warranty_duration}` and the order was completed on `{completed_at.strftime('%Y-%m-%d %H:%M:%S')}`.", discord.Color.red()))
            elif not vouch_found and not five_star_review:
                await ctx.send(embed=create_embed("Action Required", f"You did not vouch or leave a 5-star review on Sellix. Please do both within 24 hours to activate your warranty:\n\n"
                                                                    f"1. **Vouch** with the following message in the designated channel:\n"
                                                                    f"```+rep <@{config['OWNER_ID']}> {product_title} {quantity}x ${total_price}```\n"
                                                                    f"2. **Leave a 5-star review** [here](https://{config['SHOP_LINK']}/invoice/{order_id})", discord.Color.red()))
            elif not vouch_found:
                await ctx.send(embed=create_embed("Vouch Required", f"You left a 5-star review on Sellix, but did not vouch in the proper format. "
                                                                    f"Please vouch with the following message within 24 hours to activate your warranty:\n\n"
                                                                    f"```+rep <@{config['OWNER_ID']}>  {product_title} {quantity}x ${total_price} ```", discord.Color.red()))
            elif not five_star_review:
                await ctx.send(embed=create_embed("Review Required", f"You vouched in the proper format, but did not leave a 5-star review on Sellix. "
                                                                     f"Please leave a 5-star review within 24 hours to activate your warranty:\n\n"
                                                                     f"[Leave a 5-star review](https://{config['SHOP_LINK']}/invoice/{order_id})", discord.Color.red()))
            else:
                await ctx.send(embed=create_embed("Warranty Valid", f"Your warranty for the order ID `{order_id}` is still valid and will end on `{warranty_end.strftime('%Y-%m-%d %H:%M:%S')}`. Thank you for vouching and leaving a review!"))

        else:
            await ctx.send(embed=create_embed("Error", "An unexpected error occurred while checking the order ID. Please try again later.", discord.Color.red()))

    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An unexpected error occurred: {str(e)}", discord.Color.red()))

@bot.event
async def on_guild_channel_delete(channel):
    try:
        if "🔁〢pending-" in channel.name:
            tickets = load_json(config["TICKET_DIR"])

            ticket_info = next((info for oid, info in tickets.items() if info['channel_id'] == channel.id), None)

            if not ticket_info:
                return

            user = bot.get_user(ticket_info['user_id'])
            if not user:
                return
       
            transcript = await chat_exporter.export(channel, limit=1000) 

            if transcript is None:
                return 

            transcript_file = discord.File(io.BytesIO(transcript.encode()), filename=f"{channel.name}_transcript.html")

            dm_channel = user.dm_channel
            if dm_channel is None:
                dm_channel = await user.create_dm()

            await dm_channel.send(file=transcript_file)
            archive_channel = bot.get_channel(int(config["LOG_CHANNEL_ID"]))
            if archive_channel:
                await archive_channel.send(f"Ticket `{channel.name}` has been closed. Here is the transcript:", file=transcript_file)

            tickets.pop(ticket_info['order_id'], None)
            save_json(config["TICKET_DIR"], tickets)

    except Exception as e:
        print(f"An error occurred during channel deletion handling: {str(e)}")


@tasks.loop(hours=1)
async def scrape_products():
    try:
        headers = {
            'Authorization': f'Bearer {config["SELLIX_API_KEY"]}',
            'Content-Type': 'application/json'
        }
        response = requests.get('https://dev.sellix.io/v1/products', headers=headers)
        if response.status_code == 200:
            fetched_products = response.json().get('data', {}).get('products', [])
            existing_products = load_json(config["PRODUCT_DIR"])
            excluded_products = load_json(config["EXCLUDED_DIR"])

            for product in fetched_products:
                product_id = product.get('uniqid')
                title = product.get('title')
                warranty_duration = extract_warranty_duration(title)

                if product_id not in excluded_products and warranty_duration and product_id not in existing_products:
                    existing_products[product_id] = {
                        'title': title,
                        'warranty_duration': warranty_duration
                    }

            save_json(config["PRODUCT_DIR"], existing_products)
            print('Products updated and saved to products.json')
        else:
            print(f"Failed to fetch products: {response.status_code}")
    except Exception as e:
        print(f"An error occurred during the scraping process: {str(e)}")

@bot.command()
@is_admin_or_owner()
async def remove_product(ctx, product_id: str):
    try:
        products = load_json(config["PRODUCT_DIR"])
        excluded_products = load_json(config["EXCLUDED_DIR"])

        if product_id in products:
            del products[product_id]
            excluded_products.append(product_id)

            save_json(config["PRODUCT_DIR"], products)
            save_json(config["EXCLUDED_DIR"], excluded_products)

            await ctx.send(embed=create_embed("Product Removed", f"Product with ID `{product_id}` has been removed and will not be added back."))
        else:
            await ctx.send(embed=create_embed("Error", f"Product with ID `{product_id}` not found in the list.", discord.Color.red()))
    except Exception as e:
        await ctx.send(embed=create_embed("Error", f"An error occurred: {str(e)}", discord.Color.red()))

@bot.event
async def on_ready():
    bot.add_view(ReplaceView())
    print(f'{bot.user} has connected to Discord!')
    scrape_products.start()
    await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(config["BOT_STATUS"]))

os.makedirs("stock", exist_ok=True)
bot.run(config['TOKEN'])
