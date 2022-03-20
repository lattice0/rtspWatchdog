#!/usr/bin/python
#-*- coding: UTF-8 -*-
# Date: 2015-04-09
#
# Original project here: https://github.com/js2854/python-rtsp-client
# Some text google-translated from Chinese
# A bit adopted to be import'able
# -jno
#
# Date: 2017-05-30
# Ported to Python3, removed GoodThread
# -killian441

import ast, datetime, re, socket, threading, time, traceback
from hashlib import md5
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse # for python < 3.0

TRANSPORT_TYPE_MAP  = {
            'ts_over_tcp'  : 'MP2T/TCP;%s;interleaved=0-1, ',
            'rtp_over_tcp' : 'MP2T/RTP/TCP;%s;interleaved=0-1, ',
            'rtp_avp_tcp'  : 'RTP/AVP/TCP;%s;interleaved=0-1 ',
            'ts_over_udp'  : 'MP2T/UDP;%s;destination=%s;client_port=%s, ',
            'rtp_over_udp' : 'MP2T/RTP/UDP;%s;destination=%s;client_port=%s, ',
            }

RTSP_VERSION        = 'RTSP/1.0'
DEFAULT_USERAGENT   = 'Python Rtsp Client 1.0'
DEFAULT_SERVER_PORT = 554
END_OF_LINE         = '\r\n'
HEADER_END_STR      = END_OF_LINE*2

#x-notice in ANNOUNCE, BOS-Begin of Stream, EOS-End of Stream
X_NOTICE_EOS, X_NOTICE_BOS, X_NOTICE_CLOSE = 2101, 2102, 2103

class RTSPError(Exception): pass
class RTSPURLError(RTSPError): pass
class RTSPNetError(RTSPError): pass

