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
        self.keymap = {}

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
        elif basic_deliver.routing_key == "bot.motion_areadetect":
            self.motion_area(basic_deliver, properties, body)
        elif basic_deliver.routing_key == "bot.motion_moviecomplete":
            self.motion_movie(basic_deliver, properties, body)
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

    def motion_area(self, basic_deliver, properties, body):
        """Display an incoming motion area placeholder, remember key.

        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: contains the id - timestamp string

        """

        try:
            # read the key e.g. '2022-03-06_082218'
            key=bytes.decode(body)
            # plain url placeholder message
            outputmsg='https://overworld.net.au/motion2/event.php?k={0}'.format(key)

            def basicMsg(context: CallbackContext):
                my_msg =  context.bot.sendMessage(self._target_group_chat,
                    disable_notification=True,
                    disable_web_page_preview=True,
                    text=outputmsg)

                # store mapping from key to message_id
                key = str(context.job.context)
                self.keymap[key] = my_msg.message_id
                log.info('saving {0}->{1}'.format(key,my_msg.message_id))

            self._jobqueue.run_once(basicMsg, 0, context=key )

        except Exception as err:
            log.error('Error queueing motion job: {0}'.format(err))

    def motion_movie(self, basic_deliver, properties, body):
        """Update an existing motion area placeholder with an URL.

        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param str|unicode body: The message body

        """

        try:
            key=bytes.decode(body)
            log.info('looking for key: {0}'.format(key))
            outputmsg='https://overworld.net.au/motion2/event.php?k={0}'.format(key)
            if key in self.keymap:
                msg_id = self.keymap[key]
                log.info('loaded {0}->{1}'.format(key,msg_id))
                self.keymap.pop(key)
                def updateMsg(context: CallbackContext):
                    my_msg =  context.bot.edit_message_text(chat_id=self._target_group_chat,
                        message_id=msg_id,
                        text=outputmsg,
                        disable_web_page_preview=False)
                self._jobqueue.run_once(updateMsg, 0)
            else:
                def basicMsg(context: CallbackContext):
                    my_msg =  context.bot.sendMessage(self._target_group_chat, outputmsg)
                self._jobqueue.run_once(basicMsg, 0)

        except Exception as err:
            log.error('Error queueing nagios job: {0}'.format(err))
