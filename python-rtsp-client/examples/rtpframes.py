#!/usr/bin/python
#-----------------------------------------------------------------------
# Input with autocompletion
#-----------------------------------------------------------------------
import readline, sys
sys.path.append('../')
from rtsp import *
from rtp import *
from optparse import OptionParser
COMMANDS = (
        'backward',
        'begin',
        'exit',
        'forward',
        'help',
        'live',
        'pause',
        'play',
        'range:',
        'scale:',
        'teardown',
)

def complete(text, state):
    options = [i for i in COMMANDS if i.startswith(text)]
    return (state < len(options) and options[state]) or None

def input_cmd():
    readline.set_completer_delims(' \t\n')
    readline.parse_and_bind("tab: complete")
    readline.set_completer(complete)
    if(sys.version_info > (3, 0)):
        cmd = input(COLOR_STR('Input Command # ', CYAN))
    else:
        cmd = raw_input(COLOR_STR('Input Command # ', CYAN))
    PRINT('') # add one line
    return cmd
#-----------------------------------------------------------------------

#--------------------------------------------------------------------------
# Colored Output in Console
#--------------------------------------------------------------------------
DEBUG = False
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA,CYAN,WHITE = list(range(90, 98))
def COLOR_STR(msg, color=WHITE):
    return '\033[%dm%s\033[0m'%(color, msg)

def PRINT(msg, color=WHITE, out=sys.stdout):
    if DEBUG and out.isatty() :
        out.write(COLOR_STR(msg, color) + '\n')
#--------------------------------------------------------------------------

def exec_cmd(myrtsp, cmd):
    '''Execute the operation according to the command'''
    if cmd in ('exit', 'teardown'):
        myrtsp.do_teardown()
    elif cmd == 'pause':
        myrtsp.cur_scale = 1; myrtsp.cur_range = 'npt=now-'
        myrtsp.do_pause()
    elif cmd == 'help':
        PRINT(play_ctrl_help())
    elif cmd == 'forward':
        if myrtsp.cur_scale < 0: myrtsp.cur_scale = 1
        myrtsp.cur_scale *= 2; myrtsp.cur_range = 'npt=now-'
    elif cmd == 'backward':
        if myrtsp.cur_scale > 0: myrtsp.cur_scale = -1
        myrtsp.cur_scale *= 2; myrtsp.cur_range = 'npt=now-'
    elif cmd == 'begin':
        myrtsp.cur_scale = 1; myrtsp.cur_range = 'npt=beginning-'
    elif cmd == 'live':
        myrtsp.cur_scale = 1; myrtsp.cur_range = 'npt=end-'
    elif cmd.startswith('play'):
        m = re.search(r'range[:\s]+(?P<range>[^\s]+)', cmd)
        if m: myrtsp.cur_range = m.group('range')
        m = re.search(r'scale[:\s]+(?P<scale>[\d\.]+)', cmd)
        if m: myrtsp.cur_scale = int(m.group('scale'))

    if cmd not in ('pause', 'exit', 'teardown', 'help'):
        myrtsp.do_play(myrtsp.cur_range, myrtsp.cur_scale)

def main(url, options):
    myrtsp = RTSPClient(url, options.dest_ip, callback=PRINT)

    if options.transport:   myrtsp.TRANSPORT_TYPE_LIST = options.transport.split(',')
    if options.client_port: myrtsp.CLIENT_PORT_RANGE = options.client_port
    if options.nat:         myrtsp.NAT_IP_PORT = options.nat
    if options.arq:         myrtsp.ENABLE_ARQ  = options.arq
    if options.fec:         myrtsp.ENABLE_FEC  = options.fec

    if options.ping:
        PRINT('PING START', YELLOW)
        myrtsp.ping(0.1)
        PRINT('PING DONE', YELLOW)
        sys.exit(0)
        return

    try:
        myrtsp.do_describe()
        while myrtsp.state != 'describe':
            time.sleep(0.1)
        myrtsp.do_setup(0)
        while myrtsp.state != 'setup':
            time.sleep(0.1)
        #Setup up RTP capture here
        f=open('test.h264','wb')
        rtpframes = RTPReceive([10014],callback=f.write)
        while not rtpframes.running:
            time.sleep(0.1)
        myrtsp.do_play(myrtsp.cur_range, myrtsp.cur_scale)
        while myrtsp.running:
            if myrtsp.state == 'play':
                cmd = input_cmd()
                exec_cmd(myrtsp, cmd)
            # 302 redirect to re-establish chain
            if myrtsp.location:
                myrtsp = RTSPClient(myrtsp.location)
                myrtsp.do_describe()
            time.sleep(0.5)
    except KeyboardInterrupt:
        f.close()
        myrtsp.do_teardown()
        print('\n^C received, Exit.')

def play_ctrl_help():
    help = COLOR_STR('In running, you can control play by input "forward"' \
                    +', "backward", "begin", "live", "pause"\n', MAGENTA)
    help += COLOR_STR('or "play" with "range" and "scale" parameter, such ' \
                     +'as "play range:npt=beginning- scale:2"\n', MAGENTA)
    help += COLOR_STR('You can input "exit", "teardown" or ctrl+c to ' \
                     +'quit\n', MAGENTA)
    return help

if __name__ == '__main__':
    usage = COLOR_STR('%prog [options] url\n\n', GREEN) + play_ctrl_help()

    parser = OptionParser(usage=usage)
    parser.add_option('-t', '--transport', dest='transport', 
                      default='rtp_over_udp',
                      help='Set transport type when issuing SETUP: '
                          +'ts_over_tcp, ts_over_udp, rtp_over_tcp, '
                          +'rtp_over_udp[default]')
    parser.add_option('-d', '--dest_ip', dest='dest_ip',
                      help='Set destination ip of udp data transmission, '
                          +'default uses same ip as this rtsp client')
    parser.add_option('-p', '--client_port', dest='client_port',
                      help='Set client port range when issuing SETUP of udp, '
                          +'default is "10014-10015"')
    parser.add_option('-n', '--nat', dest='nat',
                      help='Add "x-NAT" when issuing DESCRIBE, arg format '
                          +'"192.168.1.100:20008"')
    parser.add_option('-r', '--arq', dest='arq', action="store_true",
                      help='Add "x-Retrans:yes" when issuing DESCRIBE')
    parser.add_option('-f', '--fec', dest='fec', action="store_true",
                      help='Add "x-zmssFecCDN:yes" when issuing DESCRIBE')
    parser.add_option('-P', '--ping', dest='ping', action="store_true",
                      help='Just issue OPTIONS and exit.')

    (options, args) = parser.parse_args()
    if len(args) < 1:
        parser.print_help()
        sys.exit()

    url = args[0]

    DEBUG = True
    main(url, options)
# EOF #

