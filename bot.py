import json
import logging
import os
import random
import asyncio
import time
import re  # For regex operations to remove emojis and hashtags
import datetime  # For handling dates and times
from base64 import urlsafe_b64decode, urlsafe_b64encode

from telethon import TelegramClient, events, Button, errors
from telethon.sessions import StringSession
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# If your custom LLM is accessible via HTTP, for example, you can import requests:
# import requests

# Load environment variables from .env file
load_dotenv()

# Set up logging to include more details
logging.basicConfig(level=logging.INFO)

# Your provided API ID and Hash from the .env file
api_id = int(os.environ.get('API_ID'))
api_hash = os.environ.get('API_HASH')

# Bot Token from BotFather from the .env file
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Now GROUP_ID is taken from the .env file instead of hard-coded
GROUP_ID = int(os.environ.get('GROUP_ID'))  # e.g. -1002289609082

# Encryption key from .env
encryption_key = os.environ.get('ENCRYPTION_KEY')
if not encryption_key:
    raise ValueError("ENCRYPTION_KEY not found in .env")

# Initialize Fernet object for encryption/decryption
fernet = Fernet(encryption_key)

bot = TelegramClient('bot_session', api_id, api_hash)


def encrypt_field(field_value):
    """Encrypt a sensitive field value using Fernet."""
    if field_value is None or field_value == '':
        return field_value
    encrypted = fernet.encrypt(field_value.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_field(field_value):
    """Decrypt a sensitive field value using Fernet."""
    if field_value is None or field_value == '':
        return field_value
    try:
        decrypted = fernet.decrypt(field_value.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception:
        # If there's an error decrypting, return as-is (for backward compatibility)
        return field_value


def load_user_data():
    """Load user data from the JSON file and decrypt sensitive fields."""
    if os.path.exists("user_data.json"):
        with open("user_data.json", "r") as f:
            data = json.load(f)
            # Decrypt sensitive fields
            for user_id, user_info in data.items():
                linked_accounts = user_info.get('linked_accounts', [])
                for acc in linked_accounts:
                    if 'session_string' in acc and acc['session_string']:
                        acc['session_string'] = decrypt_field(acc['session_string'])
                    if 'phone' in acc and acc['phone']:
                        acc['phone'] = decrypt_field(acc['phone'])
            logging.debug(f"Loaded and decrypted user data: {data}")
            return data
    return {}


def save_user_data(data):
    """Encrypt sensitive fields and save user data to the JSON file."""
    data_copy = json.loads(json.dumps(data))
    for user_id, user_info in data_copy.items():
        linked_accounts = user_info.get('linked_accounts', [])
        for acc in linked_accounts:
            if 'session_string' in acc and acc['session_string']:
                acc['session_string'] = encrypt_field(acc['session_string'])
            if 'phone' in acc and acc['phone']:
                acc['phone'] = encrypt_field(acc['phone'])

    with open("user_data.json", "w") as f:
        json.dump(data_copy, f, indent=4)


def load_chat_groups():
    """Load chat group data from JSON file."""
    if os.path.exists("chat_groups.json"):
        with open("chat_groups.json", "r") as f:
            data = json.load(f)
            logging.debug(f"Loaded chat group data: {data}")
            return data
    return {}


def save_chat_groups(chat_groups_data):
    """Save chat group data to JSON file."""
    with open("chat_groups.json", "w") as f:
        json.dump(chat_groups_data, f, indent=4)


user_data = load_user_data()
chat_groups = load_chat_groups()
user_state = {}
last_bot_message_id = {}
linked_user_clients = {}  # {(user_id, telegram_id): client}
temp_user_data = {}
message_tracker = {}  # {(user_id, telegram_id): {chat_id: [timestamps]}}
reply_tracker = {}    # {(user_id, telegram_id): {chat_id: set(reply_to_msg_ids)}}
autoreply_tracker = {}  # {(user_id, telegram_id): {chat_id: set(message_ids)}}
client_tasks = {}  # {(user_id, telegram_id): task}


async def check_membership(user_id):
    """Check if the user is a member of the specified group."""
    try:
        participants = await bot.get_participants(GROUP_ID)
        logging.debug(f"Participants fetched for group: {participants}")
        return any(p.id == user_id for p in participants)
    except Exception as e:
        logging.error(f"Error checking membership: {e}")
        return False


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    user_id = event.sender_id
    logging.debug(f"Received /start from user {user_id}")
    is_member = await check_membership(user_id)
    if is_member:
        buttons = [
            [Button.inline("Create AI Agent (max 2 Agents)", b"start_create_npc")],
            [Button.inline("Edit AI Agent", b"start_edit_npc")],
            [Button.inline("Instructional Video", b"start_instructional_video")],
            [Button.inline("Exit", b"start_exit")]
        ]
    else:
        buttons = [
            [Button.inline("Create AI Agent (max 1 Agent)", b"start_create_npc")],
            [Button.inline("Edit AI Agent", b"start_edit_npc")],
            [Button.inline("Instructional Video", b"start_instructional_video")],
            [Button.inline("Exit", b"start_exit")]
        ]
    msg = await event.respond(
        "Welcome. Use the Edit AI Agent button to manage the existing Telegram user accounts linked to this bot or Create AI Agent button to link a Telegram user account.",
        buttons=buttons
    )
    last_bot_message_id[user_id] = msg.id
    logging.debug(f"Displayed start menu to user {user_id}")


@bot.on(events.CallbackQuery)
async def start_menu_handler(event):
    user_id = event.sender_id
    data = event.data.decode("utf-8")
    logging.debug(f"Handling callback from user {user_id} with action {data}")

    if data == "start_create_npc":
        current_user_data = load_user_data()
        linked_accounts = current_user_data.get(str(user_id), {}).get('linked_accounts', [])
        is_member = await check_membership(user_id)
        max_accounts = 2 if is_member else 1
        if len(linked_accounts) >= max_accounts:
            await event.respond(f"You have reached the maximum number of {max_accounts} Agent{'s' if max_accounts > 1 else ''}.")
            return
        await createnpc(event)
    elif data == "start_edit_npc":
        await editnpc_command(event)
    elif data == "start_instructional_video":
        await send_instructional_video(event)
        return
    elif data == "start_exit":
        await event.respond("Exited.")
        return
    else:
        await callback_query_handler(event)


async def send_instructional_video(event):
    try:
        user_id = event.sender_id
        video_file_path = "NPC_BOT_Instructions.mp4"
        if os.path.exists(video_file_path):
            await event.respond("Uploading the instructional video. This could take 1-3 minutes. Please wait...")
            await bot.send_file(user_id, video_file_path, caption="NPC Bot Instructional Video")
        else:
            await event.respond("Instructional video not found.")
    except Exception as e:
        logging.error(f"Error sending instructional video: {e}")
        await event.respond("Failed to send the instructional video.")


async def createnpc(event):
    user_id = event.sender_id
    logging.debug(f"Received createnpc from user {user_id}")
    buttons = [
        [Button.inline("Link with phone #", b"link_phone")],
        [Button.inline("Link with session string", b"link_session")],
        [Button.inline("Back", b"back")]
    ]
    msg = await event.respond("How would you like to link the account?", buttons=buttons)
    last_bot_message_id[user_id] = msg.id
    logging.debug(f"Displaying link options for user {user_id}")


async def editnpc_command(event):
    user_id = event.sender_id
    logging.debug(f"Received editnpc from user {user_id}")

    current_user_data = load_user_data()

    if str(user_id) not in current_user_data or not current_user_data[str(user_id)].get('linked_accounts'):
        await event.respond("You don't have any linked accounts to edit.")
        return

    buttons = []
    for account in current_user_data[str(user_id)]['linked_accounts']:
        name = f"{account.get('first_name', '')} {account.get('last_name', '')}".strip() or "Unknown Account"
        buttons.append([Button.inline(name, data=f"chat_groups_{account['telegram_id']}")])

    buttons.append([Button.inline("Exit", data="exit")])

    msg = await event.respond("Select an account to edit:", buttons=buttons)
    last_bot_message_id[user_id] = msg.id


async def callback_query_handler(event):
    user_id = event.sender_id
    data = event.data.decode("utf-8")
    logging.debug(f"Handling callback from user {user_id} with action {data}")

    if data == "back":
        await event.respond("Returning to previous menu.")
        return

    if data == "link_phone":
        user_state[user_id] = 'awaiting_phone'
        msg = await event.respond(
            "To link a Telegram account using a phone number, you must enter the account info for a DIFFERENT account than the one you are using now. You need 2 or more accounts OR a trusted friend. Provide your phone number with country code (Example: +15557778888):"
        )
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"Set state to 'awaiting_phone' for user {user_id} with message ID {msg.id}")

    elif data == "link_session":
        user_state[user_id] = 'awaiting_session_string'
        msg = await event.respond(
            "Enter the Session String for the account you wish to link."
        )
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"Set state to 'awaiting_session_string' for user {user_id} with message ID {msg.id}")

    elif data == 'confirm':
        await create_session(user_id, event)

    elif data == 'start_over':
        user_state[user_id] = 'awaiting_phone'
        msg = await event.respond("Let's start over. Provide your phone number with country code:")
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"Set state to 'awaiting_phone' for user {user_id} with message ID {msg.id}")

    elif data == "exit":
        await event.respond("Exited.")
        return

    elif data.startswith("chat_groups_"):
        telegram_id = int(data.split("_")[2])
        buttons = [
            [Button.inline("List of Current Chat Groups", data=f"list_groups_{telegram_id}")],
            [Button.inline("Add Chat Group", data=f"add_group_{telegram_id}")],
            [Button.inline("UNLINK Account", data=f"unlink_account_{telegram_id}")],
            [Button.inline("Back", data=f"back_to_editnpc")]
        ]
        msg = await event.respond("Chat Groups Menu:", buttons=buttons)
        last_bot_message_id[user_id] = msg.id

    elif data == "back_to_editnpc":
        await editnpc_command(event)

    elif data.startswith("unlink_account_"):
        telegram_id = int(data.split("_")[2])
        buttons = [
            [Button.inline("CONFIRM", data=f"confirm_unlink_{telegram_id}")],
            [Button.inline("Back", data=f"chat_groups_{telegram_id}")]
        ]
        msg = await event.respond(
            f"Are you sure you want to unlink the account with Telegram ID {telegram_id}? This action cannot be undone.",
            buttons=buttons
        )
        last_bot_message_id[user_id] = msg.id

    elif data.startswith("confirm_unlink_"):
        telegram_id = int(data.split("_")[2])
        await unlink_account(event, user_id, telegram_id)

    elif data.startswith("list_groups_"):
        telegram_id = int(data.split("_")[2])
        await list_chat_groups(event, telegram_id)

    elif data.startswith("add_group_"):
        telegram_id = int(data.split("_")[2])
        msg = await event.respond(
            "Enter Telegram Chat Group: include @ (Ex: @groupname) or just the Chat Group ID (Ex: 123456789)."
        )
        user_state[user_id] = f'adding_group_{telegram_id}'
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"Set state to 'adding_group_{telegram_id}' for user {user_id}")

    elif data.startswith("view_group_"):
        parts = data.split("_")
        telegram_id = int(parts[2])
        chat_group_id = int(parts[3])
        await view_group(event, telegram_id, chat_group_id)

    elif data.startswith("edit_personality_"):
        parts = data.split("_")
        telegram_id = int(parts[2])
        chat_group_id = int(parts[3])
        user_state[user_id] = f'editing_personality_{telegram_id}_{chat_group_id}'
        msg = await event.respond("Edit the personality for this chat group (limit 2000 characters).")
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"Set state to 'editing_personality_{telegram_id}_{chat_group_id}'")

    elif data.startswith("personality_helper_"):
        parts = data.split("_")
        telegram_id = int(parts[2])
        chat_group_id = int(parts[3])
        await handle_personality_helper(event, user_id, telegram_id, chat_group_id)

    elif data.startswith("set_personality_"):
        telegram_id, chat_group_id = map(int, data.split('_')[2:4])
        generated_personality = temp_user_data.get(user_id, {}).get('generated_personality', '')
        if generated_personality:
            await handle_add_personality(event, user_id, telegram_id, chat_group_id, generated_personality)
            await event.respond("Personality description has been set for the chat group.")
            temp_user_data[user_id].pop('generated_personality', None)
        else:
            await event.respond("No generated personality found. Please use the Personality Helper first.")
        await view_group(event, telegram_id, chat_group_id)

    elif data.startswith("delete_group_"):
        parts = data.split("_")
        telegram_id = int(parts[2])
        chat_group_id = int(parts[3])
        success = await delete_chat_group(event, telegram_id, chat_group_id)
        if success:
            await event.respond("Chat group deleted successfully.")
            await list_chat_groups(event, telegram_id)
        else:
            await event.respond("Failed to delete chat group.")
    else:
        await event.respond("Unknown action.")


