
import os
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)
import logging

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
EMAIL, PASSWORD, MAIN_MENU, APP_SELECTION, ACTIVATION_PROOF, ADD_USER = range(6)

# File paths
DATA_DIR = "Data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
ACTIVATIONS_FILE = os.path.join(DATA_DIR, "activations.json")
APP_FILE = os.path.join(DATA_DIR, "ec_app.txt")
GUIDE_FILE = os.path.join(DATA_DIR, "ec_guide.txt")
RULES_FILE = os.path.join(DATA_DIR, "ec_rules.txt")

# Initialize files if they don't exist
for file_path in [USERS_FILE, ACTIVATIONS_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)

if not os.path.exists(APP_FILE):
    with open(APP_FILE, 'w') as f:
        f.write("paytmmoney\nangelone\nlemonn\nmstock\nupstox")

if not os.path.exists(GUIDE_FILE):
    with open(GUIDE_FILE, 'w') as f:
        f.write("Welcome to Earner Community Activation Guide")

if not os.path.exists(RULES_FILE):
    with open(RULES_FILE, 'w') as f:
        f.write("Earner Community Activation Rules")

# Apps that require screenshots
SCREENSHOT_APPS = ['mstock', 'angelone']

# Rejection reasons mapping
REJECTION_REASONS = {
    "77": "Incorrect Proof - Video/screenshot is incorrect, send correct recording showing process",
    "78": "Improper Activation - Activation not done properly, send correct video",
    "79": "Fraud Detected - Fraud detected, account not showing",
    "80": "Wrong Device - Activation not done on user's device",
    "81": "Late Submission - Activation completed after deadline",
    "nt": "Non Trade Approved"
}

# --- Helper Functions ---

def load_json(file_path):
    """Load JSON data with error handling"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_json(file_path, data):
    """Save data to JSON file"""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def read_emails():
    """Read user emails and credentials"""
    users = load_json(USERS_FILE)
    return {user['email']: {'name': user['name'], 'password': user['password'], 'chat_id': user.get('chat_id')} for user in users}

def read_apps():
    """Read available apps"""
    if os.path.exists(APP_FILE):
        with open(APP_FILE, 'r') as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []

def read_activations(email=None, app=None, mobile=None):
    """Read activation records with optional filtering"""
    activations = load_json(ACTIVATIONS_FILE)
    filtered = []

    for act in activations:
        if email and act['email'] != email:
            continue
        if app and act['app'] != app:
            continue
        if mobile and act['mobile'] != mobile.replace(" ", ""):
            continue
        filtered.append(act)

    return filtered

def is_duplicate(app, mobile):
    """Check for duplicate activations"""
    activations = read_activations(app=app)
    mobile_clean = mobile.replace(" ", "")
    return any(
        act['mobile'] == mobile_clean and act['status'] in ['pending', 'approved']
        for act in activations
    )

def write_activation(email, app, mobile, status="pending", reason="pending"):
    """Write new activation record"""
    activations = load_json(ACTIVATIONS_FILE)
    activations.append({
        'email': email,
        'mobile': mobile.replace(" ", ""),
        'app': app,
        'status': status,
        'reason': reason,
        'timestamp': datetime.now().isoformat(),
        'submission_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_json(ACTIVATIONS_FILE, activations)

def update_activation(email, app, mobile, status, reason="0"):
    """Update existing activation record"""
    activations = load_json(ACTIVATIONS_FILE)
    updated = False

    for act in activations:
        if (act['email'] == email and
            act['app'] == app and
            act['mobile'] == mobile.replace(" ", "")):
            act['status'] = status
            act['reason'] = reason
            act['timestamp'] = datetime.now().isoformat()
            updated = True
            break

    if updated:
        save_json(ACTIVATIONS_FILE, activations)
    return updated

def add_user(email, password, name, chat_id=None):
    """Add new user"""
    users = load_json(USERS_FILE)

    # Check if user already exists
    if any(user['email'].lower() == email.lower() for user in users):
        # Update chat_id if user exists but chat_id is missing
        for user in users:
            if user['email'].lower() == email.lower() and not user.get('chat_id') and chat_id:
                user['chat_id'] = chat_id
                save_json(USERS_FILE, users)
                return True, "User chat_id updated"
        return False, "User already exists"

    users.append({
        'email': email.lower(),
        'password': password,
        'name': name,
        'chat_id': chat_id,
        'created_at': datetime.now().isoformat()
    })

    save_json(USERS_FILE, users)
    return True, "User added successfully"

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command handler"""
    if context.user_data.get('admin_mode'):
        await update.message.reply_text("Admin mode active. Please send user details in format:\n\nemail\npassword\nname")
        return ADD_USER

    # Store chat_id for potential new user
    context.user_data['chat_id'] = update.effective_chat.id

    await update.message.reply_text(
        "🌟 *Welcome to Earner Community Activation Bot!* 🌟\n\n"
        "Please enter your registered *email address*:",
        parse_mode='Markdown'
    )
    return EMAIL

