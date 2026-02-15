import discord
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
import json, random
import string
import asyncio
from datetime import datetime
import aiohttp
from typing import Optional
import os


ADMIN_ROLE_NAME = "Digital Technology Chief" # was changed to role id 
FLIGHTS_FILE = "flights.json"
BOOKINGS_FILE = "bookings.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class FlightBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.flights = self.load_flights()
        self.bookings = self.load_bookings()
        
    def load_flights(self):
        try:
            with open(FLIGHTS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: {FLIGHTS_FILE} not found, starting with empty flight list")
            return {}
    
    def save_flights(self):
        with open(FLIGHTS_FILE, 'w') as f:
            json.dump(self.flights, f, indent=4)
    
    def load_bookings(self):
        try:
            with open(BOOKINGS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: {BOOKINGS_FILE} not found, starting with empty bookings")
            return {}
    
    def save_bookings(self):
        with open(BOOKINGS_FILE, 'w') as f:
            json.dump(self.bookings, f, indent=4)
    
    def add_booking(self, flight_code, booking_code, roblox_username, discord_id, cabin_class):
        if flight_code not in self.bookings:
            self.bookings[flight_code] = []
        
        booking_info = {
            "booking_code": booking_code,
            "roblox_username": roblox_username,
            "discord_id": discord_id,
            "cabin_class": cabin_class,
            "booked_at": datetime.utcnow().isoformat()
        }
        
        self.bookings[flight_code].append(booking_info)
        self.save_bookings()
    
    def generate_booking_code(self):
        flight_num = random.randint(10000, 99999)
        letters = ''.join(random.choices(string.ascii_uppercase, k=6))
        return f"AK{flight_num}-{letters}"


client = FlightBot()


async def check_roblox_username(username: str) -> bool:
    
    if len(username) < 3 or len(username) > 20:
        return False
    
    if not username.replace('_', '').isalnum():
        return False
    
    # if fail it ignores lol
    try:     
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://users.roblox.com/v1/usernames/users',
                json={"usernames": [username], "excludeBannedUsers": True}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return len(data.get('data', [])) > 0
    except Exception as e:
        print(f"Roblox API check failed: {e}")
        pass
    
    return True


class FlightSelectView(View):
    def __init__(self, flights, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.selected_flight = None
        
        options = []
        for flight_code, flight_data in flights.items():
            label = f"{flight_code} - {flight_data['route']}"
            description = f"{flight_data['aircraft']} • {flight_data['spots_left']} spots"
            
            options.append(discord.SelectOption(
                label=label[:100],
                value=flight_code,
                description=description[:100]
            ))
        
        if options:
            select = Select(
                placeholder="✈️ Select your flight",
                options=options[:25]
            )
            select.callback = self.flight_selected
            self.add_item(select)
    
    async def flight_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your booking!", ephemeral=True)
            return
        
        self.selected_flight = interaction.data['values'][0]
        
        view = BookingTypeView(self.selected_flight, self.user_id)
        flight_data = client.flights[self.selected_flight]
        
        embed = discord.Embed(
            title="🎫 Confirm Your Booking",
            description=f"**Flight:** {self.selected_flight}\n**Route:** {flight_data['route']}\n**Aircraft:** {flight_data['aircraft']}",
            color=0x0066CC
        )
        embed.add_field(name="👤 Who is flying?", value="Please select who this booking is for:", inline=False)
        embed.set_footer(text="Air Korea PTFS")
        
        await interaction.response.edit_message(embed=embed, view=view)


class RobloxUsernameModal(discord.ui.Modal, title="Enter Your Roblox Username"):
    username = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Enter your Roblox username",
        required=True,
        min_length=3,
        max_length=20
    )
    
    def __init__(self, flight_code, booker_id, passenger_id):
        super().__init__()
        self.flight_code = flight_code
        self.booker_id = booker_id
        self.passenger_id = passenger_id
    
    async def on_submit(self, interaction: discord.Interaction):
        roblox_username = self.username.value.strip()
        
        if not await check_roblox_username(roblox_username):
            await interaction.response.send_message(
                "Wrong ROblox Username.",
                ephemeral=True
            )
            return
        
        view = CabinClassView(self.flight_code, self.booker_id, roblox_username, self.passenger_id)
        await interaction.response.send_message("Please select your cabin class:", view=view, ephemeral=True)


class SomeoneElseModal(discord.ui.Modal, title="Book for Someone Else"):
    discord_id = discord.ui.TextInput(
        label="Discord User ID",
        placeholder="Enter their Discord User ID",
        required=True,
        min_length=17,
        max_length=20
    )
    
    username = discord.ui.TextInput(
        label="Roblox Username",
        placeholder="Enter their Roblox username",
        required=True,
        min_length=3,
        max_length=20
    )
    
    def __init__(self, flight_code, booker_id):
        super().__init__()
        self.flight_code = flight_code
        self.booker_id = booker_id
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            passenger_id = int(self.discord_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Invalid Discord User ID. Please start the booking process again.", ephemeral=True)
            return
        
        roblox_username = self.username.value.strip()
        
        if not await check_roblox_username(roblox_username):
            await interaction.response.send_message("❌ Invalid Roblox username. Please start the booking process again.", ephemeral=True)
            return
        
        view = CabinClassView(self.flight_code, self.booker_id, roblox_username, passenger_id)
        await interaction.response.send_message("Please select the cabin class:", view=view, ephemeral=True)


class BookingTypeView(View):
    def __init__(self, flight_code, user_id):
        super().__init__(timeout=300)
        self.flight_code = flight_code
        self.user_id = user_id
    
    @discord.ui.button(label="Myself", style=discord.ButtonStyle.primary, emoji="👤")
    async def myself_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your booking!", ephemeral=True)
            return
        
        modal = RobloxUsernameModal(self.flight_code, self.user_id, None)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Someone Else", style=discord.ButtonStyle.secondary, emoji="👥")
    async def someone_else_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your booking!", ephemeral=True)
            return
        
        modal = SomeoneElseModal(self.flight_code, self.user_id)
        await interaction.response.send_modal(modal)


class CabinClassView(View):
    def __init__(self, flight_code, booker_id, roblox_username, passenger_id):
        super().__init__(timeout=300)
        self.flight_code = flight_code
        self.booker_id = booker_id
        self.roblox_username = roblox_username
        self.passenger_id = passenger_id
        
        classes = [("Economy", "💺"), ("Premium Economy", "🪑"), ("Business", "🛋️"), ("First Class", "👑")]
        
        for class_name, emoji in classes:
            button = Button(label=class_name, emoji=emoji, style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(class_name)
            self.add_item(button)
    
    def create_callback(self, cabin_class):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.booker_id:
                await interaction.response.send_message("This isn't your booking!", ephemeral=True)
                return
            
            await self.complete_booking(interaction, cabin_class)
        return callback
    
    async def complete_booking(self, interaction: discord.Interaction, cabin_class: str):
        flight_data = client.flights.get(self.flight_code)
        
        if not flight_data:
            await interaction.response.send_message("❌ Flight not found!", ephemeral=True)
            return
        
        if flight_data['spots_left'] <= 0:
            await interaction.response.send_message("❌ No spots available on this flight!", ephemeral=True)
            return
        
        client.flights[self.flight_code]['spots_left'] -= 1
        client.save_flights()
        
        booking_code = client.generate_booking_code()
        
        passenger_discord_id = self.passenger_id if self.passenger_id else self.booker_id
        client.add_booking(self.flight_code, booking_code, self.roblox_username, passenger_discord_id, cabin_class)
        
        
        unix_time = None
        try:
            departure_dt = datetime.strptime(flight_data['departure'], "%Y-%m-%d %H:%M")
            unix_time = int(departure_dt.timestamp())
            time_display = f"<t:{unix_time}:F>"
            relative_time = f"<t:{unix_time}:R>"
        except Exception as e:
            print(f"Error parsing departure time: {e}")
            time_display = flight_data['departure']
            relative_time = "N/A"
        
        embed = discord.Embed(
            title="🎫 Booking Confirmation",
            description=f"Thank you for choosing **Air Korea!** Your flight has been successfully booked.\n\n**Flight {self.flight_code}** is ready for boarding!",
            color=0x0066CC,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="✈️ Flight Number", value=f"`{self.flight_code}`", inline=True)
        embed.add_field(name="🛫 Route", value=flight_data['route'], inline=True)
        embed.add_field(name="🛩️ Aircraft", value=flight_data['aircraft'], inline=True)
        embed.add_field(name="💳 Booking Code", value=f"```{booking_code}```", inline=False)
        embed.add_field(name="👤 Passenger (Roblox)", value=f"`{self.roblox_username}`", inline=True)
        embed.add_field(name="💺 Cabin Class", value=cabin_class, inline=True)
        embed.add_field(name="🌍 Timezone", value=flight_data.get('timezone', 'UTC'), inline=True)
        embed.add_field(name="🕐 Departure Time", value=time_display, inline=True)
        embed.add_field(name="⏱️ Boarding In", value=relative_time, inline=True)
        embed.add_field(name="📅 Booked On", value=f"<t:{int(datetime.utcnow().timestamp())}:D>", inline=True)
        
        embed.set_footer(text="Air Korea PTFS • Please arrive 30 minutes before departure")
        
        try:
            if self.passenger_id:
                passenger = await client.fetch_user(self.passenger_id)
                await passenger.send(embed=embed)
                await interaction.response.send_message(f"✅ Booking confirmed! Confirmation sent to <@{self.passenger_id}>'s DMs.", ephemeral=True)
            else:
                user = await client.fetch_user(self.booker_id)
                await user.send(embed=embed)
                await interaction.response.send_message("✅ Booking confirmed! Check your DMs for confirmation details.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("✅ Booking confirmed but couldn't send DM. Please enable DMs from server members.", ephemeral=True)
        except Exception as e:
            print(f"Error sending DM: {e}")
            await interaction.response.send_message(f"✅ Booking confirmed but couldn't send DM. Please check your DM settings.", ephemeral=True)


@client.tree.command(name="bookflight", description="Book a flight with Air Korea")
async def book_flight(interaction: discord.Interaction):
    if not client.flights:
        await interaction.response.send_message(" No flights available at the moment.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✈️ Air Korea Flight Booking",
        description="**Welcome aboard!** Select your preferred flight from the options below to begin your journey.\n\n🌏 Connecting Korea to the World",
        color=0x0066CC
    )
    
    embed.add_field(
        name="📋 Booking Process",
        value="> 1️⃣ Select your flight\n> 2️⃣ Choose passenger type\n> 3️⃣ Enter details\n> 4️⃣ Pick cabin class\n> 5️⃣ Receive confirmation",
        inline=False
    )
    
    embed.add_field(
        name="💡 Quick Tips",
        value="• Have your Roblox username ready\n• Check departure times carefully\n• Confirmation will be sent via DM",
        inline=False
    )
    
    embed.set_footer(text="Air Korea PTFS • Professional Flight Simulator")
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    
    view = FlightSelectView(client.flights, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@client.tree.command(name="adminpanel", description="Admin panel to manage flights")
@app_commands.describe(
    action="Choose an action",
    flight_code="Flight code (e.g., AK5453)",
    route="Flight route (e.g., HEATHROW → KOSICE)",
    aircraft="Aircraft type (e.g., Airbus A320-271N)",
    spots="Number of available spots",
    departure="Departure date and time (UTC format: YYYY-MM-DD HH:MM)",
    timezone="Timezone (e.g., Europe/London)"
)
async def admin_panel(interaction: discord.Interaction, action: str, flight_code: Optional[str] = None,
    route: Optional[str] = None, aircraft: Optional[str] = None, spots: Optional[int] = None,
    departure: Optional[str] = None, timezone: Optional[str] = "Europe/London"):
    
    # later was changed to role id check 
    if not any(role.name == ADMIN_ROLE_NAME for role in interaction.user.roles):
        await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
        return
    
    if action == "add":
        if not all([flight_code, route, aircraft, spots, departure]):
            await interaction.response.send_message("❌ Please provide all required fields: flight_code, route, aircraft, spots, departure", ephemeral=True)
            return
        
        client.flights[flight_code] = {
            "route": route,
            "aircraft": aircraft,
            "spots_left": spots,
            "departure": departure,
            "timezone": timezone
        }
        client.save_flights()
        
        await interaction.response.send_message(
            f"✅ Flight **{flight_code}** added successfully!\n"
            f"Route: {route}\n"
            f"Aircraft: {aircraft}\n"
            f"Spots: {spots}\n"
            f"Departure: {departure} ({timezone})",
            ephemeral=True
        )
    
    elif action == "delete":
        if not flight_code:
            await interaction.response.send_message("❌ Please provide a flight_code to delete", ephemeral=True)
            return
        
        if flight_code in client.flights:
            del client.flights[flight_code]
            client.save_flights()
            await interaction.response.send_message(f"✅ Flight **{flight_code}** deleted successfully!", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Flight **{flight_code}** not found!", ephemeral=True)
    
    elif action == "list":
        if not client.flights:
            await interaction.response.send_message("No flights available.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="✈️ Air Korea Fleet Status",
            description="Current active flights and availability",
            color=0x0066CC
        )
        
        for code, data in client.flights.items():
            passengers = len(client.bookings.get(code, []))
            total_seats = passengers + data['spots_left']
            
            embed.add_field(
                name=f"✈️ {code}",
                value=f"**Route:** {data['route']}\n"
                      f"**Aircraft:** {data['aircraft']}\n"
                      f"**Occupancy:** {passengers}/{total_seats} seats booked\n"
                      f"**Available:** {data['spots_left']} spots\n"
                      f"**Departure:** {data['departure']}",
                inline=False
            )
        
        embed.set_footer(text="Air Korea PTFS • Admin Panel")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    elif action == "passengers":
        if not flight_code:
            await interaction.response.send_message("❌ Please provide a flight_code to view passengers", ephemeral=True)
            return
        
        if flight_code not in client.flights:
            await interaction.response.send_message(f"❌ Flight **{flight_code}** not found!", ephemeral=True)
            return
        
        passengers = client.bookings.get(flight_code, [])
        
        if not passengers:
            await interaction.response.send_message(f"✈️ Flight **{flight_code}** has no passengers yet.", ephemeral=True)
            return
        
        flight_data = client.flights[flight_code]
        embed = discord.Embed(
            title=f"👥 Passenger Manifest - Flight {flight_code}",
            description=f"**Route:** {flight_data['route']}\n**Aircraft:** {flight_data['aircraft']}\n**Total Passengers:** {len(passengers)}",
            color=0x0066CC
        )
        
        # cabin class 
        economy = [p for p in passengers if p['cabin_class'] == 'Economy']
        premium = [p for p in passengers if p['cabin_class'] == 'Premium Economy']
        business = [p for p in passengers if p['cabin_class'] == 'Business']
        first = [p for p in passengers if p['cabin_class'] == 'First Class']
        
        if first:
            first_list = "\n".join([f"👑 `{p['roblox_username']}` - {p['booking_code']}" for p in first])
            embed.add_field(name="First Class", value=first_list, inline=False)
        
        if business:
            business_list = "\n".join([f"🛋️ `{p['roblox_username']}` - {p['booking_code']}" for p in business])
            embed.add_field(name="Business Class", value=business_list, inline=False)
        
        if premium:
            premium_list = "\n".join([f"🪑 `{p['roblox_username']}` - {p['booking_code']}" for p in premium])
            embed.add_field(name="Premium Economy", value=premium_list, inline=False)
        
        if economy:
            economy_list = "\n".join([f"💺 `{p['roblox_username']}` - {p['booking_code']}" for p in economy])
            embed.add_field(name="Economy Class", value=economy_list, inline=False)
        
        embed.set_footer(text=f"Air Korea PTFS • {len(passengers)} Total Passengers")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    else:
        await interaction.response.send_message("❌ Invalid action! Use: **add**, **delete**, **list**, or **passengers**", ephemeral=True)


@admin_panel.autocomplete('action')
async def action_autocomplete(interaction: discord.Interaction, current: str):
    actions = ['add', 'delete', 'list', 'passengers']
    return [app_commands.Choice(name=action, value=action) for action in actions if current.lower() in action.lower()]


async def update_flights_task():
    await client.wait_until_ready()
    while not client.is_closed():
        client.flights = client.load_flights()
        await asyncio.sleep(30)


@client.event
async def on_ready():
    await client.tree.sync()
    print(f'Online {client.user}')
    print(f'Bot')
    
    client.loop.create_task(update_flights_task())



if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        
        
        exit(1)
    
    client.run(TOKEN)
