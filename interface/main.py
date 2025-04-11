#!/bin/env python3
import tkinter
import socket
import pickle
import select
import time
from enum import Enum
from struct import unpack
from pprint import pp
import struct

from tkinter import *

from typing import Optional

# pi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# pi_socket.connect(("10.42.0.1", 8027))
# pi_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
# pi_socket.setblocking(0)
previousPos = (37, 37)


print('connecting')
while (True):
    try:
        pi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        pi_socket.connect(("10.42.0.1", 8027))
        pi_socket.settimeout(2)
        break
    except Exception:
        pass


class SquareState(Enum):
    UNKNOWN = 0
    EMPTY = 1
    WALL = 2
    ROBOT = 3
    START = 4


class Interface():
    buffer: bytes = b''
    lastPrint: float

    def recieve(self):
        # READ
        ready = select.select([pi_socket], [], [], 0)

        if ready[0]:
            try:
                while len(self.buffer) < 4:
                    self.buffer += pi_socket.recv(4)
            except (socket.error, TimeoutError):
                self.tk.after(1, self.recieve)
                return

            length = struct.unpack("<I", self.buffer[0:4])[0]
            self.buffer = self.buffer[4:]
            while len(self.buffer) < length:
                self.buffer += pi_socket.recv(1024)
                # if not self.buffer:
                #    break

            messageData = pickle.loads(self.buffer)

            if messageData['sensors'] is not None:
                # if True:
                self.sensorTextBox.delete(1.0, END)
                self.sensorTextBox.insert(
                    tkinter.END,
                    chars=str(messageData['sensors']),
                )

            now: float = time.time()
            if messageData['mapData']:
                if (now - self.lastPrint) >= 0.1:
                    self.lastPrint = now
                    robot_position: tuple[int, int] = [
                        (colnumber, rownumber)
                        for rownumber, row in enumerate(messageData['mapData'])
                        for colnumber, cell in enumerate(row)
                        if cell == SquareState.ROBOT
                    ][0]
                    for row in range(robot_position[1] - 1, robot_position[1] + 2):
                        for col in range(robot_position[0] - 1, robot_position[0] + 2):
                            match messageData['mapData'][row][col]:
                                case SquareState.UNKNOWN:
                                    pass
                                    # self.canvas.create_rectangle(
                                    #     colnumber * 8,
                                    #     rownumber * 8,
                                    #     (colnumber+1) * 8,
                                    #     (rownumber+1) * 8,
                                    #     fill='grey',
                                    # )
                                case SquareState.EMPTY:
                                    self.canvas.create_rectangle(
                                        col * 8,
                                        row * 8,
                                        (col+1) * 8,
                                        (row+1) * 8,
                                        fill='white',
                                    )
                                case SquareState.WALL:
                                    self.canvas.create_rectangle(
                                        col * 8,
                                        row * 8,
                                        (col+1) * 8,
                                        (row+1) * 8,
                                        fill='black',
                                    )
                                case SquareState.ROBOT:
                                    self.canvas.create_rectangle(
                                        col * 8,
                                        row * 8,
                                        (col+1) * 8,
                                        (row+1) * 8,
                                        fill='cyan',
                                    )
                                    self.positionText.delete(1.0, END)
                                    self.positionText.insert(
                                        END, str(col)+','+str(row))
                                case SquareState.START:
                                    self.canvas.create_rectangle(
                                        col * 8,
                                        row * 8,
                                        (col+1) * 8,
                                        (row+1) * 8,
                                        fill='lime',
                                    )

            self.buffer = self.buffer[length:]

        self.tk.after(1, self.recieve)

    def send(self, data: bytes):
        ready = select.select([], [pi_socket], [], 0)
        if ready[1]:
            pi_socket.sendall(data)

    def sendStartStop(self):
        print("Sending Start / Stop")
        self.send((0).to_bytes(8, 'big'))

    def sendForward(self):
        print("Sending Forward")
        self.send((1).to_bytes(8, 'big'))

    def sendBack(self):
        print("Sending Back")
        self.send((2).to_bytes(8, 'big'))

    def sendRight(self):
        print("Sending Right")
        self.send((3).to_bytes(8, 'big'))

    def sendLeft(self):
        print("Sending Left")
        self.send((4).to_bytes(8, 'big'))

    def sendForwardShort(self):
        print("Sending Forward Short")
        self.send((5).to_bytes(8, 'big'))

    def sendBackShort(self):
        print("Sending Back Short")
        self.send((6).to_bytes(8, 'big'))

    def sendRightShort(self):
        print("Sending Right")
        self.send((7).to_bytes(8, 'big'))

    def sendLeftShort(self):
        print("Sending Left")
        self.send((7).to_bytes(8, 'big'))

    def sendManualToggle(self):
        print("Sending Manual Toggle")
        self.send((9).to_bytes(8, 'big'))

    def reset(self):
        print("Exiting")
        self.send((10).to_bytes(8, 'big'))

    def keyHandler(self, event):
        print(event.char, event.keysym, event.keycode)
        match event.char:
            case 'w':
                self.sendForwardShort()
            case 's':
                self.sendBackShort()
            case 'a':
                self.sendLeftShort()
            case 'd':
                self.sendRightShort()
            case 'r':
                self.reset()

    def __init__(self):
        self.tk = Tk()
        self.buttonFrame = Frame(
            self.tk,
            bg='aquamarine',
        )
        self.buttonStartStop = Button(
            self.buttonFrame,
            text="Send Start / Stop",
            command=self.sendStartStop,
        )
        self.buttonForward = Button(
            self.buttonFrame,
            text="Send Forward",
            command=self.sendForward,
        )
        self.buttonBack = Button(
            self.buttonFrame,
            text="Send Backwards",
            command=self.sendBack,
        )
        self.buttonRight = Button(
            self.buttonFrame,
            text="Send Right",
            command=self.sendRight,
        )
        self.buttonLeft = Button(
            self.buttonFrame,
            text="Send Left",
            command=self.sendLeft,
        )
        self.buttonManualToggle = Button(
            self.buttonFrame,
            text="Send Manual Toggle",
            command=self.sendManualToggle,
        )
        self.lastPrint = time.time()

        # Short commands

        self.buttonForwardShort = Button(
            self.buttonFrame,
            text="Send Forward Short",
            command=self.sendForwardShort,
        )
        self.buttonBackShort = Button(
            self.buttonFrame,
            text="Send Backwards Short",
            command=self.sendBackShort,
        )
        self.buttonRightShort = Button(
            self.buttonFrame,
            text="Send Right Short",
            command=self.sendRightShort,
        )
        self.buttonLeftShort = Button(
            self.buttonFrame,
            text="Send Left Short",
            command=self.sendLeftShort,
        )

        self.positionText = Text(
            self.buttonFrame, bg='white', width=8, height=1)

        self.canvas = tkinter.Canvas(self.tk, bg='grey', width=600, height=600)
        # for colnumber in range(75):
        #     for rownumber in range(75):
        #         self.canvas.create_rectangle(
        #             colnumber * 8,
        #             rownumber * 8,
        #             (colnumber+1) * 8,
        #             (rownumber+1) * 8,
        #             fill='grey',
        #         )

        self.canvas.grid(row=0, column=0)

        self.buttonFrame.grid(row=0, column=1)
        self.buttonStartStop.pack()
        self.buttonForward.pack()
        self.buttonBack.pack()
        self.buttonRight.pack()
        self.buttonLeft.pack()
        self.buttonManualToggle.pack()

        self.buttonForwardShort.pack()
        self.buttonBackShort.pack()
        self.buttonRightShort.pack()
        self.buttonLeftShort.pack()

        self.positionText.pack()
        self.sensorTextBox = tkinter.Text(
            self.buttonFrame,
            height=12,
            width=40,
            bg='black',
            fg='lime',
        )
        self.sensorTextBox.pack()

        self.tk.bind("<Key>", self.keyHandler)

        self.tk.after(1, self.recieve)
        self.tk.mainloop()


interFace = Interface()
