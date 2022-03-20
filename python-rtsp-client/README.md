python-rtsp-client
==================

A basic rtsp client writen in pure python

Getting Started
---------------

    from rtsp import RTSPClient
    myrtsp = RTSPClient(url='rtsp://username:password@hostname:port/path',callback=print)
    try:
        myrtsp.do_describe()
        while myrtsp.state != 'describe':
            time.sleep(0.1)
        myrtsp.TRANSPORT_TYPE_LIST =  ['rtp_over_udp','rtp_over_tcp']
        myrtsp.do_setup(track_id)
        while myrtsp.state != 'setup':
            time.sleep(0.1)
        #Open socket to capture frames here
        myrtsp.do_play(rtsp.cur_range, rtsp.cur_scale)
    except:
        myrtsp.do_teardown()


Examples
--------
Usage: setupandplay.py [options] url
    
    While running, you can control play by inputting "forward","backward","begin","live","pause"
    or "play" a with "range" and "scale" parameter, such as "play range:npt=beginning- scale:2"
    You can input "exit","teardown" or ctrl+c to quit
    
    
    Options:
      -h, --help            show this help message and exit
      -t TRANSPORT, --transport=TRANSPORT
                            Set transport type when issuing SETUP: ts_over_tcp,
                            ts_over_udp, rtp_over_tcp, rtp_over_udp[default]
      -d DEST_IP, --dest_ip=DEST_IP
                            Set destination ip of udp data transmission, default
                            uses same ip as this rtsp client
      -p CLIENT_PORT, --client_port=CLIENT_PORT
                            Set client port range when issuing SETUP of udp,
                            default is "10014-10015"
      -n NAT, --nat=NAT     Add "x-NAT" when issuing DESCRIBE, arg format
                            "192.168.1.100:20008"
      -r, --arq             Add "x-Retrans:yes" when issuing DESCRIBE
      -f, --fec             Add "x-zmssFecCDN:yes" when issuing DESCRIBE
      -P, --ping            Just issue OPTIONS and exit.
