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
        self.add_view(RoleRequestPanel())
        self.add_view(RoleReviewView())
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

def _clean_name(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())

async def get_or_create_category(guild, name, overwrites=None, aliases=()):
    # Match either the final decorated name OR an older clean name, then rename in place.
    wanted = {_clean_name(name), *(_clean_name(a) for a in aliases)}
    cat = next((c for c in guild.categories if _clean_name(c.name) in wanted), None)
    if not cat:
        cat = await guild.create_category(name, overwrites=overwrites or {})
    else:
        edits = {}
        if cat.name != name:
            edits["name"] = name
        if overwrites is not None:
            edits["overwrites"] = overwrites
        if edits:
            await cat.edit(**edits)
    return cat

async def get_or_create_text(guild, category, name, overwrites=None, topic=None, aliases=()):
    # Prefer a matching channel already inside the intended category.
    wanted = {_clean_name(name), *(_clean_name(a) for a in aliases)}
    ch = next((c for c in category.text_channels if _clean_name(c.name) in wanted), None)
    if not ch:
        ch = next((c for c in guild.text_channels if _clean_name(c.name) in wanted), None)
    if not ch:
        ch = await guild.create_text_channel(name, category=category, overwrites=overwrites or {}, topic=topic)
    else:
        edits = {}
        if ch.category != category:
            edits["category"] = category
        if ch.name != name:
            edits["name"] = name
        if overwrites is not None:
            edits["overwrites"] = overwrites
        if topic is not None and ch.topic != topic:
            edits["topic"] = topic
        if edits:
            await ch.edit(**edits)
    return ch

