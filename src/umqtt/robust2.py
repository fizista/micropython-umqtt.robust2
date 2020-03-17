from utime import ticks_ms, ticks_diff
from . import simple2


class MQTTClient(simple2.MQTTClient):
    DEBUG = False

    # Information whether we store unsent messages with the flag QoS==0 in the queue.
    KEEP_QOS0 = True
    # Option, limits the possibility of only one unique message being queued.
    NO_QUEUE_DUPS = True
    # Limit the number of unsent messages in the queue.
    MSG_QUEUE_MAX = 5

    def __init__(self, *args, **kwargs):
        """
        See documentation for `umqtt.simple2.MQTTClient.__init__()`
        """
        super().__init__(*args, **kwargs)
        self.msg_to_send = []  # Queue with list of messages to send
        self.sub_to_send = []  # Queue with list of subscriptions to send
        self.msg_to_confirm = {}  # Queue with a list of messages waiting for the server to confirm of the message.
        self.sub_to_confirm = {}  # Queue with a subscription list waiting for the server to confirm of the subscription
        self.conn_issue = None  # We store here if there is a connection problem.

    def set_callback_status(self, f):
        """
        See documentation for `umqtt.simple2.MQTTClient.set_callback_status()`
        """
        self._cbstat = f

    def cbstat(self, pid, stat):
        """
        Captured message statuses affect the queue here.

        stat == 0 - the message goes back to the message queue to be sent
        stat == 1 or 2 - the message is removed from the queue
        """
        try:
            self._cbstat(pid, stat)
        except AttributeError:
            pass

        for data, pids in self.msg_to_confirm.items():
            if pid in pids:
                if stat == 0:
                    self.msg_to_send.append(data)
                pids.remove(pid)
                if not pids:
                    self.msg_to_confirm.pop(data)
                return

        for data, pids in self.sub_to_confirm.items():
            if pid in pids:
                if stat == 0:
                    self.sub_to_send.append(data)
                pids.remove(pid)
                if not pids:
                    self.sub_to_confirm.pop(data)

    def connect(self, clean_session=True, socket_timeout=-1):
        """
        See documentation for `umqtt.simple2.MQTTClient.connect()`.

        If clean_session==True, then the queues are cleared.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        if clean_session:
            self.msg_to_send[:] = []
            self.msg_to_confirm.clear()
        try:
            out = super().connect(clean_session, socket_timeout)
            self.conn_issue = None
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 1)

    def log(self):
        if self.DEBUG:
            if type(self.conn_issue) is tuple:
                conn_issue, issue_place = self.conn_issue
            else:
                conn_issue = self.conn_issue
                issue_place = 0
            place_str = ('?', 'connect', 'publish', 'subscribe',
                         'reconnect', 'sendqueue', 'disconnect', 'ping', 'wait_msg', 'keepalive')
            print("MQTT (%s): %r" % (place_str[issue_place], conn_issue))

    def reconnect(self, socket_timeout=-1):
        """
        The function tries to resume the connection.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            out = super().connect(False, socket_timeout=socket_timeout)
            self.conn_issue = None
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 4)
            if self.sock:
                self.sock.close()
                self.sock = None

    def add_msg_to_send(self, data):
        """
        By overwriting this method, you can control the amount of stored data in the queue.
        This is important because we do not have an infinite amount of memory in the devices.

        Currently, this method limits the queue length to MSG_QUEUE_MAX messages.

        :param data:
        :return:
        """
        self.msg_to_send.append(data)
        if len(self.msg_to_send) > self.MSG_QUEUE_MAX:
            self.msg_to_send.pop(0)

    def disconnect(self, socket_timeout=-1):
        """
        See documentation for `umqtt.simple2.MQTTClient.disconnect()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            return super().disconnect(socket_timeout=socket_timeout)
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 6)

    def ping(self, socket_timeout=-1):
        """
        See documentation for `umqtt.simple2.MQTTClient.ping()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            return super().ping(socket_timeout=socket_timeout)
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 7)

    def publish(self, topic, msg, retain=False, qos=0, socket_timeout=-1):
        """
        See documentation for `umqtt.simple2.MQTTClient.publish()`

        The function tries to send a message. If it fails, the message goes to the message queue for sending.

        The function does not support the `dup` parameter!

        When we have messages with the retain flag set, only one last message with that flag is sent!

        Connection problems are captured and handled by `is_conn_issue()`

        :return: None od PID for QoS==1 (only if the message is sent immediately, otherwise it returns None)
        """
        data = (topic, msg, retain, qos)
        if retain:
            # We delete all previous messages for this topic with the retain flag set to True.
            # Only the last message with this flag is relevant.
            self.msg_to_send[:] = [m for m in self.msg_to_send if not (topic == m[0] and retain == m[2])]
        try:
            out = super().publish(topic, msg, retain, qos, False, socket_timeout)
            if qos == 1:
                # We postpone the message in case it is not delivered to the server.
                # We will delete it when we receive a receipt.
                self.msg_to_confirm.setdefault(data, []).append(out)
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 2)
            # If the message cannot be sent, we put it in the queue to try to resend it.
            if self.NO_QUEUE_DUPS:
                if data in self.msg_to_send:
                    return
            if self.KEEP_QOS0 and qos == 0:
                self.msg_to_send.append(data)
            elif qos == 1:
                self.msg_to_send.append(data)

    def subscribe(self, topic, qos=0, socket_timeout=-1):
        """
        See documentation for `umqtt.simple2.MQTTClient.subscribe()`

        The function tries to subscribe to the topic. If it fails,
        the topic subscription goes into the subscription queue.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        data = (topic, qos)
        # We delete all previous subscriptions for the same topic from the queue.
        # The most important is the last subscription.
        self.sub_to_send[:] = [s for s in self.sub_to_send if topic != s[0]]
        try:
            out = super().subscribe(topic, qos, socket_timeout)
            self.sub_to_confirm.setdefault(data, []).append(out)
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 3)
            if self.NO_QUEUE_DUPS:
                if data in self.sub_to_send:
                    return
            self.sub_to_send.append(data)

    def send_queue(self, socket_timeout=-1):
        """
        The function tries to send all messages and subscribe to all topics that are in the queue to send.

        :return: True if the queue's empty.
        :rtype: bool
        """
        msg_to_del = []
        for data in self.msg_to_send:
            topic, msg, retain, qos = data
            try:
                out = super().publish(topic, msg, retain, qos, False, socket_timeout)
                if qos == 1:
                    # We postpone the message in case it is not delivered to the server.
                    # We will delete it when we receive a receipt.
                    self.msg_to_confirm.setdefault(data, []).append(out)
                msg_to_del.append(data)
            except (OSError, simple2.MQTTException) as e:
                self.conn_issue = (e, 5)
                return False
        self.msg_to_send[:] = [m for m in self.msg_to_send if m not in msg_to_del]
        del msg_to_del

        sub_to_del = []
        for data in self.sub_to_send:
            topic, qos = data
            try:
                out = super().subscribe(topic, qos, socket_timeout)
                self.sub_to_confirm.setdefault(data, []).append(out)
                sub_to_del.append(data)
            except (OSError, simple2.MQTTException) as e:
                self.conn_issue = (e, 5)
                return False
        self.sub_to_send[:] = [s for s in self.sub_to_send if s not in sub_to_del]

        return True

    def is_conn_issue(self):
        """
        With this function we can check if there is any connection problem.

        It is best to use this function with the reconnect() method to resume the connection when it is broken.

        You can also check the result of methods such as this:
        `connect()`, `publish()`, `subscribe()`, `reconnect()`, `send_queue()`, `disconnect()`, `amping()`.

        :return: Connection problem
        :rtype: bool
        """
        time_from__last_cpackage = ticks_diff(ticks_ms(), self.last_cpacket) // 1000

        if 0 < self.keepalive < time_from__last_cpackage:
            self.conn_issue = (simple2.MQTTException(7), 9)

        if self.conn_issue:
            self.log()
        return bool(self.conn_issue)

    def wait_msg(self, socket_timeout=None):
        """
        See documentation for `umqtt.simple2.MQTTClient.wait_msg()`

        The function tries to subscribe to the topic. If it fails,
        the topic subscription goes into the subscription queue.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            return super().wait_msg(socket_timeout)
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 8)
