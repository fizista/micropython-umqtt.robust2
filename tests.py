import utime
from ubinascii import hexlify
from umqtt.robust2 import MQTTClient as _MQTTClient


def debug_print(data):
    print('HEX: %s STR: /*' % hexlify(data).decode('ascii'), end='')
    for i, d in enumerate(data):
        if type(d) == str:
            d = ord(d)
        if 31 < d < 127:
            print(chr(d), end='')
        else:
            print('.', end='')
    print('*/')


def debug_func_name(f_name):
    print('FUNC: %s' % f_name)


class MQTTClient(_MQTTClient):
    DEBUG = 1
    MAX_DBG_LEN = 80
    MSG_QUEUE_MAX = 3

    def _read(self, n):
        out = super()._read(n)
        if type(out) == bytes:
            print(' R(%3d) - ' % len(out), end='')
            debug_print(out[:self.MAX_DBG_LEN])
        else:
            print(' R(---) - %s' % out)
        return out

    def _write(self, bytes_wr, *args, **kwargs):
        print(' W(%3d,%3s) - ' % (len(bytes_wr), args[0] if args else '---'), end='')
        debug_print(bytes_wr[:self.MAX_DBG_LEN])
        return super()._write(bytes_wr, *args, **kwargs)

    def connect(self, *a, **k):
        debug_func_name('connect')
        return super().connect(*a, **k)

    def disconnect(self, *a, **k):
        debug_func_name('disconnect')
        return super().disconnect(*a, **k)

    def ping(self, *a, **k):
        debug_func_name('ping')
        return super().ping(*a, **k)

    def publish(self, *a, **k):
        debug_func_name('publish')
        return super().publish(*a, **k)

    def subscribe(self, *a, **k):
        debug_func_name('subscribe')
        return super().subscribe(*a, **k)

    def wait_msg(self, *a, **k):
        debug_func_name('wait_msg')
        return super().wait_msg(*a, **k)

    def send_queue(self, *a, **k):
        debug_func_name('send_queue')
        out = super().send_queue(*a, **k)
        self.is_conn_issue()
        return out

    def connect(self, *a, **k):
        debug_func_name('connect')
        out = super().connect(*a, **k)
        self.is_conn_issue()
        return out

    def reconnect(self, *a, **k):
        debug_func_name('reconnect')
        out = super().reconnect(*a, **k)
        self.is_conn_issue()
        return out