async def get_or_create_voice(guild, category, name, overwrites=None, aliases=()):
    wanted = {_clean_name(name), *(_clean_name(a) for a in aliases)}
    ch = next((c for c in category.voice_channels if _clean_name(c.name) in wanted), None)
    if not ch:
        ch = next((c for c in guild.voice_channels if _clean_name(c.name) in wanted), None)
    if not ch:
        ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites or {})
    else:
        edits = {}
        if ch.category != category:
            edits["category"] = category
        if ch.name != name:
            edits["name"] = name
        if overwrites is not None:
            edits["overwrites"] = overwrites
        if edits:
            await ch.edit(**edits)
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
        category = next((c for c in guild.categories if _clean_name(c.name) in {_clean_name("🎟️🎬 PROJECT TICKETS"), _clean_name("🎟️ PROJECT TICKETS")}), None)
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

        logs = next((c for c in interaction.guild.text_channels if _clean_name(c.name) == "ticketlogs"), None)
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
    welcome = next((c for c in member.guild.text_channels if _clean_name(c.name) == "welcome"), None)
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
    client = await get_or_create_role(guild, "🎬 Studio Client", color=discord.Color.from_rgb(251,191,36), hoist=True)

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
        client: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
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
    entrance = await get_or_create_category(guild, "🌸🎟️ STUDIO ENTRANCE", aliases=("🎟️ STUDIO ENTRANCE",))
    welcome = await get_or_create_text(guild, entrance, "welcome", public_read, "Welcome to Sommer Studios.")
    verify = await get_or_create_text(guild, entrance, "verify", public_read, "Verify to receive Studio Guest access.")
    info = await get_or_create_text(guild, entrance, "helpful-info", staff_post, "Studio information, ordering process and helpful details.")

    # Services
    services_cat = await get_or_create_category(guild, "🌸🎬 SOMMER'S SERVICES")
    services = await get_or_create_text(guild, services_cat, "services-offered", staff_post)
    prices = await get_or_create_text(guild, services_cat, "price-list", staff_post)
    ticket = await get_or_create_text(guild, services_cat, "start-a-project", staff_post)

    # Studio
    studio_cat = await get_or_create_category(guild, "🎥✨ THE STUDIO", aliases=("🎬 THE STUDIO",))
    showcase = await get_or_create_text(guild, studio_cat, "showcase", staff_post, "Completed Sommer Studios work and portfolio.")
    projects = await get_or_create_text(guild, studio_cat, "current-projects", staff_post, "Projects currently in production.")
    partners = await get_or_create_text(guild, studio_cat, "partners", staff_post, "Official Sommer Studios partners.")

    # Public community / Hollywood-style backlot
    community_cat = await get_or_create_category(guild, "🌻🎞️ STUDIO BACKLOT", aliases=("STUDIO BACKLOT",))
    studio_lounge = await get_or_create_text(guild, community_cat, "🌸・studio-lounge", verified, "🌸 Studio Lounge • Chat, connect, share ideas and hang out with the Sommer Studios community.")
    meeting_channel = await get_or_create_text(guild, community_cat, "🎬・community-meetings", staff_post, "🎬 Community Meetings • Official meeting announcements, schedules, Studio updates and community conversations.")
    await get_or_create_voice(guild, community_cat, "🌻 The Backlot • Chill VC", verified)
    await get_or_create_voice(guild, community_cat, "🎬 Community Meeting Room", verified)
    await get_or_create_voice(guild, community_cat, "🛟 Studio Support • Help VC", verified)

    if not [m async for m in studio_lounge.history(limit=1)]:
        await studio_lounge.send(embed=pink_embed(
            "🌸 Welcome to the Studio Lounge",
            "Kick back on the **Sommer Studios Backlot** 🌻🎬\n\nChat, network, share ideas, meet other creatives, or just hang out between projects. Keep it welcoming, creative and respectful. ✨"
        ))
    if not [m async for m in meeting_channel.history(limit=1)]:
        await meeting_channel.send(embed=pink_embed(
            "🎬 Community Meetings",
            "This is the Studio call board! 📋✨\n\nOfficial **community meeting dates, Studio announcements and meeting details** will be posted here. When it is meeting time, join **🎬 Community Meeting Room**."
        ))

    # VIP
    vip_cat = await get_or_create_category(guild, "🌻⭐ VIP BACKLOT", vip_only, aliases=("⭐ VIP BACKLOT",))
    free_resources = await get_or_create_text(guild, vip_cat, "free-resources", vip_announce)
    drops = await get_or_create_text(guild, vip_cat, "resource-drops", vip_announce)
    exclusives = await get_or_create_text(guild, vip_cat, "vip-exclusives", vip_announce)
    lounge = await get_or_create_text(guild, vip_cat, "vip-lounge", vip_only)
    vip_updates = await get_or_create_text(guild, vip_cat, "vip-updates", vip_announce)

    # Creator area
    creator_cat = await get_or_create_category(guild, "🎨🔐 CREATOR LOT", creator_only, aliases=("🔐 CREATOR LOT",))
    creator_chat = await get_or_create_text(guild, creator_cat, "creator-chat", creator_only)
    await get_or_create_voice(guild, creator_cat, "🎙️ Creator VC", creator_only)

    # Tickets/logs
    ticket_cat = await get_or_create_category(guild, "🎟️🎬 PROJECT TICKETS", {
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


# Hollywood creator and streamer expansion. Existing roles and channels stay in place.
ROLE_CONTENT = "📸 Content Creator"
ROLE_STREAMER = "🎙️ Streamer"
REQUESTABLE_ROLES = (ROLE_CREATOR, ROLE_CONTENT, ROLE_STREAMER)

class RoleApplication(discord.ui.Modal, title="🎬 Your Studio Application"):
    def __init__(self, role_name):
        super().__init__()
        self.role_name = role_name
        self.about = discord.ui.TextInput(label="Tell us about your work / content", style=discord.TextStyle.paragraph, max_length=1000)
        self.links = discord.ui.TextInput(label="Portfolio / social links / streaming channel", style=discord.TextStyle.paragraph, max_length=800)
        self.plans = discord.ui.TextInput(label="What would you like to do in the Studio?", style=discord.TextStyle.paragraph, max_length=800)
        for item in (self.about, self.links, self.plans):
            self.add_item(item)

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        role = discord.utils.get(guild.roles, name=self.role_name)
        category = discord.utils.get(guild.categories, name="🎬🔒 ROLE APPLICATIONS")
        if not role or not category:
            return await interaction.followup.send("Please ask staff to run /studio_update first.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.followup.send("You already have that role! ✨", ephemeral=True)
        marker = f"application:{interaction.user.id}:{role.id}"
        existing = next((c for c in category.text_channels if c.topic == marker), None)
        if existing:
            return await interaction.followup.send(f"Your application is already open: {existing.mention}", ephemeral=True)
        permissions = dict(category.overwrites)
        permissions[interaction.user] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        channel = await guild.create_text_channel(f"application-{interaction.user.id}-{role.id}", category=category, overwrites=permissions, topic=marker)
        embed = pink_embed("🎬 Studio Role Application", f"**Applicant:** {interaction.user.mention}\n**Requested role:** {role.mention}")
        embed.add_field(name="About their work", value=str(self.about), inline=False)
        embed.add_field(name="Links / portfolio", value=str(self.links), inline=False)
        embed.add_field(name="Studio plans", value=str(self.plans), inline=False)
        await channel.send(embed=embed, view=RoleReviewView(), allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send(f"✨ Your private application is ready: {channel.mention}. Studio staff will review it.", ephemeral=True)

class RoleRequestSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Choose the role you want to apply for…", custom_id="sommer:role_request", options=[
            discord.SelectOption(label="Studio Creator", value=ROLE_CREATOR, emoji="🎨", description="Apply for the existing Studio Creator workspace"),
            discord.SelectOption(label="Content Creator", value=ROLE_CONTENT, emoji="📸", description="Photos, videos, content and creative collaborations"),
            discord.SelectOption(label="Streamer", value=ROLE_STREAMER, emoji="🎙️", description="Live streams, highlights and streaming collaborations"),
        ])
    async def callback(self, interaction):
        await interaction.response.send_modal(RoleApplication(self.values[0]))

class RoleRequestPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleRequestSelect())

class RoleReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def review(self, interaction, approve):
        if not is_management(interaction.user):
            return await interaction.response.send_message("Only Studio management can review applications.", ephemeral=True)
        topic = interaction.channel.topic or ""
        match = re.fullmatch(r"application:(\d+):(\d+)", topic)
        if not match:
            return await interaction.response.send_message("This application has already been reviewed or is invalid.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        user_id, role_id = map(int, match.groups())
        role = interaction.guild.get_role(role_id)
        if not role or role.name not in REQUESTABLE_ROLES:
            return await interaction.followup.send("Requested role is missing or is not requestable.", ephemeral=True)
        try:
            member = interaction.guild.get_member(user_id) or await interaction.guild.fetch_member(user_id)
            if approve:
                await member.add_roles(role, reason=f"Studio application approved by {interaction.user}")
        except discord.HTTPException:
            return await interaction.followup.send("Could not complete the review. Check that the member is still here and the bot role is above the requested role, then try again.", ephemeral=True)
        await interaction.channel.edit(topic=f"reviewed:{user_id}:{role_id}:{'approved' if approve else 'declined'}")
        await interaction.message.edit(view=None)
        await interaction.channel.send(f"{'✨ Approved' if approve else 'Application declined'} by {interaction.user.mention}. " + (f"{member.mention} now has {role.mention} access!" if approve else "You can speak with Studio staff here about the decision."), allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send("Application reviewed.", ephemeral=True)

    @discord.ui.button(label="Approve", emoji="✨", style=discord.ButtonStyle.success, custom_id="sommer:role_approve")
    async def approve(self, interaction, button):
        await self.review(interaction, True)

    @discord.ui.button(label="Decline", emoji="🎬", style=discord.ButtonStyle.danger, custom_id="sommer:role_decline")
    async def decline(self, interaction, button):
        await self.review(interaction, False)

@bot.tree.command(name="studio_update", description="Add private creator and streamer sections and role applications")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def studio_update(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    owner = await get_or_create_role(guild, ROLE_OWNER)
    staff = await get_or_create_role(guild, ROLE_STAFF)
    content = await get_or_create_role(guild, ROLE_CONTENT, color=discord.Color.from_rgb(244,114,182), hoist=True)
    streamer = await get_or_create_role(guild, ROLE_STREAMER, color=discord.Color.from_rgb(192,132,252), hoist=True)
    await get_or_create_role(guild, ROLE_CREATOR)
    base = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        owner: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        staff: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
    }
    sections = [
        ("╭・📸 CONTENT CREATOR SUITE ・╮", content, [
            ("💬・creator-lounge", "Connect, share content ideas and meet your fellow creators."),
            ("📸・behind-the-lens", "Find photographers, videographers, editors and models. Share examples, availability and rates."),
            ("🎬・casting-and-collabs", "Find your next co-star! Post your project, platform/city, availability and whether it is paid or a free collab."),
            ("🖼️・the-gallery", "Your red carpet moment: showcase photos, reels, videos and finished projects."),
        ]),
        ("╭・📡 SOMMER LIVE ・╮", streamer, [
            ("🎙️・backstage-chat", "Talk streaming, setups, content ideas and growing your channel."),
            ("🔴・on-air", "Going live? Post your stream link, game/topic and start time. Live links are member-posted here."),
            ("🎞️・highlight-reel", "Share your funniest clips, biggest wins and favorite stream moments."),
            ("🤝・co-star-connect", "Find streaming partners for joint streams, gaming sessions and community events."),
        ]),
    ]
    for name, role, channels in sections:
        permissions = dict(base)
        permissions[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        category = await get_or_create_category(guild, name, permissions)
        for channel_name, description in channels:
            channel = await get_or_create_text(guild, category, channel_name, permissions, description)
            if not [m async for m in channel.history(limit=1)]:
                await channel.send(embed=pink_embed(channel_name.replace('・', ' '), description + "\n\n✨ Keep it respectful, credit fellow creatives, and agree on rates and expectations before starting."))
    applications = await get_or_create_category(guild, "🎬🔒 ROLE APPLICATIONS", base)
    public = dict(base)
    for name in (ROLE_GUEST, "🎬 Studio Client", ROLE_VIP, ROLE_CREATOR, ROLE_CONTENT, ROLE_STREAMER):
        role = discord.utils.get(guild.roles, name=name)
        if role:
            public[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
    entrance = await get_or_create_category(guild, "🌸🎟️ STUDIO ENTRANCE", aliases=("🎟️ STUDIO ENTRANCE",))
    requests = await get_or_create_text(guild, entrance, "✨・role-requests", public, "Apply for Studio Creator, Content Creator or Streamer. Staff approval required.", aliases=("role-requests",))
    # Find our panel so rerunning this command does not add duplicate panels.
    panel = None
    async for message in requests.history(limit=None):
        if message.author.id == bot.user.id and message.embeds and message.embeds[0].title == "🎬 Your Next Studio Pass":
            panel = message
            break
    embed = pink_embed("🎬 Your Next Studio Pass", "Ready for your next role at **Sommer Studios**? Choose below and tell us about your work!\n\n🎨 **Studio Creator** — the existing private creator workspace.\n📸 **Content Creator** — the Content Creator Suite for photos, videos and creative collabs.\n🎙️ **Streamer** — Sommer Live for live links, clips and streaming collabs.\n\nYou can apply for both Content Creator and Streamer separately. Each approved role unlocks its matching section. Applications are private to you and Studio management.\n\n⭐ VIP and Studio Client access are handled separately and cannot be requested here.")
    if panel:
        await panel.edit(embed=embed, view=RoleRequestPanel())
    else:
        await requests.send(embed=embed, view=RoleRequestPanel())
    await interaction.followup.send("✨ Hollywood expansion ready! Private Content Creator Suite, Sommer Live and role applications are set up. Existing Studio roles and sections are preserved. Put the bot role above the roles it approves. Live alerts are member-posted; automatic platform alerts are not configured.", ephemeral=True)


CHANNEL_DECORATIONS = {
    "welcome": "🎟️・welcome", "verify": "✨・verify",
    "helpful-info": "📋・helpful-info", "services-offered": "🎨・services-offered",
    "price-list": "💰・price-list", "start-a-project": "🎬・start-a-project",
    "showcase": "🖼️・showcase", "current-projects": "🚧・current-projects",
    "partners": "🤝・partners", "free-resources": "🎁・free-resources",
    "resource-drops": "📦・resource-drops", "vip-exclusives": "💎・vip-exclusives",
    "vip-lounge": "🥂・vip-lounge", "vip-updates": "🔔・vip-updates",
    "creator-chat": "🎨・creator-chat", "ticket-logs": "🗂️・ticket-logs",
}

@bot.tree.command(name="spotlight_update", description="Add public Spotlight channels and decorate existing channel names")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def spotlight_update(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    guest = discord.utils.get(guild.roles, name=ROLE_GUEST)
    if not guest:
        return await interaction.followup.send("Run /setup first to create Studio Guest verification.", ephemeral=True)
    content = discord.utils.get(guild.roles, name=ROLE_CONTENT)
    streamer = discord.utils.get(guild.roles, name=ROLE_STREAMER)
    if not content or not streamer:
        return await interaction.followup.send("Run /studio_update first to create the creator and streamer roles.", ephemeral=True)
    for channel in guild.text_channels:
        new_name = next((name for old, name in CHANNEL_DECORATIONS.items() if _clean_name(channel.name) == _clean_name(old)), None)
        if new_name and channel.name != new_name:
            await channel.edit(name=new_name, reason="Sommer Studios Hollywood channel styling")
    perms = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guest: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True, add_reactions=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, embed_links=True, attach_files=True),
    }
    # These roles never independently grant verification or public channel access.
    # Studio Guest is the verification pass; staff can always manage the Spotlight.
    for role_name in (ROLE_OWNER, ROLE_STAFF):
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            perms[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
    category = await get_or_create_category(guild, "🌟🎬 SOMMER SPOTLIGHT", perms)
    for name, role, title, description in (
        ("🔴・now-showing", streamer, "🔴 Now Showing", "Streamers: share your Twitch, Kick, TikTok or YouTube live link and tell us what you’re streaming. Everyone verified can watch and show support!\n\nLive links are manually posted for now; automatic alerts are not connected yet."),
        ("📸・fresh-off-the-reel", content, "📸 Fresh Off the Reel", "Content Creators: share your pics, clips, reels and Instagram post links. Everyone verified can view and react—let’s support each other!\n\nFollow and tag **@sommerstudioshq** on Instagram. Automatic IG tag posting is not connected yet."),
    ):
        channel_perms = dict(perms)
        # A posting role permits sending, but Studio Guest is still needed to view.
        channel_perms[role] = discord.PermissionOverwrite(send_messages=True, attach_files=True, embed_links=True)
        channel = await get_or_create_text(guild, category, name, channel_perms, description)
        if not [message async for message in channel.history(limit=1)]:
            await channel.send(embed=pink_embed(title, description))
    await interaction.followup.send("🌟 Sommer Spotlight is ready! All Studio Guests can view and react. Streamers can post in now-showing; Content Creators can post in fresh-off-the-reel. Existing channel emojis are updated. Private sections keep their existing access. Automatic alerts and IG posting are not connected yet.", ephemeral=True)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env or hosting environment variables.")

bot.run(TOKEN)
