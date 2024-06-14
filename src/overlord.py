#!python
# -*- coding: utf-8 -*-
#

"""
Bot responds to commands via dispatcher and also starts a TelegramConsumer
which consumes messages from RabbitMQ.

"""

import asyncio
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from aioconsumer import AioConsumer
import configparser

log = logging.getLogger("overlord")
logging.getLogger("httpx").setLevel(logging.WARNING)


# Tell people they can set a timer - for testing
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Hi! Use /set <seconds> to set a timer')


async def alarm(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the alarm message.
    """
    await context.bot.send_message(context.job.chat_id, text='Beep!')


async def set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ Adds a job to the queue
    """
    chat_id = update.effective_message.chat_id
    try:
        # args[0] should contain the time for the timer in seconds
        due = float(context.args[0])
        if due < 0:
            await update.effective_message.reply_text(
                    'Sorry we cannot go back to future!')

        # Add job to queue
        context.job_queue.run_once(alarm, due, chat_id=chat_id,
                                   name=str(chat_id), data=due)

        await update.effective_message.reply_text('Timer successfully set!')

    except (IndexError, ValueError):
        await update.effective_message.reply_text('Usage: /set <seconds>')


# write telegram error messages into the log
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.warning('Update "%s" caused error "%s"' % (update, context.error))


# configuration from a file
def parse_config(file):
    """ Read the local configuration from the file specified.

    """
    log.debug("parsing config file: {}".format(file))
    config = configparser.ConfigParser()
    config.read(file)
    return config


async def main(file='overlord.conf') -> None:

    # main bot config
    kwargs = dict(parse_config(file).items("DEFAULT"))
    # a connection url to rabbit is mandatory
    amqp_url = kwargs["amqp_url"]
    # but dont include in kwargs
    if "amqp_url" in kwargs:
        del kwargs["amqp_url"]

    # we need our access token from config
    application = Application.builder().token(kwargs["access_token"]).build()
    await application.initialize()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("set", set))
    # log all errors
    application.add_error_handler(error)

    # Start the Bot
    await application.start()

    # we need to pass a JobQueue inside the telegram consumer to communicate
    telegram_consumer = AioConsumer(
        amqp_url=amqp_url, jobqueue=application.job_queue, **kwargs)

    await application.updater.start_polling()

    # loop = asyncio.get_event_loop()
    await telegram_consumer.run()
    try:
        # await asyncio.sleep(1)
        await asyncio.Future()
        # loop.run_until_completion(telegram_consumer.run())
    except KeyboardInterrupt:
        log.info('interrupted')

    await telegram_consumer.stop()
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == '__main__':
    LOG_FORMAT = '%(asctime)s %(levelname)-8s %(name)-15s %(message)s'
    logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
    config_file = os.environ.get('OVERLORD_CONFIG_FILE', './overlord.conf')
    try:
        asyncio.run(main(config_file))
    except KeyboardInterrupt:
        pass
