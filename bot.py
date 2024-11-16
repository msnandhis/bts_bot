import asyncio
import requests
import json
import hashlib
import os
import hmac
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Token for Telegram Bot
TOKEN = os.getenv("TOKEN")

# Cryptomus API Key and Merchant ID

CRYPTOMUS_API_KEY = os.getenv("CRYPTOMUS_API_KEY")
CRYPTOMUS_MERCHANT_ID = os.getenv("CRYPTOMUS_MERCHANT_ID")

# States for conversation
STARS, RECIPIENT, TELEGRAM_ID, CRYPTO, PAYMENT = range(5)

def generate_signature(secret_key, payload):
    """Generates a signature using HMAC-SHA256."""
    # Convert the payload dictionary to a JSON string
    payload_str = json.dumps(payload, separators=(',', ':'))
    # Create the signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        payload_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks how many stars the user wants to buy."""
    await update.message.reply_text(
        "Welcome to StarSeller Bot! 🎉\nHow many stars would you like to buy?"
    )
    return STARS

async def stars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the number of stars and asks for recipient information."""
    context.user_data['stars'] = update.message.text
    reply_keyboard = [['Myself', 'Someone else']]
    await update.message.reply_text(
        'Are you buying stars for yourself or someone else?',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return RECIPIENT

async def recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the recipient type and asks for Telegram ID if necessary."""
    context.user_data['recipient'] = update.message.text
    if update.message.text == 'Someone else':
        await update.message.reply_text('Please provide the Telegram ID of the recipient:')
        return TELEGRAM_ID
    else:
        context.user_data['telegram_id'] = update.message.chat_id
        return await crypto(update, context)

async def telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the Telegram ID of the recipient and moves to crypto selection."""
    context.user_data['telegram_id'] = update.message.text
    return await crypto(update, context)

async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user to select a cryptocurrency for payment."""
    reply_keyboard = [['USDT', 'Bitcoin', 'Ethereum']]
    await update.message.reply_text(
        'Please select the cryptocurrency you want to use for payment:',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
    )
    return CRYPTO

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Creates a static wallet using Cryptomus API and provides the wallet address to the user."""
    crypto_choice = update.message.text
    context.user_data['crypto'] = crypto_choice

    # Calculate the amount in USD based on number of stars
    stars = int(context.user_data['stars'])
    amount = stars * 0.2  # Multiply quantity by 0.2 to get USD value

    # Define network based on currency choice (adjust based on your needs)
    network = 'tron' if crypto_choice == 'USDT' else 'mainnet'

    # Cryptomus API to create a static wallet
    url = "https://api.cryptomus.com/v1/wallet"
    wallet_data = {
        "currency": crypto_choice,
        "network": network,
        "order_id": f"{update.message.chat_id}-{stars}",
        "url_callback": "https://yourwebsite.com/payment-callback"  # Optional: Set your callback URL here
    }

    # Generate the signature for the payload
    sign = generate_signature(CRYPTOMUS_API_KEY, wallet_data)

    headers = {
        "merchant": CRYPTOMUS_MERCHANT_ID,
        "sign": sign,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=wallet_data, headers=headers)
    response_data = response.json()

    # Log the response for debugging
    print(f"Cryptomus API Response: {response_data}")

    if response.status_code == 200 and response_data.get("state") == 0:
        wallet_address = response_data["result"]["address"]
        payment_url = response_data["result"]["url"]

        await update.message.reply_text(
            f'Please complete your payment using the following address:\n{wallet_address}\nOr use this link: {payment_url}\nOnce payment is confirmed, your stars will be delivered.'
        )
        return PAYMENT
    else:
        error_message = response_data.get("message", "Unknown error")
        await update.message.reply_text(
            f'There was an error creating the payment wallet: {error_message}. Please try again later.'
        )
        return ConversationHandler.END

async def payment_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirms payment and hits the provided API to send stars."""
    # Assuming payment is confirmed (you will need to implement a proper callback handling here)
    payment_confirmed = True  # Placeholder for actual payment confirmation check

    if payment_confirmed:
        # Data to send to your API
        telegram_id = context.user_data.get('telegram_id')
        stars = context.user_data['stars']

        # API endpoint and headers (replace 'api-key' with your actual API key)
        url = "https://tg.parssms.info/v1/stars/testnet/payment"
        headers = {
            'Content-Type': 'application/json',
            'api-key': 'd31769b2-a9ae-45c5-ae79-9ca2d4e25722'  # Replace with your actual API key
        }
        
        # Create the payload for the API request
        payload = json.dumps({
            "query": telegram_id,  # This should be the username or ID of the user receiving the stars
            "quantity": stars  # Number of stars the user wants to send
        })

        # Make the API request to send stars
        response = requests.post(url, data=payload, headers=headers)

        # Handle the response
        if response.status_code == 200:
            await update.message.reply_text('Stars have been successfully sent! 🌟')
        else:
            await update.message.reply_text('There was an error sending the stars. Please contact support.')

    else:
        await update.message.reply_text('Payment not yet confirmed. Please wait a few minutes and try again.')

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text('Transaction has been cancelled. If you need anything else, just type /start.')
    return ConversationHandler.END

async def run_bot() -> None:
    # Set up the Application with your bot's token
    application = ApplicationBuilder().token(TOKEN).build()

    # Define the conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stars)],
            RECIPIENT: [MessageHandler(filters.Regex('^(Myself|Someone else)$'), recipient)],
            TELEGRAM_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_id)],
            CRYPTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment)],
            PAYMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_confirmation)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add the conversation handler to the application
    application.add_handler(conv_handler)

    # Start the bot by polling Telegram for new messages
    await application.initialize()
    try:
        await application.start()
        await application.updater.start_polling()
        await asyncio.Event().wait()  # Keeps the bot running forever, without stopping
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    asyncio.run(run_bot())
