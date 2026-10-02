import asyncio
import re
import json
import os
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from playwright.async_api import async_playwright

BOT_TOKEN = "7788517986:AAExWAPtCkWlPN-20EOsBZDMP3yRPIhyQ4U"
ACCOUNTS_FILE = "accounts_session.json"
ALLOWED_FILE = "allowed_users.json"

OWNER_ID = 5773956827

ASK_PHONE, ASK_SESSION, ASK_UTR, ASK_OTP = range(4)
user_sessions = {}

def load_allowed():
    if os.path.exists(ALLOWED_FILE):
        try:
            with open(ALLOWED_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return [OWNER_ID]
    return [OWNER_ID]

def save_allowed(users_list):
    with open(ALLOWED_FILE, "w") as f:
        json.dump(users_list, f, indent=4)

def is_authorized(user_id: int) -> bool:
    allowed = load_allowed()
    return (user_id == OWNER_ID) or (user_id in allowed)

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_accounts(data):
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False

    if is_authorized(user.id):
        return True

    deny_text = (
        f"⛔ **Access Denied!**\n\n"
        f"Ye private bot hai. Owner se permission maangein.\n"
        f"Aapki User ID: `{user.id}`"
    )
    if update.callback_query:
        await update.callback_query.answer("⛔ Access Denied! Owner ki permission chahiye.", show_alert=True)
    elif update.message:
        await update.message.reply_text(deny_text, parse_mode="Markdown")

    user_name = user.first_name or "Unknown"
    user_handle = f"@{user.username}" if user.username else "No Username"
    alert_txt = (
        f"🔔 **Naye User Ne Access Maanga!**\n\n"
        f"👤 Name: {user_name}\n"
        f"🏷 Handle: {user_handle}\n"
        f"🆔 ID: `{user.id}`\n\n"
        f"Kya aap inhe access dena chahte hain?"
    )
    buttons = [
        [
            InlineKeyboardButton("✅ Allow Access", callback_data=f"allow_{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"deny_{user.id}")
        ]
    ]
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=alert_txt,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return False

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return ConversationHandler.END

    chat_id = str(update.effective_chat.id)
    context.user_data.clear()
    accounts = load_accounts().get(chat_id, {})

    buttons = []
    for phone in accounts.keys():
        buttons.append([InlineKeyboardButton(f"📱 {phone} (Start)", callback_data=f"run_{phone}")])

    buttons.append([InlineKeyboardButton("➕ Add Account (Phone + Session)", callback_data="add_acc")])
    buttons.append([InlineKeyboardButton("⛔ Stop Active Task", callback_data="stop_task")])

    await update.message.reply_text(
        "👋 **AR Wallet Session Bot**\n\nAccount chunein ya naya account add karein:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    allowed = load_allowed()
    msg = f"👥 **Allowed Users ({len(allowed)}):**\n"
    buttons = []
    for u in allowed:
        tag = " (Owner)" if u == OWNER_ID else ""
        msg += f"• `{u}`{tag}\n"
        if u != OWNER_ID:
            buttons.append([InlineKeyboardButton(f"❌ Remove {u}", callback_data=f"revoke_{u}")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def add_acc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👉 Apna **10-digit Phone Number** bhejein:")
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return ConversationHandler.END

    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text("❌ Kripya sahi 10-digit phone number dalein:")
        return ASK_PHONE

    context.user_data['temp_phone'] = phone
    await update.message.reply_text(
        f"✅ Number: `{phone}`\n\n👉 Ab Orion se copy kiya hua data text file (`session.txt`) bhejein ya paste karein:",
        parse_mode="Markdown"
    )
    return ASK_SESSION

async def get_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return ConversationHandler.END

    phone = context.user_data.get('temp_phone')
    chat_id = str(update.effective_chat.id)

    if update.message.document:
        doc_file = await update.message.document.get_file()
        byte_data = await doc_file.download_as_bytearray()
        raw_data = byte_data.decode('utf-8')
    else:
        raw_data = update.message.text.strip()

    try:
        parsed_json = json.loads(raw_data)
    except Exception:
        await update.message.reply_text("❌ JSON valid nahi hai! Sahi file bhejein:")
        return ASK_SESSION

    accounts = load_accounts()
    if chat_id not in accounts:
        accounts[chat_id] = {}

    accounts[chat_id][phone] = parsed_json
    save_accounts(accounts)

    await update.message.reply_text(
        f"🎉 **Account Save Ho Gaya!**\n📱 Phone: `{phone}`\n\nAb chalane ke liye `/start` dabayein.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Process cancel ho gaya. /start karein.")
    return ConversationHandler.END

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return
    await stop_user_session(update.effective_chat.id, context)

async def stop_user_session(chat_id, context):
    if chat_id in user_sessions:
        session = user_sessions[chat_id]
        session["running"] = False
        try:
            if "browser" in session:
                await session["browser"].close()
        except Exception:
            pass
        phone = session.get("phone", "")
        del user_sessions[chat_id]
        await context.bot.send_message(chat_id, f"🛑 **Session STOP ho gaya** ({phone}).")
    else:
        await context.bot.send_message(chat_id, "ℹ️ Koi active running task nahi hai.")

async def send_order_matched_alert(chat_id, page, context):
    amt = "Checked on Screen"
    try:
        amt_elem = await page.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll('*'));
                for (let el of els) {
                    const t = (el.innerText || '').trim();
                    if (/^₹\\s*[0-9,]+(\\.[0-9]{2})?$/.test(t)) {
                        return t;
                    }
                }
                return null;
            }
        """)
        if amt_elem:
            amt = amt_elem
        else:
            body_text = await page.inner_text("body")
            clean_txt = re.sub(r'1000\s*-\s*2000', '', body_text)
            clean_txt = re.sub(r'1,000\s*-\s*2,000', '', clean_txt)
            m = re.search(r'₹\s*([0-9,.]+)', clean_txt)
            if m:
                amt = f"₹ {m.group(1)}"
    except Exception:
        pass

    photo = await page.screenshot()
    buttons = [
        [InlineKeyboardButton("✅ Payment Done (Enter UTR)", callback_data="input_utr")],
        [InlineKeyboardButton("⛔ Cancel Order / Stop", callback_data="stop_task")]
    ]
    await context.bot.send_photo(
        chat_id,
        photo=photo,
        caption=f"🚨🚨 **ORDER MATCH HO GAYA!**\n\n💰 **Exact Amount: {amt}**\n⚡ QR scan karke payment complete karein, fir niche button par tap karein!",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def utr_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👉 Apna **12-digit UTR / Ref No** yahan type karke bhejein:")
    return ASK_UTR

async def handle_utr_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    utr_val = update.message.text.strip()

    if chat_id not in user_sessions:
        await update.message.reply_text("❌ Session active nahi hai. /start karein.")
        return ConversationHandler.END

    session = user_sessions[chat_id]
    page = session["page"]

    await update.message.reply_text(f"⏳ UTR `{utr_val}` submit kiya ja raha hai...")

    try:
        input_box = page.locator('input[placeholder*="UTR"], input[placeholder*="Ref"], input[type="text"]').first
        if await input_box.count() > 0:
            await input_box.fill(utr_val)
        else:
            await page.touchscreen.tap(195, 750)
            await page.keyboard.type(utr_val)

        await asyncio.sleep(1)

        submit_btn = page.locator('button:has-text("Submit"), div:has-text("Submit")').first
        if await submit_btn.count() > 0:
            await submit_btn.click(force=True)
        else:
            await page.touchscreen.tap(300, 840)

        await asyncio.sleep(3)

        shot = await page.screenshot()
        await context.bot.send_photo(
            chat_id,
            photo=shot,
            caption=f"✅ UTR submit ho gaya!\n\n👉 Agar screen par OTP manga hai, to **OTP number** bhejein (Nahi manga to /stop karein):"
        )
        return ASK_OTP

    except Exception as e:
        await update.message.reply_text(f"❌ UTR submit error: {str(e)}")
        return ConversationHandler.END

async def handle_otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    otp_val = update.message.text.strip()

    if chat_id not in user_sessions:
        await update.message.reply_text("❌ Session active nahi hai. /start karein.")
        return ConversationHandler.END

    session = user_sessions[chat_id]
    page = session["page"]

    await update.message.reply_text(f"⏳ OTP `{otp_val}` submit kiya ja raha hai...")

    try:
        otp_box = page.locator('input[placeholder*="OTP"], input[placeholder*="Code"], input[type="number"]').first
        if await otp_box.count() > 0:
            await otp_box.fill(otp_val)
        else:
            await page.keyboard.type(otp_val)

        await asyncio.sleep(1)

        confirm_btn = page.locator('button:has-text("Confirm"), button:has-text("Submit"), div:has-text("Confirm")').first
        if await confirm_btn.count() > 0:
            await confirm_btn.click(force=True)

        await asyncio.sleep(4)
        final_shot = await page.screenshot()
        await context.bot.send_photo(
            chat_id,
            photo=final_shot,
            caption="🎉 **Order Successfully Completed!**"
        )
        await stop_user_session(chat_id, context)
        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"❌ OTP Error: {str(e)}")
        return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if data.startswith("allow_") and user_id == OWNER_ID:
        target_uid = int(data.split("_")[1])
        allowed = load_allowed()
        if target_uid not in allowed:
            allowed.append(target_uid)
            save_allowed(allowed)
        await query.answer("User ko allow kar diya!")
        await query.edit_message_text(f"✅ **ID: `{target_uid}` ko access de diya gaya hai!**", parse_mode="Markdown")
        try:
            await context.bot.send_message(target_uid, "🎉 **Badhaai ho!**\nOwner ne aapko access approve kar diya hai. Ab aap `/start` karke use kar sakte hain!")
        except Exception:
            pass
        return

    if data.startswith("deny_") and user_id == OWNER_ID:
        target_uid = int(data.split("_")[1])
        await query.answer("Reject kar diya.")
        await query.edit_message_text(f"❌ **ID: `{target_uid}` ka request reject kiya gaya.**", parse_mode="Markdown")
        return

    if data.startswith("revoke_") and user_id == OWNER_ID:
        target_uid = int(data.split("_")[1])
        allowed = load_allowed()
        if target_uid in allowed:
            allowed.remove(target_uid)
            save_allowed(allowed)
        await query.answer("Access hata diya!")
        await query.edit_message_text(f"🗑️ **ID: `{target_uid}` ka access revoke ho gaya.**", parse_mode="Markdown")
        return

    if not await check_access(update, context):
        return

    await query.answer()

    if data == "stop_task":
        await query.edit_message_text("⏳ Session close ho raha hai...")
        await stop_user_session(chat_id, context)
        return

    if data.startswith("run_"):
        phone = data.split("_")[1]
        accounts = load_accounts().get(str(chat_id), {})
        session_data = accounts.get(phone)

        if not session_data:
            await query.edit_message_text("❌ Session nahi mila. /start karein.")
            return

        if chat_id in user_sessions:
            await stop_user_session(chat_id, context)

        await query.edit_message_text(f"⏳ **{phone}** session inject ho raha hai...\nBrowser start kiya ja raha hai...")
        asyncio.create_task(run_direct_session(chat_id, phone, session_data, context))

    elif data.startswith("pay_"):
        if chat_id not in user_sessions:
            await query.edit_message_text("Session expire ho chuka hai. /start karein.")
            return

        session = user_sessions[chat_id]
        page = session["page"]
        app_name = data.split("_")[1]

        await query.edit_message_text(f"⏳ **{app_name}** chuna gaya.\n₹1,000 - ₹2,000 row par matching lagai ja rahi hai...")

        try:
            body_txt = await page.inner_text("body")
            if "Cancel Matching" in body_txt:
                cancel_btn = page.locator('text="Cancel Matching"')
                if await cancel_btn.count() > 0:
                    await cancel_btn.first.click(force=True, timeout=2000)
                    await asyncio.sleep(1.5)

            body_txt = await page.inner_text("body")
            if "Back to Order List" in body_txt:
                back_btn = page.locator('text="Back to Order List"')
                if await back_btn.count() > 0:
                    await back_btn.first.click(force=True, timeout=2000)
                    await asyncio.sleep(2)

            otp_tab = page.locator('text="OTP-UPI"').first
            if await otp_tab.count() > 0:
                await otp_tab.click(force=True, timeout=2000)
                await asyncio.sleep(1.5)

            await page.touchscreen.tap(330, 828)
            await asyncio.sleep(0.5)

            buys = page.locator('text="Buy"')
            cnt = await buys.count()
            if cnt >= 7:
                b7 = buys.nth(6)
                box = await b7.bounding_box()
                if box:
                    await page.touchscreen.tap(box['x'] + box['width']/2, box['y'] + box['height']/2)

            await asyncio.sleep(2)

            if app_name.lower() == "phonepe":
                phonepe_elem = page.locator('xpath=//*[text()="PhonePe" or contains(text(), "PhonePe")]')
                if await phonepe_elem.count() > 0:
                    box_p = await phonepe_elem.last.bounding_box()
                    if box_p:
                        await page.touchscreen.tap(box_p['x'] + box_p['width']/2, box_p['y'] + box_p['height']/2)
                    else:
                        await phonepe_elem.last.click(force=True)
                else:
                    await page.touchscreen.tap(195, 620)
            elif app_name.lower() == "paytm":
                paytm_elem = page.locator('xpath=//*[text()="Paytm" or contains(text(), "Paytm")]')
                if await paytm_elem.count() > 0:
                    box_ptm = await paytm_elem.last.bounding_box()
                    if box_ptm:
                        await page.touchscreen.tap(box_ptm['x'] + box_ptm['width']/2, box_ptm['y'] + box_ptm['height']/2)
                    else:
                        await paytm_elem.last.click(force=True)
                else:
                    await page.touchscreen.tap(195, 680)

            await asyncio.sleep(3)

            check_txt = await page.inner_text("body")

            if "Countdown to Expiry" in check_txt or "Use Mobile Scan code" in check_txt or "Input or Paste UTR" in check_txt or "Matched, pending payment" in check_txt:
                await send_order_matched_alert(chat_id, page, context)
                return

            start_shot = await page.screenshot()

            if "Matching" in check_txt or "Searching available orders" in check_txt:
                await context.bot.send_photo(
                    chat_id,
                    photo=start_shot,
                    caption="🚀 **Round #1 Matching Start!** (₹1,000 - ₹2,000)\nPortal continuously monitor kar raha hai."
                )
                asyncio.create_task(matching_monitor(chat_id, page, context))
            else:
                await context.bot.send_photo(
                    chat_id,
                    photo=start_shot,
                    caption="⚠️ Status check screenshot:"
                )

        except Exception as e:
            try:
                err_pic = await page.screenshot()
                await context.bot.send_photo(chat_id, photo=err_pic, caption=f"❌ Error: {str(e)}")
            except Exception:
                await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")

async def run_direct_session(chat_id, phone, session_data, context):
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security"
            ]
        )
        context_browser = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            has_touch=True
        )

        page = await context_browser.new_page()
        page.set_default_timeout(15000)

        user_sessions[chat_id] = {
            "playwright": p,
            "browser": browser,
            "page": page,
            "phone": phone,
            "running": True
        }

        await page.goto("https://arbpay.ai", wait_until="commit", timeout=45000)
        await asyncio.sleep(2)

        await page.evaluate("""
            (storageMap) => {
                for (let k in storageMap) {
                    const val = typeof storageMap[k] === 'object' ? JSON.stringify(storageMap[k]) : storageMap[k];
                    localStorage.setItem(k, val);
                }
            }
        """, session_data)

        await page.reload(wait_until="commit", timeout=30000)
        await asyncio.sleep(3)

        for _ in range(3):
            close_btn = page.locator('button:has-text("Close"), div:has-text("Close"), button:has-text("Go buy")')
            if await close_btn.count() > 0:
                try:
                    await close_btn.first.click(force=True, timeout=1500)
                    await asyncio.sleep(1)
                except Exception:
                    pass

        buy_arb = page.locator('text="Buy ARB"').first
        if await buy_arb.count() > 0:
            try:
                await buy_arb.click(force=True, timeout=3000)
            except Exception:
                pass
        await asyncio.sleep(2)

        curr_body = await page.inner_text("body")
        if "Cancel Matching" in curr_body:
            c_btn = page.locator('text="Cancel Matching"')
            if await c_btn.count() > 0:
                await c_btn.first.click(force=True, timeout=2000)
                await asyncio.sleep(1.5)

        curr_body = await page.inner_text("body")
        if "Back to Order List" in curr_body:
            back_btn = page.locator('text="Back to Order List"')
            if await back_btn.count() > 0:
                await back_btn.first.click(force=True, timeout=2000)
                await asyncio.sleep(2)

        otp_tab = page.locator('text="OTP-UPI"').first
        if await otp_tab.count() > 0:
            try:
                box = await otp_tab.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                else:
                    await otp_tab.click(force=True, timeout=2000)
            except Exception:
                pass
        await asyncio.sleep(2)

        buttons = [
            [InlineKeyboardButton("Paytm", callback_data="pay_Paytm"), InlineKeyboardButton("PhonePe", callback_data="pay_PhonePe")],
            [InlineKeyboardButton("⛔ Cancel / Stop", callback_data="stop_task")]
        ]
        
        status_shot = await page.screenshot()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=status_shot,
            caption=f"✅ **{phone} Ready!** (Order List Loaded)\n\nKis payment app se matching start karni hai?",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

        while chat_id in user_sessions and user_sessions[chat_id]["running"]:
            await asyncio.sleep(1)

    except Exception as e:
        if chat_id in user_sessions and user_sessions[chat_id]["running"]:
            try:
                err_pic = await user_sessions[chat_id]["page"].screenshot()
                await context.bot.send_photo(chat_id, photo=err_pic, caption=f"⚠️ Screen status check:\nError: {str(e)}")
            except Exception:
                await context.bot.send_message(chat_id, f"❌ Session Error: {str(e)}")
        try:
            if chat_id in user_sessions:
                await user_sessions[chat_id]["browser"].close()
                await user_sessions[chat_id]["playwright"].stop()
        except Exception:
            pass

async def matching_monitor(chat_id, page, context):
    round_count = 2
    while chat_id in user_sessions and user_sessions[chat_id]["running"]:
        try:
            body_text = await page.inner_text("body")

            if "Countdown to Expiry" in body_text or "Use Mobile Scan code" in body_text or "Input or Paste UTR" in body_text or "Matched, pending payment" in body_text:
                await send_order_matched_alert(chat_id, page, context)
                break

            ui_state = await page.evaluate("""
                () => {
                    const txt = document.body.innerText || '';
                    const hasSearching = txt.includes('Searching available orders');
                    const hasNoMatch = txt.includes('No match found') || txt.includes('multiple attempts');
                    
                    const btns = Array.from(document.querySelectorAll('*')).filter(
                        el => (el.innerText || '').trim() === 'Match Again' && el.offsetParent !== null
                    );
                    
                    return {
                        isSearching: hasSearching,
                        isNoMatch: hasNoMatch && !hasSearching,
                        hasButton: btns.length > 0
                    };
                }
            """)

            if ui_state.get("isSearching"):
                await asyncio.sleep(3)
                continue

            if ui_state.get("isNoMatch") and ui_state.get("hasButton"):
                btn = page.locator('text="Match Again"')
                if await btn.count() > 0:
                    b_elem = btn.first
                    box = await b_elem.bounding_box()
                    if box:
                        await page.touchscreen.tap(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    else:
                        await b_elem.click(force=True, timeout=2000)
                else:
                    await page.touchscreen.tap(195, 510)

                await asyncio.sleep(4)

                after_text = await page.inner_text("body")
                if "Countdown to Expiry" in after_text or "Use Mobile Scan code" in after_text or "Matched, pending payment" in after_text:
                    await send_order_matched_alert(chat_id, page, context)
                    break

                new_state = await page.evaluate("""
                    () => {
                        const txt = document.body.innerText || '';
                        return txt.includes('Searching available orders') || txt.includes('Cancel Matching');
                    }
                """)

                if new_state:
                    shot = await page.screenshot()
                    await context.bot.send_photo(
                        chat_id,
                        photo=shot,
                        caption=f"🔄 **Round #{round_count} Matching Start!**"
                    )
                    round_count += 1
                    await asyncio.sleep(22)
                    continue

            await asyncio.sleep(3)

        except Exception:
            if chat_id in user_sessions and user_sessions[chat_id]["running"]:
                await asyncio.sleep(3)
            else:
                break

async def dummy_web():
    app = web.Application()
    async def handler(request):
        return web.Response(text="Bot is running!")
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    add_acc_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_acc_callback, pattern="^add_acc$")],
        states={
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            ASK_SESSION: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, get_session)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        allow_reentry=True
    )

    utr_otp_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(utr_button_callback, pattern="^input_utr$")],
        states={
            ASK_UTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_utr_input)],
            ASK_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_otp_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        allow_reentry=True
    )

    app.add_handler(add_acc_handler)
    app.add_handler(utr_otp_handler)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    async def post_init(application):
        await dummy_web()

    app.post_init = post_init

    print(f"Bot running with Full UTR/OTP Flow (Owner: {OWNER_ID})...")
    app.run_polling()

if __name__ == "__main__":
    main()
