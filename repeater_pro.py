# standard library imports for core functionality
import re
import time
import traceback
import os
import uuid
import random

# Base classes from the plugin environment
from base_plugin import BasePlugin, HookResult, HookStrategy

# Utility to run code on the main Android UI thread
from android_utils import log, run_on_ui_thread

# Imports from the client environment for interacting with Telegram
from client_utils import send_request, RequestCallback, get_messages_controller, send_message
from ui.alert import AlertDialogBuilder
from client_utils import get_last_fragment

# Android-specific imports for threading and Java integration
from android.os import Handler, Looper
from java.lang import Runnable, Integer
from java.chaquopy import dynamic_proxy
from org.telegram.tgnet import TLRPC
from java.util import ArrayList

# UI components for building the settings page
from ui.settings import Header, Text, Input, Divider

# Utility for parsing Markdown in text
from markdown_utils import parse_markdown

# Android-specific imports for copy-to-clipboard functionality
from android.content import ClipData, ClipboardManager, Context
from android.widget import Toast


# --- Plugin Metadata ---
# This section defines the plugin's identity and properties for the plugin manager.
__id__ = "message_repeater_pro"
__name__ = "Message Repeater"
__description__ = "Automate sending repetitive messages, create fun text effects, or test your bot's flood limits. Supports text, media, and Markdown."
__author__ = "@T3SL4"
__min_version__ = "11.9.1"
__version__ = "4.2.0"
__icon__ = "ogomk_highlights/3"

# --- Default Settings ---
# A dictionary holding the default values for all plugin settings.
# These are used if a setting is not configured or an invalid value is entered.
DEFAULT_SETTINGS = {
    # Behavior settings
    "confirmation_threshold": 100,  # Prompt for confirmation if spam count exceeds this
    "max_spam_limit": 500,         # Hard limit on the number of messages that can be spammed

    # Delay settings in seconds
    "default_media_delay_sec": 0.2,   # Default delay for media spam if not specified
    "default_deletion_delay_sec": 2.5, # Default delay for auto-deleting messages in .spamdel

    # Command names
    "cmd_spam": ".spam",
    "cmd_spamdel": ".spamdel",
    "cmd_stop": ".spamstop",
    "cmd_spamdebuglog": ".spamdebuglog",

    # File system settings
    "logs_directory": "/storage/emulated/0/Download/spammer_logs",
}

# --- HELPER CLASSES ---
class DebugLogger:
    """A static class for handling in-memory logging and saving logs to a file."""
    logs = []  # A list to hold log entries in memory

    @staticmethod
    def make_log(log_message: str):
        """Creates a timestamped log entry and adds it to the in-memory list."""
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}"
        print(f"SPAMMER_LOG: {log_message}")
        DebugLogger.logs.append(log_entry)

    @staticmethod
    def save_logs(log_dir: str) -> str:
        """Saves all in-memory logs to a file in the specified directory."""
        if not DebugLogger.logs:
            return "No logs to save."
        # Generate a unique filename for the log
        file_name = f"log-{uuid.uuid4()}.txt"
        save_path = os.path.join(log_dir, file_name)
        try:
            # Create the directory if it doesn't exist
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            # Write logs to the file and clear the in-memory list
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(DebugLogger.logs))
            DebugLogger.logs = []
            return f"Logs saved to: {save_path}"
        except Exception as e:
            final_error = f"Failed to save logs: {e}\n\n{traceback.format_exc()}"
            print(final_error)
            return final_error

class SpamTask(dynamic_proxy(Runnable)):
    """
    A proxy class that wraps a Python callable into a Java Runnable.
    This is necessary for scheduling tasks on the Android main thread using a Handler.
    """
    def __init__(self, runnable):
        super().__init__()
        self.runnable = runnable

    def run(self):
        """This method is called by the Android Handler when the task executes."""
        self.runnable()