async def email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process email input"""
    email = update.message.text.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await update.message.reply_text("❌ Invalid email format. Please enter a valid email address:")
        return EMAIL

    context.user_data['email'] = email
    await update.message.reply_text("🔒 Please enter your *password*:", parse_mode='Markdown')
    return PASSWORD

async def password_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process password input and login"""
    password = update.message.text.strip()
    email = context.user_data['email']
    users = read_emails()

    if email in users and users[email]['password'] == password:
        # Update chat_id if not already set
        if not users[email].get('chat_id'):
            users_data = load_json(USERS_FILE)
            for user in users_data:
                if user['email'] == email:
                    user['chat_id'] = update.effective_chat.id
                    save_json(USERS_FILE, users_data)
                    break

        context.user_data['name'] = users[email]['name']
        await update.message.reply_text(
            "✅ *Login successful!* 🎉\n\n"
            "You can now access all features of the bot.",
            parse_mode='Markdown'
        )
        return await main_menu(update, context)
    else:
        await update.message.reply_text(
            "❌ *Invalid email or password.*\n\n"
            "Please enter your *email address* again:",
            parse_mode='Markdown'
        )
        return EMAIL

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display main menu"""
    try:
        if update.callback_query:
            await update.callback_query.answer()
            message_editor = update.callback_query.edit_message_text
        else:
            message_editor = update.message.reply_text

        name = context.user_data.get('name', 'User')
        email = context.user_data.get('email', '')

        keyboard = [
            [InlineKeyboardButton("📊 My Activation Status", callback_data='status')],
            [InlineKeyboardButton("📤 Send Activation Proof", callback_data='proof')],
            [InlineKeyboardButton("📖 How To Work Guide", callback_data='guide')],
            [InlineKeyboardButton("📜 Activation Rules", callback_data='rules')],
        ]

        await message_editor(
            f"👋 *Hello {name}!* ({email})\n\n"
            "🔹 *Main Menu* - Please select an option:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in main_menu: {e}")
        if update.message:
            await update.message.reply_text("An error occurred. Please try again.")
        return ConversationHandler.END

async def activation_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show activation status"""
    try:
        query = update.callback_query
        await query.answer()

        email = context.user_data['email']
        activations = read_activations(email=email)

        if activations:
            text = "📊 *Your Activation Status:*\n\n"
            for act in activations:
                status = act['status'].capitalize()
                reason = REJECTION_REASONS.get(act['reason'], act['reason'])

                status_emoji = "✅" if status == "Approved" else "❌" if status == "Rejected" else "⏳"

                text += (
                    f"{status_emoji} *{act['app'].upper()}*\n"
                    f"📱 *Mobile:* `{act['mobile']}`\n"
                    f"🔄 *Status:* {status}\n"
                    f"📝 *Reason:* {reason}\n"
                    f"📅 *Date:* {act['submission_date'].split()[0]}\n\n"
                )
        else:
            text = "ℹ️ No activations found. Submit your first activation proof!"

        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ])
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in activation_status: {e}")
        if update.message:
            await update.message.reply_text("An error occurred while fetching your status.")
        return MAIN_MENU