async def unlink_account(event, user_id, telegram_id):
    global user_data, chat_groups
    user_data = load_user_data()
    chat_groups = load_chat_groups()

    if str(user_id) in user_data:
        linked_accounts = user_data[str(user_id)]['linked_accounts']
        user_data[str(user_id)]['linked_accounts'] = [
            acc for acc in linked_accounts if int(acc['telegram_id']) != int(telegram_id)
        ]
        save_user_data(user_data)

    if str(user_id) in chat_groups:
        chat_groups[str(user_id)]['linked_accounts'] = [
            acc for acc in chat_groups[str(user_id)]['linked_accounts'] if int(acc['telegram_id']) != int(telegram_id)
        ]
        save_chat_groups(chat_groups)

    client_key = (int(user_id), int(telegram_id))
    if client_key in linked_user_clients:
        client = linked_user_clients.pop(client_key)
        await client.disconnect()
    if client_key in client_tasks:
        client_tasks[client_key].cancel()
        del client_tasks[client_key]

    await event.respond(f"Account with Telegram ID {telegram_id} has been unlinked.")
    await editnpc_command(event)


@bot.on(events.NewMessage)
async def handle_input(event):
    user_id = event.sender_id
    if event.raw_text.startswith('/'):
        logging.debug(f"Ignoring command input from user {user_id}: {event.raw_text}")
        return

    if user_id not in user_state or user_id not in last_bot_message_id:
        logging.debug(f"No state is set for user {user_id}, ignoring message.")
        return

    if event.id <= last_bot_message_id[user_id]:
        logging.debug(f"Message {event.id} from user {user_id} was before bot's prompt.")
        return

    state = user_state[user_id]
    logging.debug(f"User {user_id} in state {state} sent message: {event.raw_text}")

    if state == 'awaiting_session_string':
        session_string = event.raw_text.strip()
        logging.debug(f"User {user_id} provided session string.")
        await create_session_with_string(user_id, session_string, event)
        user_state[user_id] = None

    elif state == 'awaiting_phone':
        if user_id not in temp_user_data:
            temp_user_data[user_id] = {}
        temp_user_data[user_id]['temp_phone'] = event.raw_text.strip()
        logging.debug(f"User {user_id} phone: {temp_user_data[user_id]['temp_phone']}")
        user_state[user_id] = 'awaiting_password'
        msg = await event.respond("Enter the password or 'none' if no password is set.")
        last_bot_message_id[user_id] = msg.id

    elif state == 'awaiting_password':
        if user_id not in temp_user_data:
            temp_user_data[user_id] = {}
        password = event.raw_text.strip()
        temp_user_data[user_id]['temp_password'] = password if password.lower() != "none" else ''
        logging.debug(f"User {user_id} provided password.")
        user_state[user_id] = 'confirming_info'
        password_display = "none" if temp_user_data[user_id]['temp_password'] == '' else temp_user_data[user_id]['temp_password']
        msg = await event.respond(
            f"Information provided:\nPhone: {temp_user_data[user_id]['temp_phone']}\nPassword: {password_display}\nIs this correct?",
            buttons=[Button.inline("Info Confirmed", b"confirm"), Button.inline("Start Over", b"start_over")]
        )
        last_bot_message_id[user_id] = msg.id

    elif state == 'awaiting_code':
        code = event.raw_text.strip()
        await handle_code_input(event, user_id, code)

    elif state == 'awaiting_password_for_sign_in':
        password = event.raw_text.strip()
        await handle_password_for_sign_in(event, user_id, password)

    elif state.startswith('adding_group_'):
        telegram_id = state.split('_')[2]
        chat_group_link = event.raw_text.strip()
        await handle_add_group(event, user_id, telegram_id, chat_group_link)

    elif state.startswith('adding_personality_'):
        telegram_id, chat_group_id = state.split('_')[2:4]
        personality_description = event.raw_text.strip()[:2000]
        await handle_add_personality(event, user_id, telegram_id, chat_group_id, personality_description)

    elif state.startswith('editing_personality_'):
        telegram_id, chat_group_id = state.split('_')[2:4]
        personality_description = event.raw_text.strip()[:2000]
        await handle_edit_personality(event, user_id, telegram_id, chat_group_id, personality_description)

    elif state.startswith('awaiting_personality_samples_'):
        telegram_id, chat_group_id = state.split('_')[3:5]
        samples_text = event.raw_text.strip()
        await process_personality_samples(event, user_id, telegram_id, chat_group_id, samples_text)

    else:
        logging.debug(f"No handler for state {state}")


