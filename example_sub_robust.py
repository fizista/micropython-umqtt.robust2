import utime
from umqtt.robust2 import MQTTClient


def sub_cb(topic, msg, retained, duplicate):
    print((topic, msg, retained, duplicate))


c = MQTTClient("umqtt_client", "localhost")
# Print diagnostic messages when retries/reconnects happens
c.DEBUG = True
# Information whether we store unsent messages with the flag QoS==0 in the queue.
c.KEEP_QOS0 = False
# Option, limits the possibility of only one unique message being queued.
c.NO_QUEUE_DUPS = True
# Limit the number of unsent messages in the queue.
c.MSG_QUEUE_MAX = 2

c.set_callback(sub_cb)
# Connect to server, requesting not to clean session for this
# client. If there was no existing session (False return value
# from connect() method), we perform the initial setup of client
# session - subscribe to needed topics. Afterwards, these
# subscriptions will be stored server-side, and will be persistent,
# (as we use clean_session=False).
#
# TODO: Still exists???
# There can be a problem when a session for a given client exists,
# but doesn't have subscriptions a particular application expects.
# In this case, a session needs to be cleaned first. See
# example_reset_session.py for an obvious way how to do that.
#
# In an actual application, it's up to its developer how to
# manage these issues. One extreme is to have external "provisioning"
# phase, where initial session setup, and any further management of
# a session, is done by external tools. This allows to save resources
# on a small embedded device. Another extreme is to have an application
# to perform auto-setup (e.g., clean session, then re-create session
# on each restart). This example shows mid-line between these 2
# approaches, where initial setup of session is done by application,
# but if anything goes wrong, there's an external tool to clean session.
if not c.connect(clean_session=False):
    print("New session being set up")
    c.subscribe(b"foo_topic")

while 1:
    utime.sleep_ms(500)

    # At this point in the code you must consider how to handle
    # connection errors.  And how often to resume the connection.
    if c.is_conn_issue():
        while c.is_conn_issue():
            # If the connection is successful, the is_conn_issue
            # method will not return a connection error.
            c.reconnect()
        else:
            c.resubscribe()

    c.publish('/hello/topic', 'online', qos=1)

    c.check_msg() # needed when publish(qos=1), ping(), subscribe()
    c.send_queue()  # needed when using the caching capabilities for unsent messages

c.disconnect()