async def send_activation_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guide user to send activation proof"""
    try:
        query = update.callback_query
        await query.answer()

        if query.data == 'same_app':
            app = context.user_data['selected_app']
            media_type = "screenshot/video" if app in SCREENSHOT_APPS else "video"
            await query.edit_message_text(
                f"📤 *Send proof for {app.upper()}*\n\n"
                f"Please send {media_type} with mobile number in caption\n"
                f"Example: `9876543210` (10 digits only, no spaces)",
                parse_mode='Markdown'
            )
            return ACTIVATION_PROOF

        apps = read_apps()
        if not apps:
            await query.edit_message_text(
                "⚠️ No apps available for activation.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data='back')]
                ])
            )
            return MAIN_MENU

        keyboard = [
            [InlineKeyboardButton(app.upper(), callback_data=f'app_{app}')]
            for app in apps
        ]
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back')])

        await query.edit_message_text(
            "📲 *Select application for activation:*",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return APP_SELECTION
    except Exception as e:
        logger.error(f"Error in send_activation_proof: {e}")
        if update.message:
            await update.message.reply_text("An error occurred. Please try again.")
        return MAIN_MENU

async def app_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle app selection"""
    try:
        query = update.callback_query
        await query.answer()

        app = query.data.replace('app_', '').lower()
        context.user_data['selected_app'] = app
        media_type = "screenshot or video" if app in SCREENSHOT_APPS else "video"

        await query.edit_message_text(
            f"📤 *Send proof for {app.upper()}*\n\n"
            f"Please send {media_type} with mobile number in caption\n"
            f"Example: `9876543210` (10 digits only, no spaces)\n\n"
            f"⚠️ *Important:* Make sure the proof clearly shows the activation process.",
            parse_mode='Markdown'
        )
        return ACTIVATION_PROOF
    except Exception as e:
        logger.error(f"Error in app_selected: {e}")
        if update.message:
            await update.message.reply_text("An error occurred. Please try again.")
        return MAIN_MENU