async def create_session_with_string(user_id, session_string, event):
    try:
        logging.debug(f"Creating session with session string for user {user_id}")
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await event.respond("Invalid or unauthorized session string.")
            await client.disconnect()
            return

        result = await client.get_me()
        if result.id == user_id:
            await event.respond("You cannot link the same account you are using now. Use a different account.")
            await client.disconnect()
            return

        logging.debug(f"Authorized user {result.first_name} ({result.id}) with session string.")
        await save_user_data_info(user_id, result, session_string, client, event, is_session_string=True)

    except Exception as e:
        logging.error(f"Failed to create session with string for user {user_id}: {str(e)}")
        await event.respond(f"Failed: {str(e)}")
        # If client was created successfully, ensure it's disconnected
        try:
            await client.disconnect()
        except:
            pass


async def create_session(user_id, event):
    try:
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            phone = temp_user_data[user_id]['temp_phone']
            await client.send_code_request(phone)
            msg = await event.respond("Enter the 5-digit code sent to the account.")
            user_state[user_id] = 'awaiting_code'
            last_bot_message_id[user_id] = msg.id
            temp_user_data[user_id]['temp_client'] = client
        else:
            await event.respond("Already authorized.")
            await client.disconnect()
    except Exception as e:
        logging.error(f"Failed to create session for user {user_id}: {str(e)}")
        await event.respond(f"Failed: {str(e)}")


