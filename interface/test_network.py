#!/bin/env python3
import tkinter
import socket
import struct
import time
import pickle
import select
from enum import Enum
from struct import unpack
from pprint import pp
import sys


class SquareState(Enum):
    UNKNOWN = 0
    EMPTY = 1
    WALL = 2
    ROBOT = 3
    START = 4


pi_socket: socket.socket | None = None
while (True):
    try:
        pi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        pi_socket.connect(("10.42.0.1", 8027))
        #pi_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        break
    except Exception:
        print("Anslut till kartrobot07...")


buffer = b''
header_size = 4  # 4 bytes for the message length
while True:
    # Read the header to get the message length
    
    while len(buffer) < header_size:
        buffer += pi_socket.recv(1024)
        print(len(buffer))
        print("läst buffer")
    try:    
        msglen = struct.unpack('<I', buffer[:header_size])[0]
        #if not msglen:
        #    break
    except:
        print("PICKLE FAIL")
    print(msglen)
    buffer = buffer[header_size:]
    # Read the full message
    while len(buffer) < msglen:
        buffer += pi_socket.recv(1024)
    message_data = pickle.loads(buffer[:msglen])
    buffer = buffer[msglen:]
    print(message_data)
