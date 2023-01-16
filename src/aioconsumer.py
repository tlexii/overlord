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

    async def process_message(self, message) -> None:
        async with message.process():
            log.debug(message.body)
            # await message.ack()
            if message.routing_key == "bot.message":
                await self.simple_msg(message.body)
            else:
                log.error('Unhandled routing_key: {0}'.format(
                                                message.routing_key))

#            self.acknowledge_message(basic_deliver.delivery_tag)

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

    async def run(self) -> None:
        self.connection = await aio_pika.connect_robust(self._amqp_url)
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
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)
    config_file = os.environ.get('OVERLORD_CONFIG_FILE', './overlord.conf')
    try:
        asyncio.run(main(config_file))
    except KeyboardInterrupt:
        pass

# vim: nospell