async def handle_code_input(event, user_id, code):
    client = temp_user_data[user_id]['temp_client']
    try:
        phone = temp_user_data[user_id]['temp_phone']
        password = temp_user_data[user_id].get('temp_password', '')
        if password:
            result = await client.sign_in(phone, code, password=password)
        else:
            result = await client.sign_in(phone, code)

        if result.id == user_id:
            await event.respond("You cannot link the same account used to interact with the bot. Use another account.")
            await client.disconnect()
            user_state[user_id] = None
            temp_user_data.pop(user_id, None)
            return

        session_string = client.session.save()
        await save_user_data_info(user_id, result, session_string, client, event, is_session_string=False)
        user_state[user_id] = None
        temp_user_data.pop(user_id, None)
    except errors.SessionPasswordNeededError:
        msg = await event.respond("Two-step verification. Re-enter password or 'none' if no password.")
        user_state[user_id] = 'awaiting_password_for_sign_in'
        last_bot_message_id[user_id] = msg.id
    except Exception as e:
        logging.error(f"Error during session creation for user {user_id}: {str(e)}")
        await event.respond(f"Error: {str(e)}")
        await client.disconnect()


async def handle_password_for_sign_in(event, user_id, password):
    client = temp_user_data[user_id]['temp_client']
    try:
        if password.lower() == "none":
            password = ''
        result = await client.sign_in(password=password)
        if result.id == user_id:
            await event.respond("Cannot link the same account. Use a different account.")
            await client.disconnect()
            user_state[user_id] = None
            temp_user_data.pop(user_id, None)
            return

        session_string = client.session.save()
        await save_user_data_info(user_id, result, session_string, client, event, is_session_string=False)
        user_state[user_id] = None
        temp_user_data.pop(user_id, None)
    except Exception as e:
        logging.error(f"Error during sign-in: {e}")
        await event.respond(f"Error: {e}")
        await client.disconnect()


async def save_user_data_info(user_id, result, session_string, client, event, is_session_string):
    linked_account_info = {
        'session_string': session_string,
        'first_name': result.first_name,
        'last_name': result.last_name,
        'username': result.username,
        'telegram_id': int(result.id),
    }

    if not is_session_string:
        linked_account_info['phone'] = temp_user_data[user_id]['temp_phone']

    user_data = load_user_data()
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {'linked_accounts': []}

    def update_linked_accounts(user_id):
        existing_accounts = user_data[str(user_id)]['linked_accounts']
        for i, account in enumerate(existing_accounts):
            if int(account['telegram_id']) == int(result.id):
                existing_accounts[i] = linked_account_info
                return True
        return False

    if not update_linked_accounts(user_id):
        user_data[str(user_id)]['linked_accounts'].append(linked_account_info)

    save_user_data(user_data)

    chat_groups_data = load_chat_groups()
    if str(user_id) in chat_groups_data:
        for account in chat_groups_data[str(user_id)]['linked_accounts']:
            if 'telegram_id' in account and int(account['telegram_id']) != int(result.id):
                account['telegram_id'] = int(result.id)
        save_chat_groups(chat_groups_data)

    await client.disconnect()
    await event.respond("Success. Your account is now linked.")
    user_state[user_id] = None

    await initialize_linked_user_clients()
    temp_user_data.pop(user_id, None)


