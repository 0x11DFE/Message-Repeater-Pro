# Message Repeater Pro

[![Version](https://img.shields.io/badge/version-4.2.0-blue.svg)](https://github.com/0x11DFE/Message-Repeater-Pro/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Telegram](https://img.shields.io/badge/author-%40T3SL4-blue.svg)](https://t.me/T3SL4)

An advanced plugin for extraGram clients to automate sending repetitive messages, create fun text effects, or test bot flood limits. Supports text, media, and Markdown.

> **🔐 ⚠️ DISCLAIMER – READ BEFORE USING ⚠️**
> This plugin is provided strictly for educational, testing, and personal automation purposes only. It is not intended for spamming or violating [Telegram’s Terms of Service](https://telegram.org/tos).
>
> The author does not encourage or support any form of abuse, unsolicited messaging, or unauthorized activity on Telegram or any other platform.
> - Misuse of this plugin to violate Telegram's spam policies (e.g. sending repetitive or unsolicited content to users/groups) can result in account limitations or permanent bans. You are solely responsible for how you use this tool.
> - By using this plugin, you agree to use it responsibly, ethically, and entirely at your own risk. The author assumes no liability for any actions taken with or consequences arising from its use.

---

## 📸 Preview

![Plugin Preview](https://github.com/0x11DFE/Message-Repeater-Pro/raw/refs/heads/main/repeater_pro_preview.gif)


## ✨ Features

* **Repeat Any Content:** Automate sending text, photos, stickers, videos, and files.
* **Flash Mode:** Send messages that automatically delete after a custom delay using the `.spamdel` command.
* **Repeat Last Command:** Instantly re-run your last command by simply sending `.spam` or `.spamdel` alone.
* **Full Markdown Support:** Send messages with **bold**, _italic_, `monospace`, and [hyperlinks](https://telegram.org/).
* **Highly Configurable:**
    * Customize command names.
    * Set custom delays between messages (in seconds, supports decimals).
    * Configure safety limits (`max_spam_limit`, `confirmation_threshold`).
* **Built-in Debugging:** Save detailed error logs to a file for easy troubleshooting.


## ⚙️ Installation

1.  Go to the [**Releases**](https://github.com/0x11DFE/Message-Repeater-Pro/releases) page and download the latest `.py` file.
2.  Using your device's file manager, **rename the file extension** from `.py` to `.plugin`.
3.  Send the `.plugin` file to yourself in Telegram (e.g., in your "Saved Messages").
4.  Tap on the file you just sent. The client will show a confirmation dialog.
5.  Tap **INSTALL PLUGIN** to finish.

## 🚀 How to Use

The plugin is controlled by commands sent in any chat. For details, check the FAQ inside the plugin's settings.

### General Commands

* `.spam` or `.spamdel`
    * Used with arguments, this sends a message or media multiple times.
    * **Used alone, this repeats the last spam command.**
* `.spamstop`
    * Immediately stops any active task.
* `.spamdebuglog`
    * Saves a debug log file and shows you the path.

### Text Automation

To send text repeatedly, use the format: `.spam [text] [count]`

```
.spam Hello World [50]
```

To add a delay between messages, add it in a third bracket (in seconds):

```
.spam Beep [10] [1.5]
```

### Media Automation

To repeat a photo, sticker, video, or file, **reply** to that media with the command:

```
.spam [count] [delay]
```
The delay is optional.

### Flash Mode (`.spamdel`)

This command works exactly like `.spam`, but each message is automatically deleted after a configurable delay (default is 2.5 seconds).

```
.spamdel This will flash and disappear [10]
```

## 🔧 Configuration

All settings, including command names and delays, can be configured by going to:
`Settings > extraGram Settings > Plugins > Message Repeater Pro`


## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/0x11DFE/Message-Repeater-Pro/issues).

## ❤️ Support the Developer

If you find this plugin useful, please consider supporting its development. Thank you!

* **TON:** `UQDx2lC9bQW3A4LAfP4lSqtSftQSnLczt87Kn_CIcmJhLicm`
* **USDT (TRC20):** `TXLJNebRRAhwBRKtELMHJPNMtTZYHeoYBo`


## 📜 License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](https://www.gnu.org/licenses/gpl-3.0.html) file for the full license text.