async def process_activation_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process submitted activation proof"""
    try:
        app = context.user_data.get('selected_app')
        if not app:
            await update.message.reply_text("❌ No app selected. Please start over.")
            return MAIN_MENU

        # Check media type based on app
        media = None
        media_type = None

        # For screenshot apps, accept either photo or video
        if app in SCREENSHOT_APPS:
            if update.message.photo:
                media = update.message.photo[-1].file_id
                media_type = "photo"
            elif update.message.video:
                media = update.message.video.file_id
                media_type = "video"
            else:
                await update.message.reply_text(
                    f"❌ Please send a screenshot or video for {app.upper()}\n\n"
                    "For this app, we accept either screenshots or videos as proof."
                )
                return ACTIVATION_PROOF
        else:
            if not update.message.video:
                await update.message.reply_text(f"❌ Please send a video for {app.upper()}")
                return ACTIVATION_PROOF
            media = update.message.video.file_id
            media_type = "video"

        # Validate mobile number in caption
        if not update.message.caption:
            await update.message.reply_text("❌ Please include mobile number in caption")
            return ACTIVATION_PROOF

        mobile = update.message.caption.strip()
        if not re.fullmatch(r'\d{10}', mobile):
            await update.message.reply_text(
                "❌ *Invalid mobile number*\n\n"
                "Must be 10 digits without spaces.\n"
                "Example: `9876543210`",
                parse_mode='Markdown'
            )
            return ACTIVATION_PROOF

        # Check for duplicates
        if is_duplicate(app, mobile):
            await update.message.reply_text(
                f"❌ *Duplicate Activation*\n\n"
                f"This mobile number is already used for {app.upper()}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Different App", callback_data='proof')],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data='back')]
                ])
            )
            return MAIN_MENU

        # Get user email
        email = context.user_data.get('email')
        if not email:
            await update.message.reply_text("❌ Session expired. Please /start again.")
            return ConversationHandler.END

        # Record activation
        write_activation(email, app, mobile)

        # Send to channel with approval buttons
        channel_id = os.getenv('CHANNEL_ID')
        if channel_id:
            caption = (
                f"📬 *New Activation Request*\n\n"
                f"📲 *App:* {app.upper()}\n"
                f"📧 *Email:* `{email}`\n"
                f"📱 *Mobile:* `{mobile}`\n\n"
                f"🔄 *Status:* ⏳ Pending"
            )

            rejection_reasons = {
                "Incorrect Proof": "77",
                "Improper Activation": "78",
                "Fraud Detected": "79",
                "Wrong Device": "80",
                "Late Submission": "81"
            }

            keyboard = []
            if app == 'angelone':
                keyboard.append([InlineKeyboardButton("✅ Non Trade Approved", callback_data=f'reason_nt_{email}_{app}_{mobile}')])

            keyboard.append([
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{email}_{app}_{mobile}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{email}_{app}_{mobile}")
            ])

            for reason_text, reason_id in rejection_reasons.items():
                keyboard.append([InlineKeyboardButton(f"❌ {reason_text}", callback_data=f'reason_{reason_id}_{email}_{app}_{mobile}')])

            try:
                if media_type == "photo":
                    message = await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=media,
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    message = await context.bot.send_video(
                        chat_id=channel_id,
                        video=media,
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

                # Store message_id for potential future updates
                activations = load_json(ACTIVATIONS_FILE)
                for act in activations:
                    if (act['email'] == email and 
                        act['app'] == app and 
                        act['mobile'] == mobile.replace(" ", "")):
                        act['message_id'] = message.message_id
                        break
                save_json(ACTIVATIONS_FILE, activations)

            except Exception as e:
                logger.error(f"Failed to send to channel: {e}")
                # Notify admin about the error
                admin_id = os.getenv('ADMIN_CHAT_ID')
                if admin_id:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"❌ Failed to send activation to channel:\n\nApp: {app}\nEmail: {email}\nError: {e}"
                    )

        # Simplified success message without status details
        keyboard = [
            [InlineKeyboardButton("📤 Send Another (Same App)", callback_data='same_app')],
            [InlineKeyboardButton("📲 Select Another App", callback_data='proof')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='back')]
        ]

        await update.message.reply_text(
            "✅ *Activation submitted successfully!*\n\n"
            "You can check your status anytime in the main menu.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    except Exception as e:
        logger.error(f"Error in activation proof processing: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *An error occurred*\n\n"
            "Please try again or contact support if the problem persists.",
            parse_mode='Markdown'
        )
        return MAIN_MENU

async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display guide"""
    try:
        query = update.callback_query
        await query.answer()

        guide_text = "*Guide not available yet.*\n\nCheck back later or contact admin."
        if os.path.exists(GUIDE_FILE):
            with open(GUIDE_FILE, 'r') as f:
                guide_text = f.read()

        await query.edit_message_text(
            f"📖 *Earner Community Guide*\n\n{guide_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ])
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in show_guide: {e}")
        if update.message:
            await update.message.reply_text("An error occurred while loading the guide.")
        return MAIN_MENU

async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display rules"""
    try:
        query = update.callback_query
        await query.answer()

        rules_text = "*Rules not available yet.*\n\nCheck back later or contact admin."
        if os.path.exists(RULES_FILE):
            with open(RULES_FILE, 'r') as f:
                rules_text = f.read()

        await query.edit_message_text(
            f"📜 *Earner Community Rules*\n\n{rules_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ])
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in show_rules: {e}")
        if update.message:
            await update.message.reply_text("An error occurred while loading the rules.")
        return MAIN_MENU

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to main menu"""
    try:
        query = update.callback_query
        await query.answer()
        return await main_menu(update, context)
    except Exception as e:
        logger.error(f"Error in back_to_menu: {e}")
        if update.message:
            await update.message.reply_text("An error occurred. Please try again.")
        return MAIN_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation"""
    context.user_data.clear()
    await update.message.reply_text(
        "🚫 Operation cancelled. Type /start to begin again.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# --- Admin Commands ---

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add users"""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return ConversationHandler.END

    context.user_data['admin_mode'] = True
    await update.message.reply_text(
        "🛠 *Admin User Addition Mode*\n\n"
        "Please send user details in this format:\n\n"
        "`email@example.com`\n"
        "`password123`\n"
        "`User Name`\n\n"
        "You can send multiple users separated by blank lines.",
        parse_mode='Markdown'
    )
    return ADD_USER

async def add_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user addition"""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Please provide valid user details")
        return ADD_USER

    user_entries = [entry for entry in text.split('\n\n') if entry.strip()]
    results = []

    for entry in user_entries:
        parts = [p.strip() for p in entry.split('\n') if p.strip()]
        if len(parts) < 3:
            results.append(f"❌ Invalid format: {entry[:30]}...")
            continue

        email, password, name = parts[0], parts[1], ' '.join(parts[2:])
        success, message = add_user(email, password, name)
        results.append(f"{'✅' if success else '❌'} {message}: `{email}`")

    await update.message.reply_text(
        "\n".join(results),
        parse_mode='Markdown'
    )
    await update.message.reply_text(
        "Send more user details in the same format or /cancel to exit admin mode."
    )
    return ADD_USER

async def send_json_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to send JSON files"""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return

    try:
        # Send users.json
        with open(USERS_FILE, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename='users.json',
                caption='Here is the users data file'
            )

        # Send activations.json
        with open(ACTIVATIONS_FILE, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename='activations.json',
                caption='Here is the activations data file'
            )
    except Exception as e:
        logger.error(f"Error sending JSON files: {e}")
        await update.message.reply_text("❌ Failed to send JSON files. Check logs for details.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows help information for users and admins."""
    user_id = str(update.effective_user.id)
    admin_id = os.getenv('ADMIN_CHAT_ID')

    help_text = """🤖 *Earner Community Bot Help*

*For Users:*
/start - Start the bot and login
/help - Show this help message

*Bot Features:*
• View activation status
• Submit activation proof
• Access guide and rules
• Secure login system

*How to use:*
1. Start with /start
2. Enter your registered email and password
3. Choose from the menu options
4. Follow the prompts to submit activation proof

*Need Help?*
Make sure to follow the activation rules and submit valid proof for each app.
"""

    if user_id == admin_id:
        help_text += """

*Admin Commands:*
/adduser - Add new users to the system
/stats - View bot statistics
/listusers - List all registered users
/sendreport - Send activity reports
/sendjson - Send raw JSON data files
/broadcast - Broadcast message to users
/help - Show this help

*Admin Features:*
• Approve/reject activations
• View detailed statistics
• Manage users
• Generate reports
"""

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get bot statistics."""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return

    users = load_json(USERS_FILE)
    activations = load_json(ACTIVATIONS_FILE)

    # Calculate statistics
    total_users = len(users)
    total_activations = len(activations)
    pending_activations = len([a for a in activations if a['status'] == 'pending'])
    approved_activations = len([a for a in activations if a['status'] == 'approved'])
    rejected_activations = len([a for a in activations if a['status'] == 'rejected'])

    # App-wise statistics
    app_stats = {}
    for activation in activations:
        app = activation['app']
        if app not in app_stats:
            app_stats[app] = {'total': 0, 'approved': 0, 'pending': 0, 'rejected': 0}
        app_stats[app]['total'] += 1
        app_stats[app][activation['status']] += 1

    stats_text = f"""📊 *Bot Statistics*

👥 *Users:* {total_users}
📱 *Total Activations:* {total_activations}
⏳ *Pending:* {pending_activations}
✅ *Approved:* {approved_activations}
❌ *Rejected:* {rejected_activations}

📲 *App-wise Statistics:*
"""

    for app, stats in app_stats.items():
        stats_text += f"\n*{app.upper()}*\n"
        stats_text += f"  • Total: {stats['total']}\n"
        stats_text += f"  • Approved: {stats['approved']}\n"
        stats_text += f"  • Pending: {stats['pending']}\n"
        stats_text += f"  • Rejected: {stats['rejected']}\n"

    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to list all users."""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return

    users = load_json(USERS_FILE)
    if not users:
        await update.message.reply_text("No users found.")
        return

    users_text = "👥 *Registered Users*\n\n"
    for i, user in enumerate(users[:20], 1):  # Limit to first 20 users
        join_date = datetime.fromisoformat(user['created_at']).strftime('%Y-%m-%d')
        users_text += f"{i}. *{user['name']}*\n   📧 `{user['email']}`\n   📅 {join_date}\n\n"

    if len(users) > 20:
        users_text += f"... and {len(users) - 20} more users.\n"
        users_text += f"*Total:* {len(users)} users"

    await update.message.reply_text(users_text, parse_mode='Markdown')

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast message to all users."""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return

    if not context.args:
        await update.message.reply_text(
            "Please provide a message to broadcast.\n"
            "Usage: /broadcast Your message here"
        )
        return

    message = ' '.join(context.args)
    users = load_json(USERS_FILE)
    successful = 0
    failed = 0

    for user in users:
        if user.get('chat_id'):
            try:
                await context.bot.send_message(
                    chat_id=user['chat_id'],
                    text=f"📢 *Community Announcement*\n\n{message}",
                    parse_mode='Markdown'
                )
                successful += 1
            except Exception as e:
                logger.error(f"Failed to send to {user['email']}: {e}")
                failed += 1

    await update.message.reply_text(
        f"📢 Broadcast Results:\n\n"
        f"✅ Successful: {successful}\n"
        f"❌ Failed: {failed}\n\n"
        f"Total users: {len(users)}"
    )

# --- Admin Callback Handlers ---

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin approval"""
    try:
        query = update.callback_query
        await query.answer()

        _, email, app, mobile = query.data.split('_')
        update_activation(email, app, mobile, "approved")

        # Update the channel message
        channel_id = os.getenv('CHANNEL_ID')
        if channel_id:
            try:
                activations = load_json(ACTIVATIONS_FILE)
                message_id = None
                for act in activations:
                    if (act['email'] == email and 
                        act['app'] == app and 
                        act['mobile'] == mobile.replace(" ", "")):
                        message_id = act.get('message_id')
                        break

                if message_id:
                    await context.bot.edit_message_caption(
                        chat_id=channel_id,
                        message_id=message_id,
                        caption=(
                            f"✅ *Approved Activation*\n\n"
                            f"📲 *App:* {app.upper()}\n"
                            f"📧 *Email:* `{email}`\n"
                            f"📱 *Mobile:* `{mobile}`\n\n"
                            f"🔄 *Status:* ✅ Approved"
                        ),
                        parse_mode='Markdown',
                        reply_markup=None  # Remove buttons after approval
                    )
            except Exception as e:
                logger.error(f"Failed to update channel message: {e}")

        await query.edit_message_text(
            text=(
                f"✅ *Approved Activation*\n\n"
                f"📲 *App:* {app.upper()}\n"
                f"📧 *Email:* `{email}`\n"
                f"📱 *Mobile:* `{mobile}`"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in admin_approve: {e}")
        try:
            await query.answer("Failed to process approval")
        except:
            pass

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin rejection"""
    try:
        query = update.callback_query
        await query.answer()

        _, email, app, mobile = query.data.split('_')

        rejection_reasons = {
            "Incorrect Proof": "77",
            "Improper Activation": "78",
            "Fraud Detected": "79",
            "Wrong Device": "80",
            "Late Submission": "81"
        }

        keyboard = []
        if app == 'angelone':
            keyboard.append([InlineKeyboardButton("✅ Non Trade Approved", callback_data=f'reason_nt_{email}_{app}_{mobile}')])

        for reason_text, reason_id in rejection_reasons.items():
            keyboard.append([InlineKeyboardButton(f"❌ {reason_text}", callback_data=f'reason_{reason_id}_{email}_{app}_{mobile}')])

        await query.edit_message_text(
            text=f"Select rejection reason for {app.upper()}:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in admin_reject: {e}")
        try:
            await query.answer("Failed to process rejection")
        except:
            pass

async def process_rejection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process rejection reason"""
    try:
        query = update.callback_query
        await query.answer()

        parts = query.data.split('_')
        reason_id = parts[1]
        email = parts[2]
        app = parts[3]
        mobile = parts[4]

        reason_text = REJECTION_REASONS.get(reason_id, "Unknown reason")

        if app == 'angelone' and reason_id == 'nt':
            status = "approved"
        else:
            status = "rejected"

        update_activation(email, app, mobile, status, reason_id)

        # Update the channel message
        channel_id = os.getenv('CHANNEL_ID')
        if channel_id:
            try:
                activations = load_json(ACTIVATIONS_FILE)
                message_id = None
                for act in activations:
                    if (act['email'] == email and 
                        act['app'] == app and 
                        act['mobile'] == mobile.replace(" ", "")):
                        message_id = act.get('message_id')
                        break

                if message_id:
                    await context.bot.edit_message_caption(
                        chat_id=channel_id,
                        message_id=message_id,
                        caption=(
                            f"❌ *{'Rejected' if status == 'rejected' else 'Approved with Note'} Activation*\n\n"
                            f"📲 *App:* {app.upper()}\n"
                            f"📧 *Email:* `{email}`\n"
                            f"📱 *Mobile:* `{mobile}`\n\n"
                            f"🔄 *Status:* {'❌ Rejected' if status == 'rejected' else '✅ Approved'}\n"
                            f"📝 *Reason:* {reason_text}"
                        ),
                        parse_mode='Markdown',
                        reply_markup=None  # Remove buttons after rejection
                    )
            except Exception as e:
                logger.error(f"Failed to update channel message: {e}")

        await query.edit_message_text(
            text=(
                f"❌ *{'Rejected' if status == 'rejected' else 'Approved with Note'} Activation*\n\n"
                f"📲 *App:* {app.upper()}\n"
                f"📧 *Email:* `{email}`\n"
                f"📱 *Mobile:* `{mobile}`\n\n"
                f"📝 *Reason:* {reason_text}"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in process_rejection: {e}")
        try:
            await query.answer("Failed to process rejection reason")
        except:
            pass

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify admin"""
    logger.error(f"Update {update} caused error {context.error}")

    # Notify admin about the error
    admin_id = os.getenv('ADMIN_CHAT_ID')
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"⚠️ Bot Error:\n\n{context.error}\n\nUpdate: {update}"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin about error: {e}")

# --- Report Functions ---

async def send_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to send reports"""
    if str(update.effective_user.id) != os.getenv('ADMIN_CHAT_ID'):
        await update.message.reply_text("❌ This command is for admin only.")
        return

    await send_reports(context)
    await update.message.reply_text("📊 Reports sent successfully!")

async def send_reports(context: ContextTypes.DEFAULT_TYPE):
    """Sends generated reports as CSV files to the admin chat."""
    admin_id = os.getenv('ADMIN_CHAT_ID')
    if not admin_id:
        logger.warning("ADMIN_CHAT_ID not set. Cannot send reports.")
        return

    user_report, act_report = generate_reports()

    from io import BytesIO

    # Send user report as a file
    user_file = BytesIO(user_report.encode('utf-8'))
    user_file.name = f"users_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    await context.bot.send_document(
        chat_id=admin_id,
        document=user_file,
        caption="📊 User Report",
        filename=user_file.name
    )

    # Send activations report as a file
    act_file = BytesIO(act_report.encode('utf-8'))
    act_file.name = f"activations_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    await context.bot.send_document(
        chat_id=admin_id,
        document=act_file,
        caption="📊 Activations Report",
        filename=act_file.name
    )

def generate_reports():
    """Generates user and activation reports in CSV format."""
    users = load_json(USERS_FILE)
    user_report = "Email,Name,Join Date,Chat ID\n"
    for user in users:
        join_date = datetime.fromisoformat(user['created_at']).strftime('%Y-%m-%d %H:%M')
        user_report += f"{user['email']},{user['name']},{join_date},{user.get('chat_id', 'N/A')}\n"

    activations = load_json(ACTIVATIONS_FILE)
    act_report = "Email,Mobile,App,Status,Reason,Submission Date\n"
    for act in activations:
        act_report += f"{act['email']},{act['mobile']},{act['app']},{act['status']},{act['reason']},{act['submission_date']}\n"

    return user_report, act_report

def main() -> None:
    """Start the bot"""
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN not found in environment variables.")
        return

    admin_id = os.getenv('ADMIN_CHAT_ID')
    channel_id = os.getenv('CHANNEL_ID')

    if not admin_id:
        logger.warning("ADMIN_CHAT_ID not set. Admin features will be limited.")
    if not channel_id:
        logger.warning("CHANNEL_ID not set. Activation proofs won't be forwarded.")

    try:
        application = Application.builder().token(telegram_token).build()
        logger.info("Earner Community Bot starting...")
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        return

    # Admin conversation handler
    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('adduser', add_user_command)],
        states={
            ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Main conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_input)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_input)],
            ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_handler)],
            MAIN_MENU: [
                CallbackQueryHandler(activation_status, pattern='^status$'),
                CallbackQueryHandler(send_activation_proof, pattern='^proof$'),
                CallbackQueryHandler(show_guide, pattern='^guide$'),
                CallbackQueryHandler(show_rules, pattern='^rules$'),
                CallbackQueryHandler(back_to_menu, pattern='^back$'),
                CallbackQueryHandler(send_activation_proof, pattern='^same_app$'),
            ],
            APP_SELECTION: [
                CallbackQueryHandler(app_selected, pattern='^app_'),
                CallbackQueryHandler(back_to_menu, pattern='^back$'),
            ],
            ACTIVATION_PROOF: [
                MessageHandler(
                    (filters.VIDEO | filters.PHOTO) & filters.CAPTION,
                    process_activation_proof
                ),
                CallbackQueryHandler(back_to_menu, pattern='^back$'),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Add command handlers
    application.add_handler(CommandHandler('sendreport', send_report_command))
    application.add_handler(CommandHandler('sendjson', send_json_command))
    application.add_handler(CommandHandler('stats', stats_command))
    application.add_handler(CommandHandler('listusers', list_users_command))
    application.add_handler(CommandHandler('broadcast', broadcast_command))
    application.add_handler(CommandHandler('help', help_command))

    # Add callback handlers
    application.add_handler(CallbackQueryHandler(admin_approve, pattern='^approve_'))
    application.add_handler(CallbackQueryHandler(admin_reject, pattern='^reject_'))
    application.add_handler(CallbackQueryHandler(process_rejection, pattern='^reason_'))

    # Add conversation handlers
    application.add_handler(admin_conv_handler)
    application.add_handler(conv_handler)
    application.add_error_handler(error)

    # Schedule reports to be sent every 3 hours
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            callback=send_reports,
            interval=timedelta(hours=3),
            first=0
        )

    # Start the bot
    try:
        logger.info("Bot is now running and polling for updates...")
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot encountered an error: {e}")
    finally:
        logger.info("Bot shutdown complete")

if __name__ == '__main__':
    main()