async def list_chat_groups(event, telegram_id):
    user_id = event.sender_id
    chat_groups_data = load_chat_groups()

    current_groups = chat_groups_data.get(str(user_id), {}).get('linked_accounts', [])
    account_groups = next((account['chat_groups'] for account in current_groups if int(account['telegram_id']) == int(telegram_id)), [])
    if not account_groups:
        await event.respond("No chat groups are currently managed for this account.")
        return

    group_buttons = []
    for group in account_groups:
        group_name = group.get('chat_group_name', 'Unknown Group')
        group_buttons.append([Button.inline(group_name, data=f"view_group_{telegram_id}_{group['chat_group_id']}")])
    group_buttons.append([Button.inline("Back", data=f"chat_groups_{telegram_id}")])

    msg = await event.respond("Current Chat Groups:", buttons=group_buttons)
    last_bot_message_id[user_id] = msg.id


async def view_group(event, telegram_id, chat_group_id):
    user_id = event.sender_id
    group = None
    chat_groups_data = load_chat_groups()
    for account in chat_groups_data.get(str(user_id), {}).get('linked_accounts', []):
        if int(account['telegram_id']) == int(telegram_id):
            for grp in account.get('chat_groups', []):
                if int(grp['chat_group_id']) == int(chat_group_id):
                    group = grp
                    break
            if group:
                break

    if group:
        group_name = group.get('chat_group_name', 'Unknown Group')
        buttons = [
            [Button.inline("Edit Personality", data=f"edit_personality_{telegram_id}_{chat_group_id}")],
            [Button.inline("Personality Helper", data=f"personality_helper_{telegram_id}_{chat_group_id}")],
            [Button.inline("Delete This Chat Group", data=f"delete_group_{telegram_id}_{chat_group_id}")],
            [Button.inline("Back", data=f"list_groups_{telegram_id}")]
        ]
        msg = await event.respond(
            f"Chat Group: {group_name}\nPersonality: {group['personality']}",
            buttons=buttons
        )
        last_bot_message_id[user_id] = msg.id
    else:
        await event.respond("Chat group not found.")


async def delete_chat_group(event, telegram_id, chat_group_id):
    user_id = event.sender_id
    chat_groups_data = load_chat_groups()
    account = None
    for acc in chat_groups_data.get(str(user_id), {}).get('linked_accounts', []):
        if int(acc['telegram_id']) == int(telegram_id):
            account = acc
            break

    if account:
        account['chat_groups'] = [group for group in account['chat_groups'] if int(group['chat_group_id']) != int(chat_group_id)]
        save_chat_groups(chat_groups_data)
        logging.debug(f"Deleted chat group {chat_group_id} for account {telegram_id}")
        return True
    return False


async def handle_add_group(event, user_id, telegram_id, chat_group_link):
    try:
        telegram_id = int(telegram_id)
        client_key = (user_id, telegram_id)
        client = linked_user_clients.get(client_key)
        if not client:
            await event.respond("Linked account client not found.")
            return

        # Detect if user typed @groupname or numeric ID
        if chat_group_link.startswith('@'):
            chat_entity = await client.get_entity(chat_group_link)
            chat_group_id = chat_entity.id
            chat_group_name = chat_entity.title
        elif chat_group_link.isdigit():
            chat_group_id = int('-100' + chat_group_link)
            chat_entity = await client.get_entity(chat_group_id)
            chat_group_name = chat_entity.title
        elif chat_group_link.startswith('-100') and chat_group_link[4:].isdigit():
            chat_group_id = int(chat_group_link)
            chat_entity = await client.get_entity(chat_group_id)
            chat_group_name = chat_entity.title
        else:
            await event.respond("Invalid input. Provide @username or a numeric ID.")
            return

        logging.debug(f"Adding chat group {chat_group_id} '{chat_group_name}' for user {user_id}")

        chat_groups_data = load_chat_groups()
        if str(user_id) not in chat_groups_data:
            chat_groups_data[str(user_id)] = {'linked_accounts': []}
        account = next((a for a in chat_groups_data[str(user_id)]['linked_accounts']
                        if int(a['telegram_id']) == int(telegram_id)), None)
        if not account:
            account = {'telegram_id': int(telegram_id), 'chat_groups': []}
            chat_groups_data[str(user_id)]['linked_accounts'].append(account)

        is_member = await check_membership(user_id)
        max_chat_groups = 8 if is_member else 1
        if len(account['chat_groups']) >= max_chat_groups:
            await event.respond(f"You have reached the maximum of {max_chat_groups} chat groups for this linked account.")
            return

        account['chat_groups'].append({
            'chat_group_id': chat_group_id,
            'chat_group_name': chat_group_name,
            'personality': ''
        })
        save_chat_groups(chat_groups_data)

        msg = await event.respond("Saved Chat Group. Provide a personality description for this chat group.")
        user_state[user_id] = f'adding_personality_{telegram_id}_{chat_group_id}'
        last_bot_message_id[user_id] = msg.id
        logging.debug(f"State: 'adding_personality_{telegram_id}_{chat_group_id}' for user {user_id}")

        if client_key in linked_user_clients:
            client = linked_user_clients[client_key]
            if not hasattr(client, 'chat_group_ids'):
                client.chat_group_ids = []
            if chat_group_id not in client.chat_group_ids:
                client.chat_group_ids.append(chat_group_id)
            logging.debug(f"Updated chat groups for client {telegram_id}: {client.chat_group_ids}")

    except Exception as e:
        logging.error(f"Error adding group: {e}")
        await event.respond("Failed to add chat group. Check group link or ID.")


