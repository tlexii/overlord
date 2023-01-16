# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205

from consumer import TelegramConsumer
import logging
import time

log = logging.getLogger("ReconnectingTelegramConsumer")


class ReconnectingTelegramConsumer(object):
    """This is a consumer that will reconnect if the nested
    TelegramConsumer indicates that a reconnect is necessary.

    """

    def __init__(self, amqp_url, jobqueue, **kwargs):
        self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._jobqueue = jobqueue
        self._kwargs = kwargs
        self._consumer = TelegramConsumer(self._amqp_url, self._jobqueue,
                                          **self._kwargs)

    def run(self):
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            logging.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = TelegramConsumer(self._amqp_url, self._jobqueue,
                                              **self._kwargs)

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay

    def stop(self):
        self._consumer.stop()


def main():
    LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) -35s %(lineno) -5d: %(message)s')
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
    amqp_url = 'amqp://guest:guest@localhost:5672/%2F'
    consumer = ReconnectingTelegramConsumer(amqp_url)
    consumer.run()


if __name__ == '__main__':
    main()
