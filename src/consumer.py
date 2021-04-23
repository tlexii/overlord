# -*- coding: utf-8 -*-

from telegram.ext import CallbackContext
import logging
from baseconsumer import BaseConsumer
import redis

log = logging.getLogger("TelegramConsumer")
log.setLevel("DEBUG")


#
# Subclass BaseConsumer to isolate Telegram specific message handlers
# There is currently only one which sends the MQ message to a preconfigured
# Telegram group
#
class TelegramConsumer(BaseConsumer):
    """Extends the baseconsumer to handle telegram bot related functions.

    """

    def __init__(self, amqp_url, jobqueue, **kwargs):
        """Create a new instance of the TelegramConsumer class.

        :param str amqp_url: the connection URL
        :param object jobqueue: the telegram.bot.ext.JobQueue
        :param dict kwargs: additional configuration for the exchange
            MUST include 'target_chat' which is the id of the target
            telegram group

        """
        super().__init__(amqp_url, **kwargs)
        self._jobqueue = jobqueue
        self._target_group_chat = kwargs['target_chat']

    def on_message(self, unused_channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered from RabbitMQ.
        The properties passed in is an instance of BasicProperties with
        the message properties and the body is the message that was sent.

        :param pika.channel.Channel unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """

        if basic_deliver.routing_key == "bot.message":
            self.simple_msg(basic_deliver, properties, body)
        elif basic_deliver.routing_key == "bot.nagios":
            self.nagios_msg(basic_deliver, properties, body)
        else:
            log.error('Unhandled routing_key: {0}'.format(basic_deliver.routing_key))

        self.acknowledge_message(basic_deliver.delivery_tag)

    def simple_msg(self, basic_deliver, properties, body):
        """Handle simple messages with key bot.message.

        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """

        try:
            # handle the message by queueing a job in telegram bot
            def basicMsg(context: CallbackContext):
                context.bot.sendMessage(self._target_group_chat, text=bytes.decode(body))

            self._jobqueue.run_once(basicMsg, 0)

        except Exception as err:
            log.error('Error queueing simple job: {0}'.format(err))

    def nagios_msg(self, basic_deliver, properties, body):
        """Handle nagios status messages with key bot.nagios.

        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """

        try:
            # handle the message by queueing a job in telegram bot
            def basicMsg(context: CallbackContext):
                my_msg =  context.bot.sendMessage(self._target_group_chat, text=bytes.decode(body))

            self._jobqueue.run_once(basicMsg, 0)

        except Exception as err:
            log.error('Error queueing nagios job: {0}'.format(err))