async def handle_add_personality(event, user_id, telegram_id, chat_group_id, personality_description):
    chat_groups_data = load_chat_groups()
    telegram_id = int(telegram_id)
    chat_group_id = int(chat_group_id)
    account = None
    for acc in chat_groups_data[str(user_id)]['linked_accounts']:
        if int(acc['telegram_id']) == telegram_id:
            account = acc
            break

    if account:
        for group in account['chat_groups']:
            if int(group['chat_group_id']) == chat_group_id:
                group['personality'] = personality_description
                save_chat_groups(chat_groups_data)
                break

    await event.respond("Personality description saved.")
    user_state[user_id] = None
    logging.debug(f"Cleared state for user {user_id}")


async def handle_edit_personality(event, user_id, telegram_id, chat_group_id, personality_description):
    chat_groups_data = load_chat_groups()
    telegram_id = int(telegram_id)
    chat_group_id = int(chat_group_id)
    account = None
    for acc in chat_groups_data[str(user_id)]['linked_accounts']:
        if int(acc['telegram_id']) == telegram_id:
            account = acc
            break

    if account:
        for group in account['chat_groups']:
            if int(group['chat_group_id']) == chat_group_id:
                group['personality'] = personality_description
                save_chat_groups(chat_groups_data)
                break

    await event.respond("Personality description updated.")
    user_state[user_id] = None
    logging.debug(f"Cleared state for user {user_id}")


async def handle_personality_helper(event, user_id, telegram_id, chat_group_id):
    user_state[user_id] = f'awaiting_personality_samples_{telegram_id}_{chat_group_id}'
    msg = await event.respond(
        "Personality Helper: Provide a post containing representative text. Max 1000 words. The bot will create a personality description from these samples."
    )
    last_bot_message_id[user_id] = msg.id
    logging.debug(f"Set state to 'awaiting_personality_samples_{telegram_id}_{chat_group_id}'")


async def process_personality_samples(event, user_id, telegram_id, chat_group_id, samples_text):
    """
    This function is now a placeholder that you can modify to call your custom LLM endpoint.
    For example, if your LLM runs at http://your-vps-ip:8000/generate, you can call it here
    with requests.post(...) or an async library. 
    """
    try:
        words = samples_text.split()
        if len(words) > 1000:
            samples_text = ' '.join(words[:1000])
            logging.debug(f"Samples truncated to 1000 words for user {user_id}")

        # Replace the entire OpenAI call with your custom LLM logic:
        # For example, using requests (synchronous example, adapt if needed):
        #
        # response = requests.post("http://your-vps-ip:8000/generate", json={"prompt": samples_text})
        # personality_description = response.json().get("generated_text", "")
        #
        # For now, let's just do a fake response:
        personality_description = (
            "You speak with a witty, sarcastic tone, often making dry observations and short quips."
        )

        personality_description = personality_description[:2000]

        await event.respond(
            f"Generated personality:\n\n{personality_description}"
        )

        buttons = [
            [Button.inline("Set as Personality", data=f"set_personality_{telegram_id}_{chat_group_id}")],
            [Button.inline("Back", data=f"view_group_{telegram_id}_{chat_group_id}")]
        ]
        msg = await event.respond("Set this as the personality?", buttons=buttons)
        last_bot_message_id[user_id] = msg.id

        temp_user_data[user_id] = temp_user_data.get(user_id, {})
        temp_user_data[user_id]['generated_personality'] = personality_description
        temp_user_data[user_id]['telegram_id'] = telegram_id
        temp_user_data[user_id]['chat_group_id'] = chat_group_id

        user_state[user_id] = None
        logging.debug(f"Generated personality for user {user_id}")

    except Exception as e:
        logging.error(f"Error generating personality: {e}")
        await event.respond("Failed to generate personality. Try again later.")
        user_state[user_id] = None