class TestMQTT:
    def __init__(self, *args, **kwargs):
        self.mqtt_client_args = (args, kwargs)
        self.msg_id = args[0]
        self.subsctiption_out = {}
        self.status_out = {}
        self.clients = {}
        self.client = None

    def init_mqtt_client(self, clientid_postfix='_1', mqtt_kwargs=None):
        args = list(self.mqtt_client_args[0][:])
        kwargs = self.mqtt_client_args[1].copy()
        if mqtt_kwargs:
            kwargs.update(mqtt_kwargs)
        if len(args) > 0:
            args[0] += clientid_postfix
        if 'client_id' in kwargs:
            kwargs['client_id'] += clientid_postfix
        print('MQTT connection args:', args, kwargs)
        client = MQTTClient(*args, **kwargs)
        client.set_callback(self.sub_cb_gen(clientid_postfix))
        client.set_callback_status(self.stat_cb_gen(clientid_postfix))
        self.subsctiption_out[clientid_postfix] = None
        self.status_out[clientid_postfix] = None
        self.clients[clientid_postfix] = client
        return client

    def sub_cb_gen(self, clientid_postfix='_1'):
        def sub_cb(topic, msg, retained, dup):
            print('TOPIC: %s MSG: %s R: %s D: %s' % (topic, msg, retained, dup))
            self.subsctiption_out[clientid_postfix] = (topic, msg, retained)

        return sub_cb

    def stat_cb_gen(self, clientid_postfix='_1'):
        def stat_cb(pid, status):
            print('PID: %s STATUS: %d' % (pid, status))
            self.status_out[clientid_postfix] = (pid, status)

        return stat_cb

    def get_subscription_out(self, timeout=5, clientid_postfix='_1'):
        print('WAIT SUB: timeout=%d' % (timeout,))
        client = self.clients[clientid_postfix]
        for i in range(timeout):
            client.check_msg()
            if clientid_postfix in self.subsctiption_out and self.subsctiption_out[clientid_postfix] is not None:
                o = self.subsctiption_out[clientid_postfix]
                self.subsctiption_out[clientid_postfix] = None
                return o
            utime.sleep(1)
        raise Exception('timeout')

    def get_status_out(self, timeout=5, pid=None, clientid_postfix='_1'):
        print('WAIT STAT: timeout=%d pid=%s' % (timeout, pid))
        client = self.clients[clientid_postfix]
        for i in range(timeout + 1):
            utime.sleep(1)
            client.check_msg()
            if clientid_postfix in self.status_out and self.status_out[clientid_postfix] is not None:
                o = self.status_out[clientid_postfix]
                self.status_out[clientid_postfix] = None
                if pid:
                    if pid != o[0]:
                        continue
                return o
        raise Exception('timeout')

    def disable_net(self):
        raise RuntimeError('Not implemented method')

    def enable_net(self):
        raise RuntimeError('Not implemented method')

    def get_topic(self, test_name):
        return '%s/umqtt.robust2/%s/' % (self.msg_id, test_name)

    def run(self):
        test_fails = []
        tests = [
            'test_publish_qos_0',
            'test_publish_qos_1',
            'test_subscribe',
            'test_keepalive',
            'test_queue_max'
        ]
        for test_name in tests:
            if not self.run_test(test_name):
                test_fails.append(test_name)
        if test_fails:
            print('\nTests fails: %s\n' % ', '.join(test_fails))
        else:
            print('All the tests were finished successfully!')

    def run_test(self, test_name):
        try:
            if self.client:
                self.client.disconnect()
        except:
            pass
        self.client = self.init_mqtt_client()
        self.subsctiption_out = {}
        self.status_out = {}
        test = getattr(self, test_name)
        print('RUN [%s]' % test_name)
        test_pass = True
        self.enable_net()
        try:
            test(self.get_topic(test_name))
        except Exception as e:
            from sys import print_exception
            print_exception(e)
            test_pass = False
        print('END [%s] %s\n' % (test_name, 'succes' if test_pass else 'FAIL'))
        return test_pass

    def test_publish_qos_0(self, topic):
        self.client.connect()

        self.client.sock.close()
        self.client.publish(topic, 'test QoS 0')
        if self.client.is_conn_issue():
            self.client.reconnect()
        self.client.check_msg()
        self.client.subscribe(topic + '#')

        assert self.client.send_queue()
        t, m, r = self.get_subscription_out()
        assert t.decode('ascii') == topic
        assert m.decode('ascii') == 'test QoS 0'

        self.client.disconnect()

    def test_publish_qos_1(self, topic):
        self.client.connect()

        self.client.sock.close()
        pid = self.client.publish(topic, 'test QoS 1', qos=1)
        assert pid is None

        print('msg_to_:', self.client.msg_to_send, self.client.msg_to_confirm, self.client.rcv_pids)
        assert self.client.msg_to_send == [(topic, 'test QoS 1', False, 1)]
        assert self.client.msg_to_confirm == {}

        if self.client.is_conn_issue():
            self.client.reconnect()

        assert self.client.send_queue()
        print('msg_to_:', self.client.msg_to_send, self.client.msg_to_confirm, self.client.rcv_pids)
        pid = list(self.client.rcv_pids.keys())[0]
        assert self.client.msg_to_send == []
        assert self.client.msg_to_confirm == {(topic, 'test QoS 1', False, 1): [pid]}

        self.client.check_msg()  # get a confirmation
        out_pid, status = self.get_status_out(pid=pid)
        assert status == 1

        print('msg_to_:', self.client.msg_to_send, self.client.msg_to_confirm, self.client.rcv_pids)
        assert self.client.msg_to_send == []
        assert self.client.msg_to_confirm == {}

        self.client.disconnect()

    def test_subscribe(self, topic):
        self.client.connect()

        self.client.sock.close()
        pid = self.client.subscribe(topic + '#')
        assert pid is None

        print(self.client.sub_to_send, self.client.sub_to_confirm, self.client.rcv_pids, 2)
        assert self.client.sub_to_send == [(topic + '#', 0)]
        assert self.client.sub_to_confirm == {}

        if self.client.is_conn_issue():
            self.client.reconnect()

        print(self.client.sub_to_send, self.client.sub_to_confirm, self.client.rcv_pids, 3)
        assert self.client.sub_to_send == [(topic + '#', 0)]
        assert self.client.sub_to_confirm == {}

        assert self.client.send_queue()  # resubscribe

        print(self.client.sub_to_send, self.client.sub_to_confirm, self.client.rcv_pids, 4)
        pid = list(self.client.rcv_pids.keys())[0]
        assert self.client.sub_to_send == []
        assert self.client.sub_to_confirm == {(topic + '#', 0): [pid]}

        out_pid, status = self.get_status_out(pid=pid)

        print(self.client.sub_to_send, self.client.sub_to_confirm, self.client.rcv_pids, 5)
        assert status == 1
        assert self.client.sub_to_send == []
        assert self.client.sub_to_confirm == {}

        self.client.disconnect()

    def test_keepalive(self, topic):
        c = self.init_mqtt_client(mqtt_kwargs={'keepalive': 3})
        c.connect()  # 3 sec
        assert not c.is_conn_issue()
        utime.sleep(2)
        c.ping()  # 3 sec
        utime.sleep(1)
        c.check_msg()
        assert not c.is_conn_issue()
        utime.sleep(1)
        assert not c.is_conn_issue()
        utime.sleep(3)
        assert c.is_conn_issue()
        c.disconnect()

    def test_queue_max(self, topic):
        c = self.init_mqtt_client()
        c.add_msg_to_send((1, 'x', 'y'))
        c.add_msg_to_send((2, 'x', 'y'))
        c.add_msg_to_send((3, 'x', 'y'))
        c.add_msg_to_send((4, 'x', 'y'))
        print(c.msg_to_send)
        assert len(c.msg_to_send) == 3
        assert c.msg_to_send[-1] == (4, 'x', 'y')
