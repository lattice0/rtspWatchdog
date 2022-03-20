#!/usr/bin/env python3
#Reboots an ONVIF/RTSP camera if RTSP is down. VStarcam cameras suffer from this problem.

import rx
from rx import operators as ops
import time
from cameras import cams, Camera
from pprint import pprint
from functools import partial
import signal,sys,time

def signal_handling(signum,frame):           
    sys.exit()                        

signal.signal(signal.SIGINT,signal_handling) 

QUERY_INTERVAL = 55

import datetime
print(str(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')) + ' ----------- rtspWatchdog started')

cam_holder = {}

class Cam():
    cam = None
    watchdog = None
    buffer_signal = None
    stream = None
    repeater = None

def process_camera_condition(cam, condition):
    if cam.RTSP_UNHEALTHY in condition and cam.ONVIF_HEALTHY in condition:
        cam.log("REBOOTING!")
        cam.camera.create_devicemgmt_service()
        cam.camera.devicemgmt.SystemReboot()
    if cam.RTSP_UNHEALTHY in condition and cam.ONVIF_UNHEALTHY in condition:
        cam.log("Both ONVIF and RTSP are down!")
    if cam.RTSP_HEALTHY in condition and cam.ONVIF_UNHEALTHY in condition:
        cam.log("Very strange, RTSP is ok but not ONVIF")
    if cam.RTSP_HEALTHY in condition and cam.ONVIF_UNHEALTHY in condition:
        #cam.log("Camera OK")
        pass

def high_order_subscribe(watchdog,observable,disposable):
    return watchdog.subscribe(observable)

def high_order_return(o):
    return o

def high_order_log(logger_function, info):
    logger_function(info)
    return

for cam in cams:
    unique_id = str(cam.ip) + ':' + str(cam.onvif)
    cam_holder[unique_id] = Cam()
    c = cam_holder[unique_id]
    c.cam = cam

    c.watchdog = rx.subject.Subject()

    c.buffer_signal = rx.create(partial(high_order_subscribe, c.watchdog)).pipe(
        ops.filter(lambda x: x==Camera.COMPLETE_BUFFER)
    )

    c.stream = rx.create(partial(high_order_subscribe, c.watchdog)).pipe(
        ops.buffer_when(partial(high_order_return, c.buffer_signal))
    )

    c.buffer_signal.subscribe(
        on_next = lambda i: None,
        on_error = partial(high_order_log, cam.log_error),
        on_completed = lambda: None,
    )

    c.stream.subscribe(
        on_next = partial(process_camera_condition,c.cam),
        on_error = partial(high_order_log, cam.log_error),
        on_completed = lambda: None,
    )

    c.repeater = rx.interval(QUERY_INTERVAL).pipe(
        ops.do_action(partial(c.cam.watchdog,c.watchdog))
    )

    c.repeater.subscribe(
        on_next = lambda i: None,
        on_error = partial(high_order_log, cam.log_error),
        on_completed = lambda: None,
    )

while True:
    pass