async def handle_linked_user_message(event, user_id):
    try:
        telegram_id = event.client.me.id
        message = event.message
        chat_id = event.chat_id
        current_time = time.time()

        logging.debug(f"Message in chat {chat_id} by user {message.sender_id}")

        sender = await message.get_sender()
        if sender:
            logging.debug(f"Message sender: {sender.first_name} {sender.last_name} (ID: {sender.id})")

        if sender and sender.id == telegram_id:
            logging.debug("Ignoring linked account's own message.")
            return

        if message.date < event.client.user_start_time:
            logging.debug("Message before client start; skipping.")
            return

        if contains_link(message.text):
            logging.debug("Message contains a link; skipping.")
            return

        if not message.text:
            logging.debug("No text; skipping.")
            return

        client_key = (user_id, telegram_id)
        chat_groups_data = load_chat_groups()
        user_chat_groups = chat_groups_data.get(str(user_id), {}).get('linked_accounts', [])
        linked_account = next((acc for acc in user_chat_groups if int(acc['telegram_id']) == telegram_id), None)
        if not linked_account:
            logging.debug("No linked account found.")
            return

        chat_group_ids = [int(cg['chat_group_id']) for cg in linked_account.get('chat_groups', [])]
        if chat_id not in chat_group_ids:
            logging.debug("Chat ID not assigned to this account.")
            return

        chat_group = next((cg for cg in linked_account.get('chat_groups', []) if int(cg['chat_group_id']) == chat_id), None)
        if not chat_group:
            logging.debug("No chat group data found.")
            return

        if client_key not in message_tracker:
            message_tracker[client_key] = {}
        if chat_id not in message_tracker[client_key]:
            message_tracker[client_key][chat_id] = []

        if client_key not in reply_tracker:
            reply_tracker[client_key] = {}
        if chat_id not in reply_tracker[client_key]:
            reply_tracker[client_key][chat_id] = set()

        # Clean out timestamps older than 7 hours
        message_tracker[client_key][chat_id] = [
            ts for ts in message_tracker[client_key][chat_id]
            if current_time - ts < 25200
        ]

        is_member = await check_membership(user_id)
        message_limit = 4 if is_member else 1
        if len(message_tracker[client_key][chat_id]) >= message_limit:
            logging.debug("Message limit reached; cooling off.")
            return

        if message.is_reply and message.reply_to_msg_id:
            original_message = await message.get_reply_message()
            if original_message and original_message.sender_id:
                if int(original_message.sender_id) != telegram_id:
                    logging.debug("Original message not from linked account.")
                    return
            else:
                logging.debug("No original message or sender_id.")
                return

            if sender and sender.bot:
                logging.debug("Replier is a bot; skipping.")
                return

            if message.id in reply_tracker[client_key][chat_id]:
                logging.debug("Already replied to this message.")
                return

            personality_description = chat_group['personality']
            delay = random.uniform(32, 2600)
            logging.debug(f"Waiting {delay} seconds before responding.")
            await asyncio.sleep(delay)

            response_text = await generate_llm_response(personality_description, message.text)

            try:
                if not event.client.is_connected():
                    await event.client.connect()

                await event.client.send_message(chat_id, response_text, reply_to=message.id)
                logging.info(f"Replied in chat {chat_id}")
            except errors.FloodWaitError as e:
                logging.warning(f"FloodWaitError: Waiting {e.seconds}s")
                await asyncio.sleep(e.seconds)
                await event.client.send_message(chat_id, response_text, reply_to=message.id)
            except Exception as e:
                logging.error(f"Error sending message: {e}")
                return

            message_tracker[client_key][chat_id].append(current_time)
            reply_tracker[client_key][chat_id].add(message.id)
        else:
            logging.debug("Not a reply to linked account's message; skipping.")

    except Exception as e:
        logging.error(f"Error handling linked user message: {e}")
        await asyncio.sleep(5)


def contains_link(text):
    url_pattern = re.compile(
        r'(?i)\b((?:https?://|www\.|telegram\.me/|t\.me/|bit\.ly/|goo\.gl/|tinyurl\.com|'
        r'\w+\.\w{2,}/\S*))'
    )
    return bool(url_pattern.search(text or ''))


async def generate_llm_response(personality_description, user_input):
    """
    Replace this placeholder with an actual request to your custom LLM running on another VPS.
    """
    try:
        # For example, if your LLM endpoint is an HTTP API:
        # response = requests.post("http://your-vps-ip:8000/generate", json={
        #     "personality": personality_description,
        #     "input_text": user_input
        # })
        # response_text = response.json()["response"]

        # For now, we'll just return a made-up, short response:
        fake_response = [
            "Sure, I'll keep that in mind.",
            "Absolutely, no problem!",
            "Alright, consider it done.",
            "Got it."
        ]
        response_text = random.choice(fake_response)

        # Optionally remove emojis, hashtags, or do further processing:
        response_text = remove_emojis_and_hashtags(response_text)

        # We no longer do any word-censorship or exclamation replacements
        # because you requested that function be removed.

        return response_text
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Sorry, I couldn't generate a response."


def remove_emojis_and_hashtags(text):
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  
        "\U0001F300-\U0001F5FF"  
        "\U0001F680-\U0001F6FF"  
        "\U0001F700-\U0001F77F"  
        "\U0001F780-\U0001F7FF"  
        "\U0001F800-\U0001F8FF"  
        "\U0001F900-\U0001F9FF"  
        "\U0001FA00-\U0001FA6F"  
        "\U0001FA70-\U0001FAFF"  
        "\U00002702-\U000027B0"  
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    text = re.sub(r'#\w+', '', text)
    return text


