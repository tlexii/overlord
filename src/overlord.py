#!python
# -*- coding: utf-8 -*-
#

"""
Bot responds to commands via dispatcher and also starts a TelegramConsumer
which consumes messages from RabbitMQ.

"""

import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from reconnectingtelegramconsumer import ReconnectingTelegramConsumer
import configparser

log = logging.getLogger("overlord")


# Tell people they can set a timer - for testing
def start(update: Update, context: CallbackContext):
    update.message.reply_text('Hi! Use /set <seconds> to set a timer')


def alarm(context: CallbackContext):
    """Send the alarm message.
    """
    context.bot.send_message(context.job.context, text='Beep!')


def set(update: Update, context: CallbackContext):
    """ Adds a job to the queue
    """
    chat_id = update.message.chat_id
    try:
        # args[0] should contain the time for the timer in seconds
        due = int(context.args[0])
        if due < 0:
            update.message.reply_text('Sorry we cannot go back to future!')

        # Add job to queue
        job = context.job_queue.run_once(alarm, due, context=chat_id)
        context.chat_data['job'] = job

        update.message.reply_text('Timer successfully set!')

    except (IndexError, ValueError):
        update.message.reply_text('Usage: /set <seconds>')


# write telegram error messages into the log
def error(update: Update, context: CallbackContext):
    log.warning('Update "%s" caused error "%s"' % (update, context.error))


# configuration from a file
def parse_config(file):
    """ Read the local configuration from the file specified.

    """
    log.debug("parsing config file: {}".format(file))
    config = configparser.ConfigParser()
    config.read(file)
    return config


def overlord_main(file='overlord.conf'):

    # main bot config
    kwargs = dict(parse_config(file).items("DEFAULT"))

    # we need our access token from config to get an Updater
    updater = Updater(kwargs["access_token"], use_context=True)

    # a connection url to rabbit is mandatory
    amqp_url = kwargs["amqp_url"]

    # but dont include in kwargs
    if "amqp_url" in kwargs:
        del kwargs["amqp_url"]

    # we need to pass a JobQueue inside the telegram consumer to communicate
    telegram_consumer = ReconnectingTelegramConsumer(amqp_url=amqp_url, jobqueue=updater.job_queue, **kwargs)

    # on different commands - answer in Telegram
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(CommandHandler("help", start))
    updater.dispatcher.add_handler(CommandHandler("set", set))

    # log all errors
    updater.dispatcher.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # start the MQ consumer
    try:
        telegram_consumer.run()      # does block
    except KeyboardInterrupt:
        log.info('interrupted')

    updater.stop()
    telegram_consumer.stop()


if __name__ == '__main__':
    PID_FILE = "/var/run/overlord.pid"
    with open(PID_FILE, "w") as pidfile:
        pidfile.write("%s\n" % os.getpid())
    LOG_FORMAT = '%(asctime)s %(levelname)-8s %(name)-15s %(message)s'
    LOG_FILE = "/var/log/overlord/overlord.log"
    logging.basicConfig(filename=LOG_FILE, format=LOG_FORMAT, level=logging.INFO)
    overlord_main()
