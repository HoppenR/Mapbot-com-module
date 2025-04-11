#!/bin/env python3
from copy import deepcopy
from enum import IntEnum
from math import floor
from pprint import pp
from queue import LifoQueue, Queue
from random import random
import datetime
import os
import pickle
import select
import serial
import socket
import struct
import sys
import time

from threading import Thread

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)

try:
    client_socket.bind(('0.0.0.0', 8027))
except socket.error as message:
    print(message)
    sys.exit(8)

client_socket.listen(9)
conn, address = client_socket.accept()
#conn.setblocking(0)
print("ACCEPTED!!!!!")
class SquareState(IntEnum):
    UNKNOWN = 0
    EMPTY = 1
    WALL = 2
    ROBOT = 3
    START = 4

sensorData = [42, 42, 42, 42]
mapData: list[list[SquareState]] = [
    [SquareState.UNKNOWN if i % 3 == 0 else SquareState.WALL for i in range(75)]
    for _ in range(75)
]
pickled_data = pickle.dumps(mapData)
#pickled_data = pickle.dumps(sensorData)

while True:
    print("Sending one..")
    time.sleep(1)
    length: int = len(pickled_data)
    lenPack = struct.pack('<I', length)
    print(lenPack)
    print(len(pickled_data))
    while True:
        ready = select.select([], [conn], [], 0)
        if ready[1]:
            conn.sendall(lenPack)
            break
    sent: int = 0
    while sent < length:
        ready = select.select([], [conn], [], 0)
        if ready[1]:
            conn.sendall(pickled_data[sent : sent + 1024])
            sent += 1024
