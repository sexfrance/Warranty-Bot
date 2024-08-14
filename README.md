<div align="center">
 
  <h2 align="center">Discord - Warranty Bot</h2>
  <p align="center">
A Discord bot for managing digital product warranties, automating replacement requests, and tracking customer reviews and vouches. Ideal for sellers on platforms like Sellix to ease after-sales support. The bot will check if the user vouched in the right format (+rep @ownerid quantity product price), if they made a 5 star review on the shop and if the warranty expired. It includes an auto warranty duration scrapper using product title, the warranty duration is of course customisable in products.json
    <br />
    <br />
    <a href="https://discord.gg/bestnitro">💬 Discord</a>
    ·
    <a href="https://github.com/sexfrance/Warranty-Bot#-changelog">📜 ChangeLog</a>
    ·
    <a href="https://github.com/sexfrance/Warranty-Bot/issues">⚠️ Report Bug</a>
    ·
    <a href="https://github.com/sexfrance/Warranty-Bot/issues">💡 Request Feature</a>
  </p>
</div>

### ⚙️ Installation

- Requires: `Python 3.9+`
- Make a python virtual environment: `python3 -m venv venv`
- Source the environment: `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (macOS, Linux)
- Install the requirements: `pip install -r requirements.txt`
- Start: `python3 main.py`

---

### 🔥 Features
- Nice Embeds
- Easy rebrand
- Creates vouch messages
- Can dm the user with his product (file/text) or stock (saved under stock/productname.txt)
- Checks if the user vouched in the rigt format (+rep <@ownerid> quantity product price)
- Checks if the user made a 5 star website review before opening a ticket
- Smart Ticket system included (.replace will close the ticket)
- Auto Scrapes warranty duration from product titles and saves data in product.json (Product id, title and warranty duration)
- Customizable, if you manually changed a warranty duration in json it will not update it while scrapping
- Can add excluded product ids for the warranty scrapper in excluded.json
- Everything in config.json is customizable and changable using the .set command
- And more!

#### Commands
-  ℹ️  `.help` - List all available commands
- 📨 `.replace_message` - Initiates a replacement request system
- 🗑️ `.remove_product <product_id>` - Removes and excludes a product by its ID in JSON 
- 🔑 `.create_warr <product_id> <duration>` - Creates a new warranty for a product
- 📦 `.stock <product> <file>` - Saves product to a stock file under stock/<product>.txt
- 🔄 `.replace <user> [amount] <product> [file/string]` - Sends a replacement embed to a user. It can be sent from stock (using the amount parameter) or a file/string (no amount parameter needed)
- 🧹 `.warr` - Displays an embed with the warranty duration of all products
- 🔧 `.set <setting> <value>` - Set various bot configurations. Use `.set help` for details
- 🔎 `.check_warr <user> <order_id>` - Checks if the user has vouched, left a web review, and if their warranty has not expired
---
#### 📹 Preview

![Queue Bot Help Command](https://i.imgur.com/51wmu0Q.png) ![Queue Bot Queue System](https://i.imgur.com/Jlq3c8r.png) ![Queue Bot DM](https://i.imgur.com/f04pX21.png) ![Queue Bot replacement request](https://i.imgur.com/F5uEeS2.png) ![Queue Vouch Required](https://i.imgur.com/0FYG7wh.png)

---
### ❗ Disclaimers

- I am not responsible for anything that may happen, such as API Blocking, Account Termination, etc.
- This was a quick project that was made for fun and personal use if you want to see further updates, star the repo & create an "issue" [here](https://github.com/sexfrance/Warranty-Bot/issues/)

---

### 📜 ChangeLog

```diff
v0.0.1 ⋮ 08/14/2024
! Initial release
```

---

<p align="center">
  <img src="https://img.shields.io/github/license/sexfrance/Warranty-Bot.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/stars/sexfrance/Warranty-Bot.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/languages/top/sexfrance/Warranty-Bot.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=python"/>
</p>