class RTSPClient(threading.Thread):
    TRANSPORT_TYPE_LIST = []
    NAT_IP_PORT         = ''
    ENABLE_ARQ          = False
    ENABLE_FEC          = False
    HEARTBEAT_INTERVAL  = 10 # 10s
    CLIENT_PORT_RANGE   = '10014-10015'

    def __init__(self, url, dest_ip='', callback=None, socks=None, choose_transport=None):
        threading.Thread.__init__(self)
        self._auth        = None
        self._callback    = callback or (lambda x: x)
        self._cseq        = 0
        self._cseq_map    = {} # {CSeq:Method} mapping
        self._dest_ip     = dest_ip
        self._parsed_url  = self._parse_url(url)
        self._server_port = self._parsed_url.port or DEFAULT_SERVER_PORT
        self._orig_url    = self._parsed_url.scheme + "://" + \
                            self._parsed_url.hostname + \
                            ":" + str(self._server_port) + \
                            self._parsed_url.path
        self._session_id  = ''
        self._sock        = None
        self._socks        = socks
        self.cur_range    = 'npt=end-'
        self.cur_scale    = 1
        self.location     = ''
        self.response     = None
        self.response_buf = []
        self.running      = True
        self.state        = None
        self.choose_transport = choose_transport
        self.track_id_lst = []
        if '.sdp' not in self._parsed_url.path.lower():
            self.cur_range = 'npt=0.00000-' # On demand starts from the beginning
        self._connect_server()
        self._update_dest_ip()
        self.closed = False
        self.start()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def flush(self):
        while self.response_buf:
            x = self.response_buf.pop()
            del x

    def set_cache(self, s):
        self.flush()
        self.response_buf.append(s)

    def cache(self, s=None):
        if s is None:
            return ''.join(self.response_buf)
        else:
            self.response_buf.append(s)

    def close(self):
        if not self.closed:
            self.closed  = True
            self.running = False
            self.state   = 'closed'
            self._sock.close()

    def run(self):
        try:
            while self.running:
                self.response = msg = self.recv_msg()
                if msg.startswith('RTSP'):
                    self._process_response(msg)
                elif msg.startswith('ANNOUNCE'):
                    self._process_announce(msg)
        except Exception as e:
            raise RTSPError('Run time error: %s' % e)
        self.running = False
        self.close()

    def _parse_url(self, url):
        '''Resolve url, return the urlparse object'''
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        ip = parsed.hostname
        port = parsed.port and int(parsed.port) or DEFAULT_SERVER_PORT
        target = parsed.path
        if parsed.query:
            target += '?' + parsed.query
        if parsed.fragment:
            target += '#' + parsed.fragment

        if not scheme:
            raise RTSPURLError('Bad URL "%s"' % url)
        if scheme not in ('rtsp',): # 'rtspu'):
            raise RTSPURLError('Unsupported scheme "%s" \
                                in URL "%s"' % (scheme, url))
        if not ip or not target:
            raise RTSPURLError('Invalid url: %s (host="%s" \
                                port=%u target="%s")' %
                                (url, ip, port, target))
        return parsed

    def _connect_server(self):
        '''Connect to the server and create a socket'''
        try:
            self._sock = self._socks or socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.connect((self._parsed_url.hostname, self._server_port))
        except socket.error as e:
            raise RTSPNetError('socket error: %s [%s:%d]' % 
                            (e, self._parsed_url.hostname, self._server_port))

    def _update_content_base(self, msg):
        m = re.search(r'[Cc]ontent-[Bb]ase:\s?(?P<base>[a-zA-Z0-9_:\/\.]+)', msg)
        if (m and m.group('base')):
            new_url = m.group('base')
            if new_url[-1] == '/':
                new_url = new_url[:-1]
            self._orig_url = new_url

    def _update_dest_ip(self):
        '''If DEST_IP is not specified, 
           by default the same IP is used as this RTSP client'''
        if not self._dest_ip:
            self._dest_ip = self._sock.getsockname()[0]
            #self._callback('DEST_IP: %s\n' % self._dest_ip)

    def recv_msg(self):
        '''A complete response message or 
           an ANNOUNCE notification message is received'''
        try:
            while not (not self.running or HEADER_END_STR in self.cache()):
                more = self._sock.recv(2048)
                if not more:
                    break
                self.cache(more.decode())
        except socket.error as e:
            RTSPNetError('Receive data error: %s' % e)

        msg = ''
        if self.cache():
            tmp = self.cache()
            try:
            	(msg, tmp) = tmp.split(HEADER_END_STR, 1)
            except ValueError as e:
            	self._callback(self._get_time_str() + '\n' + tmp)
            	raise RTSPError('Response did not contain double CRLF')
            content_length = self._get_content_length(msg)
            msg += HEADER_END_STR + tmp[:content_length]
            self.set_cache(tmp[content_length:])
        return msg

    def _add_auth(self, msg):
        '''Authentication request string 
           (i.e. everything after "www-authentication")'''
        #TODO: this is too simplistic and will fail if more than one method
        #       is acceptable, among other issues
        if msg.lower().startswith('basic'):
            pass
        elif msg.lower().startswith('digest '):
            mod_msg = '{'+msg[7:].replace('=',':')+'}'
            mod_msg = mod_msg.replace('realm','"realm"')
            mod_msg = mod_msg.replace('nonce','"nonce"')
            msg_dict = ast.literal_eval(mod_msg)
            response = self._auth_digest(msg_dict)
            auth_string = 'Digest ' \
                          'username="{}", ' \
                          'algorithm="MD5", ' \
                          'realm="{}", ' \
                          'nonce="{}", ' \
                          'uri="{}", ' \
                          'response="{}"'.format(
                          self._parsed_url.username,
                          msg_dict['realm'],
                          msg_dict['nonce'],
                          self._parsed_url.path,
                          response)
            self._auth = auth_string
        else: # Some other failure
            self.do_teardown()
            raise RTSPError('Authentication failure')

    def _auth_digest(self, auth_parameters):
        '''Creates a response string for digest authorization, only works
           with the MD5 algorithm at the moment'''
        #TODO expand to more than MD5
        if self._parsed_url.username:
            HA1 = md5("{}:{}:{}".format(self._parsed_url.username,
                                        auth_parameters['realm'],
                                        self._parsed_url.password).encode()
                                        ).hexdigest()
            HA2 = md5("{}:{}".format(self._cseq_map[self._cseq],
                                     self._parsed_url.path).encode()
                                     ).hexdigest()
            response = md5("{}:{}:{}".format(HA1,
                                             auth_parameters['nonce'],
                                             HA2).encode()).hexdigest()
            return response
        else:
            self.do_teardown()
            raise RTSPError('Authentication required, no username provided')

    def _get_content_length(self, msg):
        '''Content-length is parsed from the message'''
        m = re.search(r'content-length:\s?(?P<len>\d+)', msg.lower(), re.S)
        return (m and int(m.group('len'))) or 0

    def _get_time_str(self):
        '''Python 2.6 and above only supports %f parameters,
           compatible with the lower version with the following wording'''
        dt = datetime.datetime.now()
        return dt.strftime('%Y-%m-%d %H:%M:%S.') + str(dt.microsecond)

    def _process_response(self, msg):
        '''Process the response message'''
        status, headers, body = self._parse_response(msg)
        rsp_cseq = int(headers['cseq'])
        
        if self._cseq_map[rsp_cseq] != 'GET_PARAMETER':
            self._callback(self._get_time_str() + '\n' + msg)
        
        if status == 401 and not self._auth:
            self._add_auth(headers['www-authenticate'])
            self.do_replay_request()
        elif status == 302:
            self.location = headers['location']
        elif status != 200:
            self.do_teardown()
        elif self._cseq_map[rsp_cseq] == 'DESCRIBE': #Implies status 200
            self._update_content_base(msg)
            self._parse_track_id(body)
            self.state = 'describe'
            if self.choose_transport:
                self.TRANSPORT_TYPE_LIST = self.choose_transport(body)
        elif self._cseq_map[rsp_cseq] == 'SETUP':
            self._session_id = headers['session']
            self.send_heart_beat_msg()
            self.state = 'setup'
        elif self._cseq_map[rsp_cseq] == 'PLAY':
            self.state = 'play'
        else:
            pass
            #print(msg)

    def _process_announce(self, msg):
        '''Processes the ANNOUNCE notification message'''
        self._callback(msg)
        headers = self._parse_header_params(msg.splitlines()[1:])
        x_notice_val = int(headers['x-notice'])
        if x_notice_val in (X_NOTICE_EOS, X_NOTICE_BOS):
            self.cur_scale = 1
            self.do_play(self.cur_range, self.cur_scale)
        elif x_notice_val == X_NOTICE_CLOSE:
            self.do_teardown()

    def _parse_response(self, msg):
        '''Resolve the response message'''
        header, body = msg.split(HEADER_END_STR)[:2]
        header_lines = header.splitlines()
        version, status = header_lines[0].split(None, 2)[:2]
        headers = self._parse_header_params(header_lines[1:])
        return int(status), headers, body

    def _parse_header_params(self, header_param_lines):
        '''Parse header parameters'''
        headers = {}
        for line in header_param_lines:
            if line.strip():
                key, val = line.split(':', 1)
                headers[key.lower()] = val.strip()
        return headers

    def _parse_track_id(self, sdp):
        '''Resolves a string of the form trackID = 2 from sdp'''
        m = re.findall(r'a=control:(?P<trackid>[\w=\d]+)', sdp, re.S)
        #m = re.findall(r'a=control:\w+(?P<trackid>[\d]+)', sdp, re.S)
        self.track_id_lst = m

    def _next_seq(self):
        self._cseq += 1
        return self._cseq

    def _sendmsg(self, method, url, headers):
        '''Send a message'''
        self.flush() # clear recv buffer
        msg = '%s %s %s'%(method, url, RTSP_VERSION)
        headers['User-Agent'] = DEFAULT_USERAGENT
        cseq = self._next_seq()
        self._cseq_map[cseq] = method
        headers['CSeq'] = str(cseq)
        if self._session_id:
            headers['Session'] = self._session_id
        for (k, v) in list(headers.items()):
            msg += END_OF_LINE + '%s: %s'%(k, str(v))
        msg += HEADER_END_STR # End headers
        if method != 'GET_PARAMETER' or 'x-RetransSeq' in headers:
            self._callback(self._get_time_str() + END_OF_LINE + msg)
        try:
            self._sock.send(msg.encode())
        except socket.error as e:
            self._callback('Send msg error: %s'%e)
            raise RTSPNetError(e)

    def _get_transport_type(self):
        '''The Transport string parameter that is required to get SETUP'''
        transport_str = ''
        ip_type = 'unicast' #TODO: if IPAddress(DEST_IP).is_unicast() 
                            #      else 'multicast'
        for t in self.TRANSPORT_TYPE_LIST:
            if t not in TRANSPORT_TYPE_MAP:
                raise RTSPError('Error param: %s' % t)
            if t.endswith('tcp'):
                transport_str +=TRANSPORT_TYPE_MAP[t]%ip_type
            else:
                transport_str +=TRANSPORT_TYPE_MAP[t]%(ip_type, 
                                                       self._dest_ip, 
                                                       self.CLIENT_PORT_RANGE)
        return transport_str

    def do_describe(self, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        headers['Accept'] = 'application/sdp'
        if self.ENABLE_ARQ:
            headers['x-Retrans'] = 'yes'
            headers['x-Burst'] = 'yes'
        if self.ENABLE_FEC: 
            headers['x-zmssFecCDN'] = 'yes'
        if self.NAT_IP_PORT: 
            headers['x-NAT'] = self.NAT_IP_PORT
        self._sendmsg('DESCRIBE', self._orig_url, headers)

    def do_setup(self, track_id_str=None, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        headers['Transport'] = self._get_transport_type()
        #TODO: Currently issues SETUP for all tracks but doesn't keep track 
        # of all sessions or teardown all of them.
        if isinstance(track_id_str,str):
            self._sendmsg('SETUP', self._orig_url+'/'+track_id_str, headers)
        elif isinstance(track_id_str, int):
            self._sendmsg('SETUP', self._orig_url + '/' +
                                   self.track_id_lst[track_id_str], headers)
        elif self.track_id_lst:
            for track in self.track_id_lst:
                self._sendmsg('SETUP', self._orig_url+'/'+track, headers)
        else:
            self._sendmsg('SETUP', self._orig_url, headers)

    def do_play(self, range='npt=end-', scale=1, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        headers['Range'] = range
        headers['Scale'] = scale
        self._sendmsg('PLAY', self._orig_url, headers)

    def do_pause(self, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        self._sendmsg('PAUSE', self._orig_url, headers)

    def do_teardown(self, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        self._sendmsg('TEARDOWN', self._orig_url, headers)
        self.running = False

    def do_options(self, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        self._sendmsg('OPTIONS', self._orig_url, headers)

    def do_get_parameter(self, headers={}):
        if self._auth:
            headers['Authorization'] = self._auth
        self._sendmsg('GET_PARAMETER', self._orig_url, headers)

    def do_replay_request(self, headers={}):
        if self._cseq_map[self._cseq] == 'DESCRIBE':
            self.do_describe()
        elif self._cseq_map[self._cseq] == 'SETUP':
            self.do_setup()
        elif self._cseq_map[self._cseq] == 'PLAY':
            self.do_play()
        elif self._cseq_map[self._cseq] == 'PAUSE':
            self.do_pause()
        elif self._cseq_map[self._cseq] == 'TEARDOWN':
            self.do_teardown()
        elif self._cseq_map[self._cseq] == 'OPTIONS':
            self.do_options()
        elif self._cseq_map[self._cseq] == 'GET_PARAMETER':
            self.do_get_parameter()

    def send_heart_beat_msg(self):
        '''Timed sending GET_PARAMETER message keep alive'''
        if not self.running:
            self.do_get_parameter()
            threading.Timer(self.HEARTBEAT_INTERVAL, 
                            self.send_heart_beat_msg).start()

    def ping(self, timeout=0.01):
        '''No exceptions == service available'''
        self.do_options()
        time.sleep(timeout)
        self.close()
        return self.response
