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
    await update.message.reply_text('Hi!')


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
    # log all errors
    application.add_error_handler(error)

    # Start the Bot
    await application.start()

    # we need to pass a JobQueue inside the telegram consumer to communicate
    telegram_consumer = AioConsumer(amqp_url=amqp_url, jobqueue=application.job_queue, **kwargs)

    await telegram_consumer.run()
    try:
        await asyncio.Future()
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
