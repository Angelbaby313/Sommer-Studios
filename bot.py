import os
import re
import io
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class SommerBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(VerifyView())
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

bot = SommerBot(command_prefix="!", intents=intents)

BRAND = "🎬 Sommer Studios"
TAGLINE = "Development • Design • Digital Creation"
FOOTER = "Sommer Studios • Where Creators Create."

ROLE_OWNER = "🎬 Studio Owner"
ROLE_STAFF = "🎥 Studio Staff"
ROLE_CREATOR = "🎨 Studio Creator"
ROLE_VIP = "⭐ STUDIO VIP"
ROLE_GUEST = "🎟️ Studio Guest"

def pink_embed(title, description="", **kwargs):
    e = discord.Embed(title=title, description=description, color=discord.Color.from_rgb(236, 72, 153), **kwargs)
    e.set_footer(text=FOOTER)
    return e

async def get_or_create_role(guild, name, **kwargs):
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(name=name, **kwargs)
    return role

async def get_or_create_category(guild, name, overwrites=None):
    cat = discord.utils.get(guild.categories, name=name)
    if not cat:
        cat = await guild.create_category(name, overwrites=overwrites or {})
    return cat

async def get_or_create_text(guild, category, name, overwrites=None, topic=None):
    ch = discord.utils.get(guild.text_channels, name=name)
    if not ch:
        ch = await guild.create_text_channel(name, category=category, overwrites=overwrites or {}, topic=topic)
    return ch

async def get_or_create_voice(guild, category, name, overwrites=None):
    ch = discord.utils.get(guild.voice_channels, name=name)
    if not ch:
        ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites or {})
    return ch

def is_management(member):
    names = {r.name for r in member.roles}
    return member.guild_permissions.administrator or ROLE_OWNER in names or ROLE_STAFF in names

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Sommer Studios", emoji="🎟️", style=discord.ButtonStyle.success, custom_id="sommer:verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = discord.utils.get(interaction.guild.roles, name=ROLE_GUEST)
        if not role:
            return await interaction.response.send_message("Studio Guest role is missing. Please tell Studio Staff.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("You're already checked in to the Studio. 🎬", ephemeral=True)
        await interaction.user.add_roles(role, reason="Sommer Studios verification")
        await interaction.response.send_message("🎬 Welcome in! You now have **Studio Guest** access.", ephemeral=True)

class TicketModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title=f"Start a Project • {service[:20]}")
        self.service = service
        self.project = discord.ui.TextInput(label="Tell me what you need", style=discord.TextStyle.paragraph, max_length=1000, required=True)
        self.style = discord.ui.TextInput(label="Theme / colors / style", max_length=300, required=False)
        self.deadline = discord.ui.TextInput(label="Deadline (if any)", max_length=100, required=False)
        self.budget = discord.ui.TextInput(label="Budget / package (if known)", max_length=100, required=False)
        self.refs = discord.ui.TextInput(label="Links / references / extra notes", style=discord.TextStyle.paragraph, max_length=600, required=False)
        for item in (self.project, self.style, self.deadline, self.budget, self.refs):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="🎟️ PROJECT TICKETS")
        if not category:
            return await interaction.response.send_message("Ticket category is missing. Please tell Studio Staff.", ephemeral=True)

        existing = [c for c in category.text_channels if c.topic and f"user:{interaction.user.id}" in c.topic]
        if existing:
            return await interaction.response.send_message(f"You already have an open project: {existing[0].mention}", ephemeral=True)

        owner_role = discord.utils.get(guild.roles, name=ROLE_OWNER)
        staff_role = discord.utils.get(guild.roles, name=ROLE_STAFF)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        slug = re.sub(r"[^a-z0-9-]", "", interaction.user.name.lower().replace(" ", "-"))[:16] or "client"
        channel = await guild.create_text_channel(
            f"project-{slug}",
            category=category,
            overwrites=overwrites,
            topic=f"user:{interaction.user.id} | service:{self.service}"
        )

        embed = pink_embed(
            f"🎬 New Project • {self.service}",
            f"Welcome {interaction.user.mention}! Your Sommer Studios project request is open.\n\n"
            "**What happens next:** Sommer/Studio Staff will review your request, confirm the scope and price, then let you know the next step."
        )
        embed.add_field(name="Project", value=str(self.project), inline=False)
        embed.add_field(name="Theme / Style", value=str(self.style) or "Not provided", inline=False)
        embed.add_field(name="Deadline", value=str(self.deadline) or "Flexible", inline=True)
        embed.add_field(name="Budget / Package", value=str(self.budget) or "Not provided", inline=True)
        embed.add_field(name="References / Notes", value=str(self.refs) or "None", inline=False)
        await channel.send(content=f"{interaction.user.mention}", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"🎟️ Your project ticket is ready: {channel.mention}", ephemeral=True)

class ServiceSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Discord Setup", emoji="💻", description="Full server setup, channels, roles & organization"),
            discord.SelectOption(label="Custom Discord Bot", emoji="🤖", description="Custom bot features and automation"),
            discord.SelectOption(label="FiveM Development / Setup", emoji="🎮", description="Server setup, resources and development help"),
            discord.SelectOption(label="Graphics / Flyers", emoji="🖼️", description="Flyers and promotional graphics"),
            discord.SelectOption(label="Logo / Branding", emoji="✨", description="Logos and visual branding"),
            discord.SelectOption(label="Streaming Graphics", emoji="📺", description="Overlays, panels and stream assets"),
            discord.SelectOption(label="Emojis / Stickers", emoji="💕", description="Custom Discord emojis and stickers"),
            discord.SelectOption(label="Bot Update / Support", emoji="🛠️", description="Updates or support for an existing bot"),
            discord.SelectOption(label="Other Request", emoji="🎬", description="Something else? Tell the Studio what you need"),
        ]
        super().__init__(placeholder="Choose your project type…", min_values=1, max_values=1, options=options, custom_id="sommer:service_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal(self.values[0]))

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ServiceSelect())

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", emoji="🎬", style=discord.ButtonStyle.primary, custom_id="sommer:claim")
    async def claim(self, interaction, button):
        if not is_management(interaction.user):
            return await interaction.response.send_message("Only Studio management can claim projects.", ephemeral=True)
        await interaction.response.send_message(f"🎬 **{interaction.user.display_name}** has claimed this project.")

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="sommer:close")
    async def close(self, interaction, button):
        if not is_management(interaction.user):
            return await interaction.response.send_message("Only Studio management can close projects.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        # Save a simple text transcript before closing.
        lines = []
        async for msg in interaction.channel.history(limit=500, oldest_first=True):
            stamp = msg.created_at.strftime("%Y-%m-%d %H:%M UTC")
            content = msg.content or "[embed/attachment]"
            lines.append(f"[{stamp}] {msg.author}: {content}")
            for a in msg.attachments:
                lines.append(f"  Attachment: {a.url}")
        data = "\n".join(lines).encode("utf-8")
        transcript = discord.File(io.BytesIO(data), filename=f"{interaction.channel.name}-transcript.txt")

        logs = discord.utils.get(interaction.guild.text_channels, name="ticket-logs")
        if logs:
            await logs.send(
                content=f"🔒 Closed **#{interaction.channel.name}** by {interaction.user.mention}",
                file=transcript
            )
        await interaction.followup.send("Closing project ticket…", ephemeral=True)
        await interaction.channel.delete(reason=f"Closed by {interaction.user}")

@bot.event
async def on_ready():
    print(f"Sommer Studios is online as {bot.user}.")

@bot.event
async def on_member_join(member):
    welcome = discord.utils.get(member.guild.text_channels, name="welcome")
    if welcome:
        embed = pink_embed(
            "🎬 Welcome to Sommer Studios!",
            f"Hey {member.mention}! Welcome to **Sommer Studios** — a creative studio for development, design, and digital creation.\n\n"
            "Head to **#verify** to grab your 🎟️ Studio Guest pass and enter the Studio."
        )
        await welcome.send(embed=embed)

@bot.tree.command(name="setup", description="Build the Sommer Studios server layout")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild

    owner = await get_or_create_role(guild, ROLE_OWNER, color=discord.Color.from_rgb(236,72,153), hoist=True)
    staff = await get_or_create_role(guild, ROLE_STAFF, color=discord.Color.from_rgb(192,132,252), hoist=True)
    creator = await get_or_create_role(guild, ROLE_CREATOR, color=discord.Color.from_rgb(96,165,250), hoist=True)
    vip = await get_or_create_role(guild, ROLE_VIP, color=discord.Color.gold(), hoist=True)
    guest = await get_or_create_role(guild, ROLE_GUEST, color=discord.Color.from_rgb(244,114,182))

    if OWNER_ID:
        member = guild.get_member(OWNER_ID)
        if member and owner not in member.roles:
            await member.add_roles(owner)

    everyone = guild.default_role
    bot_member = guild.me

    public_read = {
        everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
    }
    verified = {
        everyone: discord.PermissionOverwrite(view_channel=False),
        guest: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        vip: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        creator: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        staff: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
    }
    staff_post = dict(verified)
    staff_post[guest] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
    staff_post[vip] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
    staff_post[creator] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)

    vip_only = {
        everyone: discord.PermissionOverwrite(view_channel=False),
        vip: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        staff: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
    }
    vip_announce = dict(vip_only)
    vip_announce[vip] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)

    creator_only = {
        everyone: discord.PermissionOverwrite(view_channel=False),
        creator: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
        staff: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    # Entrance
    entrance = await get_or_create_category(guild, "🌸🎟️ STUDIO ENTRANCE")
    welcome = await get_or_create_text(guild, entrance, "welcome", public_read, "Welcome to Sommer Studios.")
    verify = await get_or_create_text(guild, entrance, "verify", public_read, "Verify to receive Studio Guest access.")
    info = await get_or_create_text(guild, entrance, "helpful-info", staff_post, "Studio information, ordering process and helpful details.")

    # Services
    services_cat = await get_or_create_category(guild, "🌸🎬 SOMMER'S SERVICES")
    services = await get_or_create_text(guild, services_cat, "services-offered", staff_post)
    prices = await get_or_create_text(guild, services_cat, "price-list", staff_post)
    ticket = await get_or_create_text(guild, services_cat, "start-a-project", staff_post)

    # Studio
    studio_cat = await get_or_create_category(guild, "🎥✨ THE STUDIO")
    showcase = await get_or_create_text(guild, studio_cat, "showcase", staff_post, "Completed Sommer Studios work and portfolio.")
    projects = await get_or_create_text(guild, studio_cat, "current-projects", staff_post, "Projects currently in production.")
    partners = await get_or_create_text(guild, studio_cat, "partners", staff_post, "Official Sommer Studios partners.")

    # Public community / Hollywood-style backlot
    community_cat = await get_or_create_category(guild, "🌻🎞️ STUDIO BACKLOT")
    await get_or_create_text(guild, community_cat, "🌸・studio-lounge", verified, "A welcoming public community space for Studio Guests, VIPs and Creators.")
    await get_or_create_text(guild, community_cat, "🎬・community-meetings", staff_post, "Community meeting announcements, Studio updates and scheduled conversations.")
    await get_or_create_voice(guild, community_cat, "🌻 The Backlot • Chill VC", verified)
    await get_or_create_voice(guild, community_cat, "🎬 Community Meeting Room", verified)
    await get_or_create_voice(guild, community_cat, "🛟 Studio Support • Help VC", verified)

    # VIP
    vip_cat = await get_or_create_category(guild, "🌻⭐ VIP BACKLOT", vip_only)
    free_resources = await get_or_create_text(guild, vip_cat, "free-resources", vip_announce)
    drops = await get_or_create_text(guild, vip_cat, "resource-drops", vip_announce)
    exclusives = await get_or_create_text(guild, vip_cat, "vip-exclusives", vip_announce)
    lounge = await get_or_create_text(guild, vip_cat, "vip-lounge", vip_only)
    vip_updates = await get_or_create_text(guild, vip_cat, "vip-updates", vip_announce)

    # Creator area
    creator_cat = await get_or_create_category(guild, "🎨🔐 CREATOR LOT", creator_only)
    creator_chat = await get_or_create_text(guild, creator_cat, "creator-chat", creator_only)
    await get_or_create_voice(guild, creator_cat, "🎙️ Creator VC", creator_only)

    # Tickets/logs
    ticket_cat = await get_or_create_category(guild, "🎟️ PROJECT TICKETS", {
        everyone: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(view_channel=True),
        staff: discord.PermissionOverwrite(view_channel=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    })
    logs_cat = await get_or_create_category(guild, "🎬🔒 STUDIO MANAGEMENT", {
        everyone: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(view_channel=True),
        staff: discord.PermissionOverwrite(view_channel=True),
        bot_member: discord.PermissionOverwrite(view_channel=True)
    })
    await get_or_create_text(guild, logs_cat, "ticket-logs", {
        everyone: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(view_channel=True),
        staff: discord.PermissionOverwrite(view_channel=True),
        bot_member: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    })

    # Starter posts only if channels are empty
    if not [m async for m in verify.history(limit=1)]:
        await verify.send(embed=pink_embed(
            "🎟️ Studio Check-In",
            "Ready to enter **Sommer Studios**?\n\nTap the button below to receive your **🎟️ Studio Guest** role and unlock the Studio."
        ), view=VerifyView())

    if not [m async for m in info.history(limit=1)]:
        await info.send(embed=pink_embed(
            "📌 Welcome to the Studio",
            "**How to work with Sommer Studios**\n\n"
            "1. Browse **#services-offered** and **#price-list**.\n"
            "2. Go to **#start-a-project** and choose what you need.\n"
            "3. Complete the project form with as much detail as possible.\n"
            "4. Your private ticket will open for consultation, pricing and next steps.\n\n"
            "✨ Check **#showcase** for completed work.\n"
            "⭐ STUDIO VIP members receive access to private resources, drops and exclusives."
        ))

    if not [m async for m in services.history(limit=1)]:
        e = pink_embed("🎨 Sommer Studios Services", "Development, design & digital creation—all in one Studio.")
        e.add_field(name="💻 Discord Development", value="Server setup • categories/channels • roles • permissions • ticket systems • bot configuration", inline=False)
        e.add_field(name="🤖 Custom Discord Bots", value="Custom commands • verification • tickets • welcome systems • automation • hosted bot updates", inline=False)
        e.add_field(name="🎮 FiveM Development / Setup", value="Setup assistance • resource installation • configuration • server organization • development support", inline=False)
        e.add_field(name="🖼️ Graphics & Branding", value="Flyers • logos • AI logos • server graphics • promotional designs", inline=False)
        e.add_field(name="📺 Creator Graphics", value="Streaming overlays • panels • creator branding • Discord emojis & stickers", inline=False)
        await services.send(embed=e)

    if not [m async for m in prices.history(limit=1)]:
        e = pink_embed("💰 Sommer Studios Price List", "Current starting prices. Custom projects are quoted based on scope.")
        e.add_field(name="💻 Discord Setup", value="Basic — up to 5 categories: **$25**\nBot setup/configuration add-on: **+$10**\nExpanded packages: **$40 / $50**", inline=False)
        e.add_field(name="🤖 Custom Bot", value="Starting at **$65** • final price depends on features", inline=False)
        e.add_field(name="🛠️ Hosted Bot Updates", value="Updates/changes starting at **$5 each**", inline=False)
        e.add_field(name="🎨 Graphics / FiveM / Custom Work", value="Open a project ticket for a quote based on your request.", inline=False)
        e.add_field(name="📌 Please Note", value="Pricing may change with complexity, rush deadlines, revisions, hosting, paid assets, or additional features.", inline=False)
        await prices.send(embed=e)

    if not [m async for m in ticket.history(limit=1)]:
        await ticket.send(embed=pink_embed(
            "🎟️ Start a Project",
            "Ready to bring your idea to life?\n\nChoose your project type below. You'll fill out a quick form, then a **private project ticket** will open for you and Sommer Studios."
        ), view=TicketPanelView())

    if not [m async for m in showcase.history(limit=1)]:
        await showcase.send(embed=pink_embed("✨ Sommer Studios Showcase", "Finished projects, transformations and client work will be showcased here. 🎬"))

    if not [m async for m in projects.history(limit=1)]:
        await projects.send(embed=pink_embed("🚧 Now in Production", "Current Sommer Studios projects and progress updates will be posted here."))

    if not [m async for m in partners.history(limit=1)]:
        await partners.send(embed=pink_embed("🤝 Studio Partners", "Official creator and development partners will be announced here. Partner storefronts will be added only after approval."))

    if not [m async for m in free_resources.history(limit=1)]:
        await free_resources.send(embed=pink_embed("🎁 VIP Free Resources", "Exclusive free resources for **STUDIO VIP** members will live here."))
    if not [m async for m in drops.history(limit=1)]:
        await drops.send(embed=pink_embed("📦 Resource Drops", "New templates, assets and resources will be announced here first."))
    if not [m async for m in exclusives.history(limit=1)]:
        await exclusives.send(embed=pink_embed("💎 VIP Exclusives", "VIP-only downloads, early releases and special Studio extras."))
    if not [m async for m in vip_updates.history(limit=1)]:
        await vip_updates.send(embed=pink_embed("🔔 VIP Updates", "Early Studio news, resource announcements and VIP updates."))
    if not [m async for m in creator_chat.history(limit=1)]:
        await creator_chat.send(embed=pink_embed("🎨 Creator Lot", "Private workspace for approved **Studio Creators** and Sommer Studios management."))

    await interaction.followup.send("🎬 **Sommer Studios is built!** Channels, roles, verification, VIP Backlot, Creator Lot and project tickets are ready.", ephemeral=True)

@bot.tree.command(name="vip", description="Add or remove STUDIO VIP access")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Member to update", action="Give or remove VIP")
@app_commands.choices(action=[
    app_commands.Choice(name="Give VIP", value="give"),
    app_commands.Choice(name="Remove VIP", value="remove"),
])
async def vip(interaction: discord.Interaction, member: discord.Member, action: app_commands.Choice[str]):
    role = discord.utils.get(interaction.guild.roles, name=ROLE_VIP)
    if not role:
        return await interaction.response.send_message("Run `/setup` first.", ephemeral=True)
    if action.value == "give":
        await member.add_roles(role)
        msg = f"⭐ {member.mention} now has **STUDIO VIP** access."
    else:
        await member.remove_roles(role)
        msg = f"VIP access removed from {member.mention}."
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="creator", description="Add or remove an approved Studio Creator")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Creator to update", action="Approve or remove creator access")
@app_commands.choices(action=[
    app_commands.Choice(name="Approve Creator", value="give"),
    app_commands.Choice(name="Remove Creator", value="remove"),
])
async def creator_cmd(interaction: discord.Interaction, member: discord.Member, action: app_commands.Choice[str]):
    role = discord.utils.get(interaction.guild.roles, name=ROLE_CREATOR)
    if not role:
        return await interaction.response.send_message("Run `/setup` first.", ephemeral=True)
    if action.value == "give":
        await member.add_roles(role)
        msg = f"🎨 {member.mention} is now an approved **Studio Creator**."
    else:
        await member.remove_roles(role)
        msg = f"Creator access removed from {member.mention}."
    await interaction.response.send_message(msg, ephemeral=True)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env or hosting environment variables.")

bot.run(TOKEN)
