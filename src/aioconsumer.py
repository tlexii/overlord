import asyncio

import aio_pika
import logging
import os
import configparser
from telegram.ext import ContextTypes

log = logging.getLogger("overlord")


class AioConsumer(object):

    def __init__(self, amqp_url, jobqueue, **kwargs) -> None:
        self._target_group_chat = kwargs['target_chat']
        # self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._jobqueue = jobqueue
        self._exchange = kwargs.get('exchange', 'exchange')
        self._exchange_type = kwargs.get('exchange_type', 'topic')
        self._queue = kwargs.get('queue', 'task_queue')
        self._routing_key = kwargs.get('routing_key', 'bot.message')
        self.connection = None
        self.keymap = {}

    async def process_message(self, message) -> None:
        async with message.process():
            # log.debug(message.body)
            if message.routing_key == "bot.message":
                await self.simple_msg(message.body)
            elif message.routing_key == "bot.motion_areadetect":
                await self.motion_area(message.body)
            elif message.routing_key == "bot.motion_moviecomplete":
                await self.motion_movie(message.body)
            elif message.routing_key == "bot.nagios":
                # TODO
                await self.simple(message.body)
            else:
                log.error('Unhandled routing_key: {0}'.format(
                                                message.routing_key))

            # TODO
            # await message.ack()

    async def simple_msg(self, body) -> None:
        """Handle simple messages with key bot.send_message.

        :param str|unicode body: The message body

        """

        try:
            # handle the message by queueing a job in telegram bot
            async def basicMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.send_message(self._target_group_chat,
                                               text=bytes.decode(body))

            self._jobqueue.run_once(basicMsg, 0.1)

        except Exception as err:
            log.error('Error queueing simple job: {0}'.format(err))

    async def motion_area(self, body):
        """Display an incoming motion area placeholder, remember key.

        :param str|unicode body: contains the id - timestamp string

        """

        try:
            # read the key e.g. '2022-03-06_082218'
            key = bytes.decode(body)
            # plain url placeholder message
            outputmsg = 'https://overworld.net.au/motion2/event.php?k={0}'\
                .format(key)

            async def basicMsg(context: ContextTypes.DEFAULT_TYPE):
                my_msg = await context.bot.send_message(
                        self._target_group_chat,
                        disable_notification=True,
                        disable_web_page_preview=True,
                        text=outputmsg)

                # store mapping from key to message_id
                key = str(context.job.data)
                self.keymap[key] = my_msg.message_id
                log.info('saving {0}->{1}'.format(key, my_msg.message_id))

            self._jobqueue.run_once(basicMsg, 0.1, data=key)

        except Exception as err:
            log.error('Error queueing motion job: {0}'.format(err))

    async def motion_movie(self, body):
        """Update an existing motion area placeholder with an URL.

        :param str|unicode body: The message body

        """

        try:
            key = bytes.decode(body)
            log.info('looking for key: {0}'.format(key))
            outputmsg = 'https://overworld.net.au/motion2/event.php?k={0}'\
                .format(key)
            if key in self.keymap:
                msg_id = self.keymap[key]
                log.info('loaded {0}->{1}'.format(key, msg_id))
                self.keymap.pop(key)

                async def updateMsg(context: ContextTypes.DEFAULT_TYPE):
                    await context.bot.edit_message_text(
                        chat_id=self._target_group_chat,
                        message_id=msg_id,
                        text=outputmsg,
                        disable_web_page_preview=False)
                self._jobqueue.run_once(updateMsg, 0.1)
            else:
                async def basicMsg(context: ContextTypes.DEFAULT_TYPE):
                    await context.bot.send_message(
                        self._target_group_chat, outputmsg)
                self._jobqueue.run_once(basicMsg, 0)

        except Exception as err:
            log.error('Error queueing nagios job: {0}'.format(err))

    async def run(self) -> None:
        # self.connection = await aio_pika.connect_robust(self._amqp_url)
        self.connection = await aio_pika.connect(self._amqp_url)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
                            name=self._exchange,
                            type=self._exchange_type,
                            auto_delete=False)

        # Maximum message count which will be processing at the same time.
        await self.channel.set_qos(prefetch_count=1)
        # Declaring queue
        self.queue = await self.channel.declare_queue(self._queue,
                                                      durable=True,
                                                      auto_delete=False)
        await self.queue.bind(self.exchange, self._routing_key)
        await self.queue.consume(self.process_message)

    async def stop(self) -> None:
        await self.queue.unbind(self.exchange, self._routing_key)
        await self.delete()
        await self.connection.close()


def parse_config(file):
    """ Read the local configuration from the file specified.

    """
    log.debug("parsing config file: {}".format(file))
    config = configparser.ConfigParser()
    config.read(file)
    return config


async def main(file='overlord.conf') -> None:

    kwargs = dict(parse_config(file).items("DEFAULT"))
    # a connection url to rabbit is mandatory
    amqp_url = kwargs["amqp_url"]
    # but dont include in kwargs
    if "amqp_url" in kwargs:
        del kwargs["amqp_url"]
    aioconsumer = AioConsumer(amqp_url, None, **kwargs)
    await aioconsumer.run()
    try:
        # Wait until terminate
        await asyncio.Future()
    finally:
        await aioconsumer.stop()


if __name__ == "__main__":
    LOG_FORMAT = '%(asctime)s %(levelname)-8s %(name)-15s %(message)s'
    logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
    config_file = os.environ.get('OVERLORD_CONFIG_FILE', './overlord.conf')
    try:
        asyncio.run(main(config_file))
    except KeyboardInterrupt:
        pass

# vim: nospell
