import asyncio
import aio_pika
import logging, traceback
import os, subprocess
import configparser
from telegram.ext import ContextTypes
from pymemcache.client.base import Client

log = logging.getLogger("overlord")
log.setLevel(logging.DEBUG)

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
        self.cache = Client('memcache')

    async def process_message(self, message) -> None:
        async with message.process():
            # log.debug(message.body)
            if message.routing_key == "bot.message":
                await self.simple_msg(message.body)
            elif message.routing_key == "bot.motion_eventstart":
                await self.motion_event(message.body)
            elif message.routing_key == "bot.motion_areadetect":
                await self.motion_area(message.body)
            elif message.routing_key == "bot.motion_picturesaved":
                await self.motion_picture(message.body)
            elif message.routing_key == "bot.motion_moviecomplete":
                await self.motion_movie(message.body)
            else:
                log.error('Unhandled routing_key: {0}'.format(message.routing_key))

            # TODO
            # await message.ack()

    async def simple_msg(self, body) -> None:
        """Handle simple messages with key bot.send_message.

        :param str|unicode body: The message body

        """

        try:
            # handle the message by queueing a job in telegram bot
            async def basicMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.send_message(self._target_group_chat, text=bytes.decode(body))

            self._jobqueue.run_once(basicMsg, 0.001)

        except Exception as err:
            log.error(f'Error queueing simple job: {err}')


    async def motion_event(self, body):
        """Display an incoming motion area placeholder, remember key.

        :param str|unicode body: contains the event_id

        """

        try:
            # read the event_id
            event_id = bytes.decode(body)
            key = self.cache.get(event_id, None)
            if key is None:
                log.warning(f'event start - cache miss: {event_id}')
                return

            if key != '0':
                log.debug(f"event start - key already set {event_id}={key}")

            # placeholder message
            outputmsg = 'Event started ...'
            log.info(f"motion event start: {event_id}")

            async def eventMsg(context: ContextTypes.DEFAULT_TYPE):
                my_msg = await context.bot.send_message(self._target_group_chat, disable_notification=True,
                        text=outputmsg)

                # store mapping from event_id to message_id
                key = str(context.job.data)
                log.info('saving {0}->{1}'.format(key + ':id', my_msg.message_id))
                self.cache.add(key + ':id', my_msg.message_id, 86400)

            self._jobqueue.run_once(eventMsg, 0.001, data=event_id)

        except Exception as err:
            log.error(f'Error queueing motion job: {err}')


    async def motion_area(self, body):
        """Notify the user.

        :param str|unicode body: contains the event_id

        """

        try:
            # read the key e.g. '2022-03-06_082218'
            event_id = bytes.decode(body)
            log.info(f'area detect for event_id: {event_id}')

            outputmsg = f'Proximity alert for {event_id}'
            async def areaMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.send_message(self._target_group_chat, text=outputmsg)

            self._jobqueue.run_once(areaMsg, 0.001)

        except Exception as err:
            log.error(f'Error queueing motion job: {err}')


    async def motion_picture(self, body):
        """Notify the user.

        :param str|unicode body: contains the event_id

        """
        try:
            event_id = bytes.decode(body)
            event = self.cache.get(event_id, None)
            msg_id = self.cache.get(event_id + ':id', None)
            if msg_id is None:
                log.info(f'picture saved - invalid cache for: {event_id}')
                return

            # update placeholder message
            event = event.decode()
            msg_id = msg_id.decode()
            outputmsg = f'https://overworld.net.au/motion2/preview.php?k={event}'
            log.info(f'picture saved for event_id: {event_id}')

            async def pictureMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.edit_message_text( chat_id=self._target_group_chat, message_id=msg_id, text=outputmsg)

            self._jobqueue.run_once(pictureMsg, 0.001)

        except Exception as err:
            log.error(f'Error queueing motion job: {err}')


    async def motion_movie(self, body):
        """Update an existing motion area placeholder with an URL.

        :param str|unicode body: The message body

        """

        try:
            event_id = bytes.decode(body)
            event = self.cache.get(event_id, None)
            msg_id = self.cache.get(event_id + ':id', None)
            filename = self.cache.get(event_id + ':filename', None)
            if msg_id is None or filename is None:
                log.info(f'movie end - invalid cache for: {event_id}')
                return

            event = event.decode()
            msg_id = msg_id.decode()
            filename = filename.decode()

            outputmsg = f'Processing https://overworld.net.au/motion2/preview.php?k={event}'
            async def updateProcessMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.edit_message_text(chat_id=self._target_group_chat, message_id=msg_id, text=outputmsg)

            self._jobqueue.run_once(updateProcessMsg, 0.2)

            target = filename.replace('mp4', 'webm')
            log.info(f'movie end {event_id} - calling ffmpeg: {filename}->{target}')
            process = await asyncio.create_subprocess_exec("ffmpeg","-v", "quiet","-i", filename, "-c:v", "libvpx-vp9", "-crf", "35", "-b:v", "2000k", "-an", target)
            rc = await process.wait()

            outputmsg = f'https://overworld.net.au/motion2/event.php?k={event}'
            async def updateMovieMsg(context: ContextTypes.DEFAULT_TYPE):
                await context.bot.edit_message_text(chat_id=self._target_group_chat, message_id=msg_id, text=outputmsg)

            self._jobqueue.run_once(updateMovieMsg, 0.2)

            log.info(f'movie end {event_id} - removing: {filename}')
            os.remove(filename)

        except Exception as err:
            log.error(f'Error queueing motion job: {err}')
            log.error(traceback.format_exc())


    async def run(self) -> None:
        # self.connection = await aio_pika.connect_robust(self._amqp_url)
        self.connection = await aio_pika.connect(self._amqp_url)
        self.channel = await self.connection.channel()
        self.exchange = await self.channel.declare_exchange(
                            name=self._exchange,
                            type=self._exchange_type,
                            auto_delete=False)

        # Maximum message count which will be processing at the same time.
        await self.channel.set_qos(prefetch_count=2)
        # Declaring queue
        self.queue = await self.channel.declare_queue(self._queue, durable=True, auto_delete=False)
        await self.queue.bind(self.exchange, self._routing_key)
        await self.queue.consume(self.process_message)

    async def stop(self) -> None:
        await self.queue.unbind(self.exchange, self._routing_key)
        await self.delete()
        await self.connection.close()


def parse_config(file):
    """ Read the local configuration from the file specified.

    """
    log.debug(f"parsing config file: {file}")
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
