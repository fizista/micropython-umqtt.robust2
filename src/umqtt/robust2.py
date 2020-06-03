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
    # When you reconnect, all existing subscriptions are renewed.
    RESUBSCRIBE = True

    def __init__(self, *args, **kwargs):
        """
        See documentation for `umqtt.simple2.MQTTClient.__init__()`
        """
        super().__init__(*args, **kwargs)
        self.subs = []  # List of stored subscriptions
        self.msg_to_send = []  # Queue with list of messages to send
        self.sub_to_send = []  # Queue with list of subscriptions to send
        self.msg_to_confirm = {}  # Queue with a list of messages waiting for the server to confirm of the message.
        self.sub_to_confirm = {}  # Queue with a subscription list waiting for the server to confirm of the subscription
        self.conn_issue = None  # We store here if there is a connection problem.

    def is_keepalive(self):
        """
        It checks if the connection is active. If the connection is not active at the specified time,
        saves an error message and returns False.

        :return: If the connection is not active at the specified time returns False otherwise True.
        """
        time_from__last_cpackage = ticks_diff(ticks_ms(), self.last_cpacket) // 1000
        if 0 < self.keepalive < time_from__last_cpackage:
            self.conn_issue = (simple2.MQTTException(7), 9)
            return False
        return True

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
                    self.msg_to_send.insert(0, data)
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

    def connect(self, clean_session=True):
        """
        See documentation for `umqtt.simple2.MQTTClient.connect()`.

        If clean_session==True, then the queues are cleared.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        if clean_session:
            self.msg_to_send[:] = []
            self.msg_to_confirm.clear()
        try:
            self.conn_issue = None
            return super().connect(clean_session)
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
                         'reconnect', 'sendqueue', 'disconnect', 'ping', 'wait_msg', 'keepalive', 'check_msg')
            print("MQTT (%s): %r" % (place_str[issue_place], conn_issue))

    def reconnect(self):
        """
        The function tries to resume the connection.

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            self.conn_issue = None
            return super().connect(False)
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 4)
            if self.sock:
                self.sock.close()
                self.sock = None

    def resubscribe(self):
        """
        Function from previously registered subscriptions, sends them again to the server.

        :return:
        """
        for topic, qos in self.subs:
            self.subscribe(topic, qos, False)

    def add_msg_to_send(self, data):
        """
        By overwriting this method, you can control the amount of stored data in the queue.
        This is important because we do not have an infinite amount of memory in the devices.

        Currently, this method limits the queue length to MSG_QUEUE_MAX messages.

        The number of active messages is the sum of messages to be sent with messages awaiting confirmation.

        :param data:
        :return:
        """
        self.msg_to_send.append(data)
        if (len(self.msg_to_send) + len(self.msg_to_confirm)) > self.MSG_QUEUE_MAX:
            self.msg_to_send.pop(0)

    def disconnect(self):
        """
        See documentation for `umqtt.simple2.MQTTClient.disconnect()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        try:
            return super().disconnect()
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 6)

    def ping(self):
        """
        See documentation for `umqtt.simple2.MQTTClient.ping()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        if not self.is_keepalive():
            return
        try:
            return super().ping()
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 7)

    def publish(self, topic, msg, retain=False, qos=0):
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
            self.msg_to_send[:] = [
                m for m in self.msg_to_send if topic != m[0] or retain != m[2]
            ]

        try:
            out = super().publish(topic, msg, retain, qos, False)
            if qos == 1:
                # We postpone the message in case it is not delivered to the server.
                # We will delete it when we receive a receipt.
                self.msg_to_confirm.setdefault(data, []).append(out)
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 2)
            # If the message cannot be sent, we put it in the queue to try to resend it.
            if self.NO_QUEUE_DUPS and data in self.msg_to_send:
                return
            if self.KEEP_QOS0 and qos == 0:
                self.add_msg_to_send(data)
            elif qos == 1:
                self.add_msg_to_send(data)

    def subscribe(self, topic, qos=0, resubscribe=True):
        """
        See documentation for `umqtt.simple2.MQTTClient.subscribe()`

        The function tries to subscribe to the topic. If it fails,
        the topic subscription goes into the subscription queue.

        Connection problems are captured and handled by `is_conn_issue()`

        """
        data = (topic, qos)

        if self.RESUBSCRIBE and resubscribe and topic not in dict(self.subs):
            self.subs.append(data)

        # We delete all previous subscriptions for the same topic from the queue.
        # The most important is the last subscription.
        self.sub_to_send[:] = [s for s in self.sub_to_send if topic != s[0]]
        try:
            out = super().subscribe(topic, qos)
            self.sub_to_confirm.setdefault(data, []).append(out)
            return out
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 3)
            if self.NO_QUEUE_DUPS and data in self.sub_to_send:
                return
            self.sub_to_send.append(data)

    def send_queue(self):
        """
        The function tries to send all messages and subscribe to all topics that are in the queue to send.

        :return: True if the queue's empty.
        :rtype: bool
        """
        msg_to_del = []
        for data in self.msg_to_send:
            topic, msg, retain, qos = data
            try:
                out = super().publish(topic, msg, retain, qos, False)
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
                out = super().subscribe(topic, qos)
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
        `connect()`, `publish()`, `subscribe()`, `reconnect()`, `send_queue()`, `disconnect()`, `ping()`, `wait_msg()`,
        `check_msg()`, `is_keepalive()`.

        The value of the last error is stored in self.conn_issue.

        :return: Connection problem
        :rtype: bool
        """
        self.is_keepalive()

        if self.conn_issue:
            self.log()
        return bool(self.conn_issue)

    def wait_msg(self):
        """
        See documentation for `umqtt.simple2.MQTTClient.wait_msg()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        self.is_keepalive()
        try:
            return super().wait_msg()
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 8)

    def check_msg(self):
        """
        See documentation for `umqtt.simple2.MQTTClient.check_msg()`

        Connection problems are captured and handled by `is_conn_issue()`
        """
        self.is_keepalive()
        try:
            return super().check_msg()
        except (OSError, simple2.MQTTException) as e:
            self.conn_issue = (e, 10)
