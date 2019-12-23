from utime import ticks_ms,ticks_diff
from .  import simple2
class MQTTClient(simple2.MQTTClient):
	DEBUG=False;KEEP_QOS0=True;NO_QUEUE_DUPS=True;MSG_QUEUE_MAX=5
	def __init__(A,*B,**C):super().__init__(*B,**C);A.msg_to_send=[];A.sub_to_send=[];A.msg_to_confirm={};A.sub_to_confirm={};A.conn_issue=None
	def set_callback_status(A,f):A._cbstat=f
	def cbstat(A,pid,stat):
		E=stat;C=pid
		try:A._cbstat(C,E)
		except AttributeError:pass
		for (D,B) in A.msg_to_confirm.items():
			if C in B:
				if E==0:A.msg_to_send.append(D)
				B.remove(C)
				if not B:A.msg_to_confirm.pop(D)
				return
		for (D,B) in A.sub_to_confirm.items():
			if C in B:
				if E==0:A.sub_to_send.append(D)
				B.remove(C)
				if not B:A.sub_to_confirm.pop(D)
	def connect(A,clean_session=True,socket_timeout=-1):
		B=clean_session
		if B:A.msg_to_send[:]=[];A.msg_to_confirm.clear()
		try:C=super().connect(B,socket_timeout);A.conn_issue=None;return C
		except (OSError,simple2.MQTTException)as D:A.conn_issue=D,1
	def log(A):
		if A.DEBUG:
			if type(A.conn_issue)is tuple:B,C=A.conn_issue
			else:B=A.conn_issue;C=0
			D='?','connect','publish','subscribe','reconnect','sendqueue','disconnect','ping','wait_msg','keepalive';print('MQTT (%s): %r'%(D[C],B))
	def reconnect(A,socket_timeout=-1):
		try:B=super().connect(False,socket_timeout=socket_timeout);A.conn_issue=None;return B
		except (OSError,simple2.MQTTException)as C:A.conn_issue=C,4
	def add_msg_to_send(A,data):
		A.msg_to_send.append(data)
		if len(A.msg_to_send)>A.MSG_QUEUE_MAX:A.msg_to_send.pop(0)
	def disconnect(A,socket_timeout=-1):
		try:return super().disconnect(socket_timeout=socket_timeout)
		except (OSError,simple2.MQTTException)as B:A.conn_issue=B,6
	def ping(A,socket_timeout=-1):
		try:return super().ping(socket_timeout=socket_timeout)
		except (OSError,simple2.MQTTException)as B:A.conn_issue=B,7
	def publish(A,topic,msg,retain=False,qos=0,socket_timeout=-1):
		E=topic;C=retain;B=qos;D=E,msg,C,B
		if C:A.msg_to_send[:]=[B for B in A.msg_to_send if not(E==B[0]and C==B[2])]
		try:
			F=super().publish(E,msg,C,B,False,socket_timeout)
			if B==1:A.msg_to_confirm.setdefault(D,[]).append(F)
			return F
		except (OSError,simple2.MQTTException)as G:
			A.conn_issue=G,2
			if A.NO_QUEUE_DUPS:
				if D in A.msg_to_send:return
			if A.KEEP_QOS0 and B==0:A.msg_to_send.append(D)
			elif B==1:A.msg_to_send.append(D)
	def subscribe(A,topic,qos=0,socket_timeout=-1):
		B=topic;C=B,qos;A.sub_to_send[:]=[C for C in A.sub_to_send if B!=C[0]]
		try:D=super().subscribe(B,qos,socket_timeout);A.sub_to_confirm.setdefault(C,[]).append(D);return D
		except (OSError,simple2.MQTTException)as E:
			A.conn_issue=E,3
			if A.NO_QUEUE_DUPS:
				if C in A.sub_to_send:return
			A.sub_to_send.append(C)
	def send_queue(A,socket_timeout=-1):
		H=socket_timeout;D=[]
		for B in A.msg_to_send:
			E,J,K,C=B
			try:
				F=super().publish(E,J,K,C,False,H)
				if C==1:A.msg_to_confirm.setdefault(B,[]).append(F)
				D.append(B)
			except (OSError,simple2.MQTTException)as G:A.conn_issue=G,5;return False
		A.msg_to_send[:]=[B for B in A.msg_to_send if B not in D];del D;I=[]
		for B in A.sub_to_send:
			E,C=B
			try:F=super().subscribe(E,C,H);A.sub_to_confirm.setdefault(B,[]).append(F);I.append(B)
			except (OSError,simple2.MQTTException)as G:A.conn_issue=G,5;return False
		A.sub_to_send[:]=[B for B in A.sub_to_send if B not in I];return True
	def is_conn_issue(A):
		B=ticks_diff(ticks_ms(),A.last_cpacket)//1000
		if 0<A.keepalive<B:A.conn_issue=simple2.MQTTException(7),9
		if A.conn_issue:A.log()
		return bool(A.conn_issue)
	def wait_msg(A,socket_timeout=None):
		try:return super().wait_msg(socket_timeout)
		except (OSError,simple2.MQTTException)as B:A.conn_issue=B,8