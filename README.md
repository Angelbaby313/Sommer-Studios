# 🎬 Sommer Studios Bot

A custom Discord setup/ticket bot for **Sommer Studios**.

## What it builds
- 🎟️ Studio Entrance
  - #welcome
  - #verify
  - #helpful-info
- 🌸 Sommer's Services
  - #services-offered
  - #price-list
  - #start-a-project
- 🎬 The Studio
  - #showcase
  - #current-projects
  - #partners
- ⭐ VIP Backlot
  - #free-resources
  - #resource-drops
  - #vip-exclusives
  - #vip-lounge
  - #vip-updates
- 🔐 Creator Lot
  - #creator-chat
  - Creator VC
- Private project ticket area + private ticket logs

## Roles
- 🎬 Studio Owner
- 🎥 Studio Staff
- 🎨 Studio Creator
- ⭐ STUDIO VIP
- 🎟️ Studio Guest

## Ticket choices
Discord Setup, Custom Discord Bot, FiveM Development / Setup, Graphics / Flyers,
Logo / Branding, Streaming Graphics, Emojis / Stickers, Bot Update / Support, Other Request.

Tickets include a project intake form and persistent Claim/Close buttons. Closing a ticket saves
a text transcript in #ticket-logs.

## Slash commands
- `/setup` — builds the server and posts all starter panels
- `/vip` — give/remove STUDIO VIP
- `/creator` — approve/remove Studio Creator access

## Setup
1. Create a Discord application/bot in the Discord Developer Portal.
2. Enable **Server Members Intent** and **Message Content Intent** for the bot.
3. Invite the bot with the `bot` and `applications.commands` scopes.
4. For the easiest first setup, give the bot Administrator permission. After setup, you can reduce permissions if desired.
5. Rename `.env.example` to `.env` for local use, or add these as Railway Variables:
   - `DISCORD_TOKEN`
   - `GUILD_ID`
   - `OWNER_ID`
6. Install requirements: `pip install -r requirements.txt`
7. Run: `python bot.py`
8. In your Discord, run `/setup` once.

## Railway
Upload/push these files to GitHub, connect the repo to Railway, add the 3 environment variables,
and use `python bot.py` as the start command. The included Procfile also defines the worker command.

## Important
Never upload your real `.env` or bot token to GitHub. `.gitignore` is included.