# --- MAIN PLUGIN CLASS ---
class SpammerPlugin(BasePlugin):
    """
    The main class for the Spammer plugin. It handles settings, hooks,
    and the core logic for spamming messages.
    """

    # Wallet addresses for the "Support the Developer" section
    TON_ADDRESS = "UQDx2lC9bQW3A4LAfP4lSqtSftQSnLczt87Kn_CIcmJhLicm"
    USDT_ADDRESS = "TXLJNebRRAhwBRKtELMHJPNMtTZYHeoYBo"

    def on_plugin_load(self):
        """Called when the plugin is loaded by the application."""
        # A handler to schedule tasks on Android's main UI thread
        self.main_thread_handler = Handler(Looper.getMainLooper())
        # State variables to manage the spamming process
        self.spam_active = False
        self.messages_sent_count = 0
        self.scheduled_task = None
        self.last_command_data = None  # To remember the last spam command for repetition
        # Register the message hook to intercept outgoing messages
        self.add_on_send_message_hook()

    def on_plugin_unload(self):
        """Called when the plugin is unloaded."""
        # Ensure any running spam task is stopped
        self.spam_active = False
        if self.scheduled_task:
            self.main_thread_handler.removeCallbacks(self.scheduled_task)

    def _cleanup_task(self):
        """Resets the state of the spam task."""
        self.spam_active = False
        self.scheduled_task = None

    def _copy_to_clipboard(self, text_to_copy: str, label: str):
        """Copies the given text to the device's clipboard."""
        activity = get_last_fragment().getParentActivity()
        if not activity:
            return
        try:
            clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
            clip = ClipData.newPlainText(label, text_to_copy)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(activity, f"{label} address copied to clipboard!", Toast.LENGTH_SHORT).show()
        except Exception as e:
            error_message = f"Failed to copy to clipboard: {traceback.format_exc()}"
            DebugLogger.make_log(error_message)
            Toast.makeText(activity, "Failed to copy address.", Toast.LENGTH_SHORT).show()

    def create_settings(self) -> list:
        """Creates the list of UI components for the plugin's settings page."""
        return [
            Header(text="Behavior Settings"),
            Input(key="confirmation_threshold", text="Confirmation Threshold", default=str(DEFAULT_SETTINGS["confirmation_threshold"]), subtext="Show confirmation if spam count exceeds this value."),
            Input(key="max_spam_limit", text="Max Spam Limit", default=str(DEFAULT_SETTINGS["max_spam_limit"]), subtext="Maximum allowed spam count."),
            Divider(),
            Header(text="Default Delays (in seconds)"),
            Input(key="default_media_delay_sec", text="Media Spam Delay", default=str(DEFAULT_SETTINGS["default_media_delay_sec"]), subtext="Default delay for media if not specified in the command."),
            Input(key="default_deletion_delay_sec", text="Auto-Deletion Delay", default=str(DEFAULT_SETTINGS["default_deletion_delay_sec"]), subtext=f"Default deletion delay for your spam-delete command."),
            Divider(),
            Header(text="Command Settings"),
            Input(key="cmd_spam", text="Spam Command", default=DEFAULT_SETTINGS["cmd_spam"]),
            Input(key="cmd_spamdel", text="Spam-Delete Command", default=DEFAULT_SETTINGS["cmd_spamdel"]),
            Input(key="cmd_stop", text="Stop Command", default=DEFAULT_SETTINGS["cmd_stop"]),
            Input(key="cmd_spamdebuglog", text="Debug Log Command", default=DEFAULT_SETTINGS["cmd_spamdebuglog"]),
            Divider(),
            Input(key="logs_directory", text="Logs Directory", default=DEFAULT_SETTINGS["logs_directory"], subtext="Directory to save debug logs."),
            Divider(),
            Text(text="How to Use (FAQ)", icon="msg_info", on_click=self._show_faq_dialog),
            Divider(),
            Header(text="Support the Developer"),
            Text(text="TON", icon="msg_ton", accent=True, on_click=lambda view: run_on_ui_thread(lambda: self._copy_to_clipboard(self.TON_ADDRESS, "TON"))),
            Text(text="USDT (TRC20)", icon="msg_copy", accent=True, on_click=lambda view: run_on_ui_thread(lambda: self._copy_to_clipboard(self.USDT_ADDRESS, "USDT"))),
        ]

    def _show_faq_dialog(self, view):
        """Displays the FAQ/Help dialog."""
        def show_dialog_action():
            activity = get_last_fragment().getParentActivity()
            if not activity:
                return
            faq_text = self._get_faq_text()
            # Parse the Markdown text for proper display in the dialog
            parsed_faq = parse_markdown(faq_text)
            builder = AlertDialogBuilder(activity)
            builder.set_title("Spammer Pro - FAQ")
            builder.set_message(parsed_faq.text if parsed_faq else faq_text)
            builder.set_positive_button("Close", lambda b, w: b.dismiss())
            builder.show()
        # Ensure the dialog is shown on the main UI thread
        run_on_ui_thread(show_dialog_action)

    def _get_faq_text(self) -> str:
        """Constructs the FAQ text using the currently configured command names."""
        cmd_spam = self.get_setting("cmd_spam", DEFAULT_SETTINGS["cmd_spam"])
        cmd_spamdel = self.get_setting("cmd_spamdel", DEFAULT_SETTINGS["cmd_spamdel"])
        cmd_stop = self.get_setting("cmd_stop", DEFAULT_SETTINGS["cmd_stop"])
        cmd_spamdebuglog = self.get_setting("cmd_spamdebuglog", DEFAULT_SETTINGS["cmd_spamdebuglog"])

        return f"""
**🔐 ⚠️ DISCLAIMER – READ BEFORE USING ⚠️**
This plugin is provided strictly for educational, testing, and personal automation purposes only. It is not intended for spamming or violating [Telegram’s Terms of Service](https://telegram.org/tos).

The author does not encourage or support any form of abuse, unsolicited messaging, or unauthorized activity on Telegram or any other platform.
  - Misuse of this plugin to violate Telegram's spam policies (e.g. sending repetitive or unsolicited content to users/groups) can result in account limitations or permanent bans. You are solely responsible for how you use this tool.
  - By using this plugin, you agree to use it responsibly, ethically, and entirely at your own risk. The author assumes no liability for any actions taken with or consequences arising from its use.

**Frequently Asked Questions**

Welcome to the official guide for the Spammer Pro plugin!

**✅ GENERAL COMMANDS**

`{cmd_spam}` or `{cmd_spamdel}`
Sends messages multiple times. **Use alone to repeat the last command.**

`{cmd_stop}`
Immediately stops any spam task that is currently running.

`{cmd_spamdebuglog}`
Saves a detailed log file for troubleshooting.

**✍️ TEXT SPAM**

**How do I spam text?**
Use the format: `{cmd_spam} [text] [count]`
**Example:** `{cmd_spam} Hello World [50]`

**How do I add a delay?**
Add the delay in seconds in a third bracket.
**Example:** `{cmd_spam} Beep [10] [1.5]`

**How do I use formatting?**
The plugin supports **bold**, __italic__, `code`, and [links](https://google.com).

**🖼️ MEDIA SPAM (PHOTOS, STICKERS, FILES)**

**How do I spam media?**
Reply to any photo, sticker, video, or file with the command: `{cmd_spam} [count] [delay]`. The delay is optional.

**🗑️ DELETING SPAM ({cmd_spamdel})**

**How does it work?**
`{cmd_spamdel}` works just like `{cmd_spam}` but deletes each message after it's sent. It's great for "flash" effects.
**Example:** `{cmd_spamdel} Boo! [10]`
"""

    def start_spam_media_task(self, chat_id, remaining_count, input_media, delay_ms):
        """Handles the recursive logic for spamming media."""
        try:
            # Stop condition: task cancelled or all messages sent
            if not self.spam_active or remaining_count <= 0:
                return self._cleanup_task()
            # Prepare and send one media message
            req = TLRPC.TL_messages_sendMedia()
            req.peer = get_messages_controller().getInputPeer(chat_id)
            req.random_id = random.getrandbits(63)
            req.media = input_media
            send_request(req, RequestCallback(lambda r, e: None))
            self.messages_sent_count += 1
            # If more messages are left, schedule the next one
            if remaining_count > 1:
                next_runnable = SpamTask(lambda: self.start_spam_media_task(chat_id, remaining_count - 1, input_media, delay_ms))
                self.scheduled_task = next_runnable
                self.main_thread_handler.postDelayed(self.scheduled_task, delay_ms)
            else:
                self._cleanup_task()
        except Exception:
            DebugLogger.make_log(f"ERROR in media spam: {traceback.format_exc()}")
            self._cleanup_task()

    def start_spamdel_media_task(self, chat_id, remaining_count, input_media, deletion_ms, delay_ms):
        """Handles the recursive logic for spamming and then deleting media."""
        try:
            if not self.spam_active or remaining_count <= 0:
                return self._cleanup_task()
            
            # Define a callback to handle the response after a message is sent
            def handle_media_sent(response, error):
                try:
                    if error:
                        raise Exception(f"TLRPC Error: {error.text}")
                    self.messages_sent_count += 1
                    message_id = self.extract_message_id(response)
                    if not message_id:
                        raise Exception("Could not get message ID to delete.")
                    # Schedule the deletion of the sent message
                    self.main_thread_handler.postDelayed(SpamTask(lambda mid=message_id: self._delete_single_message(chat_id, mid)), deletion_ms)
                    # Schedule the next message if the task is still active
                    if self.spam_active and remaining_count > 1:
                        next_runnable = SpamTask(lambda: self.start_spamdel_media_task(chat_id, remaining_count - 1, input_media, deletion_ms, delay_ms))
                        self.scheduled_task = next_runnable
                        self.main_thread_handler.postDelayed(self.scheduled_task, delay_ms)
                    else:
                        self._cleanup_task()
                except Exception:
                    DebugLogger.make_log(f"ERROR in spamdel media callback: {traceback.format_exc()}")
                    self._cleanup_task()
            
            # Prepare and send one media message, with the callback attached
            req = TLRPC.TL_messages_sendMedia()
            req.peer = get_messages_controller().getInputPeer(chat_id)
            req.random_id = random.getrandbits(63)
            req.media = input_media
            send_request(req, RequestCallback(handle_media_sent))
        except Exception:
            DebugLogger.make_log(f"ERROR in spamdel media: {traceback.format_exc()}")
            self._cleanup_task()

    def start_spam_task(self, chat_id, text_to_spam, remaining_count, delay_ms, reply_to_msg_id, entities):
        """Handles the recursive logic for spamming text messages."""
        try:
            if not self.spam_active or remaining_count <= 0:
                return self._cleanup_task()
            # Prepare and send one text message
            req = TLRPC.TL_messages_sendMessage()
            req.peer = get_messages_controller().getInputPeer(chat_id)
            req.message = text_to_spam
            req.random_id = random.getrandbits(63)
            # Handle replies
            if reply_to_msg_id:
                req.reply_to = TLRPC.TL_inputReplyToMessage()
                req.reply_to.reply_to_msg_id = reply_to_msg_id
                req.flags |= 1
            # Handle Markdown/formatting entities
            if entities and not entities.isEmpty():
                req.entities = entities
                req.flags |= 8
            send_request(req, RequestCallback(lambda r, e: None))
            self.messages_sent_count += 1
            # Schedule the next message
            if remaining_count > 1:
                next_runnable = SpamTask(lambda: self.start_spam_task(chat_id, text_to_spam, remaining_count - 1, delay_ms, reply_to_msg_id, entities))
                self.scheduled_task = next_runnable
                self.main_thread_handler.postDelayed(self.scheduled_task, delay_ms)
            else:
                self._cleanup_task()
        except Exception:
            DebugLogger.make_log(f"ERROR in text spam: {traceback.format_exc()}")
            self._cleanup_task()

    def start_spamdel_task(self, chat_id, text_to_spam, remaining_count, reply_to_msg_id, deletion_ms, delay_ms, entities):
        """Handles the recursive logic for spamming and then deleting text messages."""
        try:
            if not self.spam_active or remaining_count <= 0:
                return self._cleanup_task()
            
            def handle_message_sent(response, error):
                try:
                    if error:
                        raise Exception(f"TLRPC Error: {error.text}")
                    self.messages_sent_count += 1
                    message_id = self.extract_message_id(response)
                    if not message_id:
                        raise Exception("Could not get message ID to delete.")
                    # Schedule deletion
                    self.main_thread_handler.postDelayed(SpamTask(lambda mid=message_id: self._delete_single_message(chat_id, mid)), deletion_ms)
                    # Schedule next send
                    if self.spam_active and remaining_count > 1:
                        next_runnable = SpamTask(lambda: self.start_spamdel_task(chat_id, text_to_spam, remaining_count - 1, reply_to_msg_id, deletion_ms, delay_ms, entities))
                        self.scheduled_task = next_runnable
                        self.main_thread_handler.postDelayed(self.scheduled_task, delay_ms)
                    else:
                        self._cleanup_task()
                except Exception:
                    DebugLogger.make_log(f"ERROR in spamdel callback: {traceback.format_exc()}")
                    self._cleanup_task()

            req = TLRPC.TL_messages_sendMessage()
            req.peer = get_messages_controller().getInputPeer(chat_id)
            req.message = text_to_spam
            req.random_id = random.getrandbits(63)
            if reply_to_msg_id:
                req.reply_to = TLRPC.TL_inputReplyToMessage()
                req.reply_to.reply_to_msg_id = reply_to_msg_id
                req.flags |= 1
            if entities and not entities.isEmpty():
                req.entities = entities
                req.flags |= 8
            send_request(req, RequestCallback(handle_message_sent))
        except Exception:
            DebugLogger.make_log(f"ERROR in spamdel: {traceback.format_exc()}")
            self._cleanup_task()

    def on_send_message_hook(self, account: int, params) -> HookResult:
        """
        The core function of the plugin. It intercepts every outgoing message
        to check if it's a spam command.
        """
        try:
            # --- Initial Checks ---
            # Ignore non-text messages or messages without content
            if not hasattr(params, "message") or not isinstance(params.message, str):
                return HookResult()
            message_text = params.message.strip()

            # --- Get current command names from settings ---
            cmd_stop = self.get_setting("cmd_stop", DEFAULT_SETTINGS["cmd_stop"])
            cmd_spamdebuglog = self.get_setting("cmd_spamdebuglog", DEFAULT_SETTINGS["cmd_spamdebuglog"])
            cmd_spam = self.get_setting("cmd_spam", DEFAULT_SETTINGS["cmd_spam"])
            cmd_spamdel = self.get_setting("cmd_spamdel", DEFAULT_SETTINGS["cmd_spamdel"])

            # --- Handle .spamstop command ---
            if message_text.lower() == cmd_stop:
                if self.spam_active:
                    self.spam_active = False
                    self._cleanup_task()
                    activity = get_last_fragment().getParentActivity()
                    if activity:
                        self.show_stopped_dialog(activity, self.messages_sent_count)
                return HookResult(strategy=HookStrategy.CANCEL)  # Cancel sending ".spamstop"
            
            # --- Handle .spamdebuglog command ---
            if message_text.lower() == cmd_spamdebuglog:
                log_dir = self.get_setting("logs_directory", DEFAULT_SETTINGS["logs_directory"])
                # Modify the message content to be the log file path
                params.message = DebugLogger.save_logs(log_dir)
                return HookResult(strategy=HookStrategy.MODIFY, params=params)

            # --- Prevent new spam commands while another is active ---
            if self.spam_active:
                if message_text.lower().startswith((cmd_spam, cmd_spamdel)):
                    # Silently cancel the new command if one is already running
                    return HookResult(strategy=HookStrategy.CANCEL)
                return HookResult()  # Let other messages pass through

            activity = get_last_fragment().getParentActivity()
            if not activity:
                return HookResult(strategy=HookStrategy.CANCEL)

            # --- Parse the command type ---
            is_delete_mode = False
            command_args = None
            is_repeat_command = False

            if message_text.lower().startswith(f"{cmd_spamdel} "):
                is_delete_mode = True
                command_args = message_text[len(cmd_spamdel)+1:].strip()
            elif message_text.lower().startswith(f"{cmd_spam} "):
                command_args = message_text[len(cmd_spam)+1:].strip()
            elif message_text.lower() == cmd_spamdel:
                is_delete_mode = True
                is_repeat_command = True
            elif message_text.lower() == cmd_spam:
                is_repeat_command = True
            else:
                return HookResult()  # Not a spam command, let it pass

            # --- Handle repeating the last command ---
            if is_repeat_command:
                if self.last_command_data:
                    # Load parameters from the previously stored command
                    command_args = self.last_command_data["args"]
                    reply_to_msg_object = self.last_command_data["reply"]
                    original_entities = self.last_command_data["entities"]
                else:
                    self.show_info_dialog(activity, "No Previous Command", "There is no command to repeat. Please see the FAQ for usage.")
                    return HookResult(strategy=HookStrategy.CANCEL)
            else:
                # Store parameters for a potential future repeat command
                reply_to_msg_object = params.replyToMsg if hasattr(params, 'replyToMsg') else None
                original_entities = params.entities if hasattr(params, 'entities') else None
                self.last_command_data = {"args": command_args, "reply": reply_to_msg_object, "entities": original_entities}

            reply_to_msg_id = reply_to_msg_object.messageOwner.id if reply_to_msg_object and hasattr(reply_to_msg_object, 'messageOwner') else None
            # Parse the command arguments into text, count, and delay
            text_to_spam, count, delay = self.parse_command(command_args)
            
            if count <= 0:
                 return HookResult(strategy=HookStrategy.CANCEL)

            # --- Logic for Media Spam (when replying to media) ---
            if text_to_spam is None:
                input_media = self.get_input_media_from_message(reply_to_msg_object)
                if input_media and count > 0:
                    # Check for expired photo data which can cause crashes
                    if isinstance(input_media, TLRPC.TL_inputMediaPhoto) and (not input_media.id.file_reference or len(input_media.id.file_reference) == 0):
                        self.show_info_dialog(activity, "Spammer Error", "Cannot forward this photo, data expired.")
                        return HookResult(strategy=HookStrategy.CANCEL)
                    
                    def start_media_action():
                        """The function that actually starts the media spam task."""
                        self.spam_active = True
                        self.messages_sent_count = 0
                        try:
                            media_delay_sec = float(self.get_setting('default_media_delay_sec', DEFAULT_SETTINGS["default_media_delay_sec"]))
                            del_delay_sec = float(self.get_setting('default_deletion_delay_sec', DEFAULT_SETTINGS["default_deletion_delay_sec"]))
                        except (ValueError, TypeError):
                            media_delay_sec = DEFAULT_SETTINGS["default_media_delay_sec"]
                            del_delay_sec = DEFAULT_SETTINGS["default_deletion_delay_sec"]
                        delay_ms = int(delay * 1000) if delay > 0 else int(media_delay_sec * 1000)
                        deletion_ms = int(del_delay_sec * 1000)
                        if is_delete_mode:
                            self.start_spamdel_media_task(params.peer, count, input_media, deletion_ms, delay_ms)
                        else:
                            self.start_spam_media_task(params.peer, count, input_media, delay_ms)

                    # Show confirmation for high spam counts
                    try:
                        confirmation_threshold = int(float(self.get_setting("confirmation_threshold", DEFAULT_SETTINGS["confirmation_threshold"])))
                    except (ValueError, TypeError):
                        confirmation_threshold = DEFAULT_SETTINGS["confirmation_threshold"]
                    if count > confirmation_threshold:
                        self.show_confirmation_dialog(activity, count, start_media_action)
                    else:
                        start_media_action()
                return HookResult(strategy=HookStrategy.CANCEL)

            # --- Logic for Text Spam ---
            # Calculate the offset to correctly adjust Markdown entity positions
            command_len_with_space = len(message_text) - len(command_args) if not is_repeat_command else 0
            final_entities = ArrayList()
            if original_entities:
                # Loop through existing entities and shift their offsets
                for i in range(original_entities.size()):
                    entity = original_entities.get(i)
                    if is_repeat_command or entity.offset >= command_len_with_space:
                        new_entity = type(entity)()
                        new_entity.offset = entity.offset - command_len_with_space if not is_repeat_command else entity.offset
                        new_entity.length = entity.length
                        if hasattr(entity, 'url'):
                            new_entity.url = entity.url
                        final_entities.add(new_entity)

            def start_text_action():
                """The function that actually starts the text spam task."""
                self.spam_active = True
                self.messages_sent_count = 0
                delay_ms = int(delay * 1000)
                try:
                    del_delay_sec = float(self.get_setting('default_deletion_delay_sec', DEFAULT_SETTINGS["default_deletion_delay_sec"]))
                except (ValueError, TypeError):
                    del_delay_sec = DEFAULT_SETTINGS["default_deletion_delay_sec"]
                deletion_ms = int((delay if delay > 0 else del_delay_sec) * 1000)
                if is_delete_mode:
                    self.start_spamdel_task(params.peer, text_to_spam, count, reply_to_msg_id, deletion_ms, delay_ms, final_entities)
                else:
                    self.start_spam_task(params.peer, text_to_spam, count, delay_ms, reply_to_msg_id, final_entities)

            # Show confirmation for high spam counts
            try:
                confirmation_threshold = int(float(self.get_setting("confirmation_threshold", DEFAULT_SETTINGS["confirmation_threshold"])))
            except (ValueError, TypeError):
                confirmation_threshold = DEFAULT_SETTINGS["confirmation_threshold"]
            if count > confirmation_threshold:
                self.show_confirmation_dialog(activity, count, start_text_action)
            else:
                start_text_action()
            
            # CRITICAL: Cancel the original message (e.g., ".spam hello 5") from being sent.
            return HookResult(strategy=HookStrategy.CANCEL)

        except Exception as e:
            # --- Failsafe Error Handling ---
            tb_string = traceback.format_exc()
            DebugLogger.make_log(f"FATAL ERROR in hook: {tb_string}")
            self._cleanup_task()
            activity_for_error = get_last_fragment().getParentActivity()
            if activity_for_error and 'params' in locals():
                self.show_error_dialog(activity_for_error, "Plugin Error", tb_string, params.peer)
            return HookResult(strategy=HookStrategy.CANCEL)

    def parse_command(self, command_args: str) -> (str, int, float):
        """
        Parses the command arguments to extract text, count, and delay.
        Supports two formats:
        1. [text] [count] [delay] (delay is optional) - handled by regex
        2. [text] [count] - handled by string splitting
        """
        text_to_spam, count, delay = None, 0, 0.0
        # Regex for format: `some text [count]` or `some text [count] [delay]`
        match = re.search(r'^(.*?)?[\s\u2063]*\[(\d+)\](?:[\s\u2063]*\[([0-9.]+)\])?$', command_args.strip())
        if match:
            text_content = match.group(1)
            text_to_spam = text_content.strip() if text_content else None
            count = int(match.group(2))
            if match.group(3):
                delay = float(match.group(3))
        else:
            # Fallback for format: `some text count`
            parts = command_args.rsplit(' ', 1)
            if len(parts) == 2 and parts[1].isdigit():
                text_to_spam = parts[0].strip()
                count = int(parts[1])
            # For media spam: `count`
            elif len(parts) == 1 and parts[0].isdigit():
                text_to_spam = None
                count = int(parts[0])
        
        if text_to_spam == "":
            text_to_spam = None
        
        # Enforce the maximum spam limit from settings
        try:
            max_limit = int(float(self.get_setting("max_spam_limit", DEFAULT_SETTINGS["max_spam_limit"])))
        except (ValueError, TypeError):
            max_limit = DEFAULT_SETTINGS["max_spam_limit"]
        return text_to_spam, min(count, max_limit), delay
    
    def show_confirmation_dialog(self, activity, count, on_confirm_action):
        """Displays a confirmation dialog for high spam counts."""
        def show_dialog():
            def on_confirm(bld, w):
                on_confirm_action()
                bld.dismiss()
            builder = AlertDialogBuilder(activity)
            builder.set_title("⚠️ High Spam Count")
            builder.set_message(f"You are about to send {count} items.\n\nAre you sure?")
            builder.set_positive_button("Proceed", on_confirm)
            builder.set_negative_button("Cancel", lambda b, w: b.dismiss())
            builder.show()
        run_on_ui_thread(show_dialog)
        
    def show_info_dialog(self, activity, title, message):
        """Displays a simple informational dialog."""
        def show_dialog():
            if not activity: return
            try:
                builder = AlertDialogBuilder(activity)
                builder.set_title(title)
                builder.set_message(message)
                builder.set_positive_button("OK", lambda b, w: b.dismiss())
                builder.show()
            except Exception:
                DebugLogger.make_log(f"ERROR showing info dialog: {traceback.format_exc()}")
        run_on_ui_thread(show_dialog)

    def get_input_media_from_message(self, message_object):
        """Extracts the necessary TLRPC media object from a replied-to message."""
        if not message_object or not hasattr(message_object, "messageOwner"):
            return None
        media = getattr(message_object.messageOwner, "media", None)
        if not media:
            return None
        # Handle photos
        if isinstance(media, TLRPC.TL_messageMediaPhoto) and hasattr(media, "photo"):
            photo = media.photo
            if not isinstance(photo, TLRPC.TL_photo):
                return None
            input_media = TLRPC.TL_inputMediaPhoto()
            input_media.id = TLRPC.TL_inputPhoto()
            input_media.id.id = photo.id
            input_media.id.access_hash = photo.access_hash
            input_media.id.file_reference = photo.file_reference if photo.file_reference is not None else bytearray(0)
            return input_media
        # Handle documents (stickers, files, videos)
        if isinstance(media, TLRPC.TL_messageMediaDocument) and hasattr(media, "document"):
            doc = media.document
            if not isinstance(doc, TLRPC.TL_document):
                return None
            input_media = TLRPC.TL_inputMediaDocument()
            input_media.id = TLRPC.TL_inputDocument()
            input_media.id.id = doc.id
            input_media.id.access_hash = doc.access_hash
            input_media.id.file_reference = doc.file_reference if doc.file_reference is not None else bytearray(0)
            return input_media
        return None

    def show_stopped_dialog(self, activity, final_count: int):
        """Displays a dialog confirming that the spam task was stopped."""
        def show_dialog():
            if not activity: return
            try:
                builder = AlertDialogBuilder(activity)
                builder.set_title("✅ Task Stopped")
                builder.set_message(f"The spam task was successfully stopped.\n\nItems sent: {final_count}")
                builder.set_positive_button("OK", lambda b, w: b.dismiss())
                builder.show()
            except Exception:
                DebugLogger.make_log(f"ERROR showing stopped dialog: {traceback.format_exc()}")
        run_on_ui_thread(show_dialog)

    def _delete_single_message(self, chat_id, message_id):
        """Sends a request to delete a single message by its ID."""
        try:
            id_list = ArrayList()
            id_list.add(Integer(message_id))
            channel_id = 0
            # Handle channel IDs which are different from group/user IDs
            if str(chat_id).startswith("-100"):
                channel_id = int(str(chat_id)[4:])
            get_messages_controller().deleteMessages(id_list, None, None, chat_id, 0, True, channel_id)
        except Exception:
            DebugLogger.make_log(f"ERROR deleting message ID {message_id}: {traceback.format_exc()}")

    def extract_message_id(self, response) -> int:
        """Extracts the message ID from various possible TLRPC response types."""
        if isinstance(response, TLRPC.TL_updateShortSentMessage):
            return response.id
        if hasattr(response, "updates") and response.updates:
            for i in range(response.updates.size()):
                update = response.updates.get(i)
                if isinstance(update, TLRPC.TL_updateNewMessage) and hasattr(update, "message"):
                    return update.message.id
                elif isinstance(update, TLRPC.TL_updateMessageID):
                    return update.id
        return None

    def show_error_dialog(self, activity, title: str, full_error_text: str, chat_id: int):
        """Displays a detailed error dialog with an option to send the log to the chat."""
        def show_dialog():
            if not activity: return
            builder = AlertDialogBuilder(activity)
            builder.set_title(title)
            builder.set_message(full_error_text)
            # Add a button to easily send the error log for debugging
            def on_send_log(bld, w):
                send_message({"peer": chat_id, "message": f"```{full_error_text}```"})
                bld.dismiss()
            builder.set_positive_button("Send Log to Chat", on_send_log)
            builder.set_negative_button("Dismiss", lambda b, w: b.dismiss())
            builder.show()
        run_on_ui_thread(show_dialog)