async def autopost_task(client):
    client_key = (client.user_id, client.telegram_id)
    while True:
        try:
            if not client.is_connected():
                await client.connect()

            is_member = await check_membership(client.user_id)
            if is_member:
                delay = random.uniform(21600, 61200)  # 6 to 17 hours
            else:
                delay = random.uniform(43200, 86400)  # 12 to 24 hours

            logging.debug(f"Waiting {delay} seconds before autoposting")
            await asyncio.sleep(delay)

            chat_groups_data = load_chat_groups()
            user_chat_groups = chat_groups_data.get(str(client.user_id), {}).get('linked_accounts', [])
            linked_account = next((acc for acc in user_chat_groups if int(acc['telegram_id']) == client.telegram_id), None)

            if not linked_account:
                logging.debug("No linked account found for autopost.")
                continue

            for chat_group in linked_account.get('chat_groups', []):
                chat_id = int(chat_group['chat_group_id'])
                personality_description = chat_group['personality']

                if client_key not in autoreply_tracker:
                    autoreply_tracker[client_key] = {}
                if chat_id not in autoreply_tracker[client_key]:
                    autoreply_tracker[client_key][chat_id] = set()

                now = datetime.datetime.now(datetime.timezone.utc)
                found_message = None
                async for message in client.iter_messages(chat_id, limit=100):
                    if (now - message.date).total_seconds() > 25200:
                        break
                    if message.sender_id == client.me.id:
                        continue
                    sender = await message.get_sender()
                    if sender and sender.bot:
                        continue
                    if contains_link(message.text):
                        continue
                    if not message.text:
                        continue
                    if message.id in autoreply_tracker[client_key][chat_id]:
                        continue
                    found_message = message
                    break

                if not found_message:
                    logging.debug(f"No suitable message in chat {chat_id} for autopost.")
                    continue

                last_message = found_message
                response_text = await generate_llm_response(personality_description, last_message.text or "")

                try:
                    if not client.is_connected():
                        await client.connect()
                    await client.send_message(chat_id, response_text, reply_to=last_message.id)
                    logging.info(f"Autoposted reply in chat {chat_id}")
                    autoreply_tracker[client_key][chat_id].add(last_message.id)

                except errors.FloodWaitError as e:
                    logging.warning(f"FloodWaitError: Waiting {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                    await client.send_message(chat_id, response_text, reply_to=last_message.id)
                    logging.info(f"Autoposted reply after wait in chat {chat_id}")
                    autoreply_tracker[client_key][chat_id].add(last_message.id)
                except Exception as e:
                    logging.error(f"Error autoposting message: {e}")
                    continue

        except Exception as e:
            logging.error(f"Error in autopost_task: {e}")
            await asyncio.sleep(3600)


async def check_for_updates():
    global user_data, chat_groups, linked_user_clients
    while True:
        try:
            new_user_data = load_user_data()
            if new_user_data != user_data:
                logging.info("Change in user_data.json detected.")
                user_data = new_user_data
                await initialize_linked_user_clients()

            new_chat_groups = load_chat_groups()
            if new_chat_groups != chat_groups:
                logging.info("Change in chat_groups.json detected.")
                chat_groups = new_chat_groups
                for client_key, client in linked_user_clients.items():
                    user_id, telegram_id = client_key
                    user_chat_groups = chat_groups.get(str(user_id), {}).get('linked_accounts', [])
                    linked_account = next((acc for acc in user_chat_groups if int(acc['telegram_id']) == telegram_id), None)
                    if linked_account:
                        client.chat_group_ids = [int(group['chat_group_id']) for group in linked_account.get('chat_groups', [])]
                    else:
                        client.chat_group_ids = []
                    logging.debug(f"Updated chat groups for client {telegram_id}: {client.chat_group_ids}")

        except Exception as e:
            logging.error(f"Error checking updates: {e}")

        await asyncio.sleep(60)


async def initialize_linked_user_clients():
    global linked_user_clients, client_tasks
    existing_client_keys = set(linked_user_clients.keys())
    new_client_keys = set()
    current_user_data = load_user_data()
    for user_id, data in current_user_data.items():
        for account in data.get('linked_accounts', []):
            session_string = account.get('session_string')
            if not session_string:
                continue
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            client.user_id = int(user_id)
            client.session_string = session_string
            await client.connect()
            if not await client.is_user_authorized():
                logging.warning(f"Client for {account.get('telegram_id')} not authorized.")
                continue
            client.user_start_time = datetime.datetime.now(datetime.timezone.utc)
            client.me = await client.get_me()
            client.telegram_id = client.me.id

            if int(account.get('telegram_id', 0)) != client.telegram_id:
                account['telegram_id'] = client.telegram_id
                save_user_data(current_user_data)
                logging.info(f"Updated telegram_id for user {user_id}")

            client_key = (client.user_id, client.telegram_id)
            new_client_keys.add(client_key)
            linked_user_clients[client_key] = client

            chat_groups_data = load_chat_groups()
            user_chat_groups = chat_groups_data.get(str(client.user_id), {}).get('linked_accounts', [])
            linked_account = next((acc for acc in user_chat_groups if int(acc['telegram_id']) == client.telegram_id), None)
            if linked_account:
                client.chat_group_ids = [int(group['chat_group_id']) for group in linked_account.get('chat_groups', [])]
            else:
                client.chat_group_ids = []

            @client.on(events.NewMessage(incoming=True, outgoing=False))
            async def client_event_handler(evt, client=client):
                if evt.chat_id in client.chat_group_ids:
                    await handle_linked_user_message(evt, client.user_id)

            asyncio.create_task(autopost_task(client))
            client_task = asyncio.create_task(client.run_until_disconnected())
            client_tasks[client_key] = client_task

    for client_key in existing_client_keys - new_client_keys:
        client = linked_user_clients[client_key]
        await client.disconnect()
        del linked_user_clients[client_key]
        if client_key in client_tasks:
            client_tasks[client_key].cancel()
            del client_tasks[client_key]
        logging.debug(f"Removed client {client_key}")


async def initialize_bot_tasks():
    await bot.start(bot_token=BOT_TOKEN)
    await initialize_linked_user_clients()


async def main():
    await initialize_bot_tasks()
    tasks = [
        asyncio.create_task(check_for_updates()),
    ]
    tasks.append(asyncio.create_task(bot.run_until_disconnected()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        logging.info("Starting the bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped manually.")
    except Exception as e:
        logging.error(f"Error occurred: {e}")
    finally:
        logging.info("Bot is shutting down.")
