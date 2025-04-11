#!/bin/env python3
from copy import deepcopy
from enum import IntEnum
from math import floor
from pprint import pp
from queue import LifoQueue, Queue
from random import random
import datetime
import os
import struct
import pickle
import select
import serial
import socket
import sys
import time

from threading import Thread

DEBUG_STANDALONE_MODE: bool = False

driverSndQueue: Queue = Queue()
sensorSndQueue: Queue = Queue()
driverRcvQueue: Queue = Queue()
sensorRcvQueue: Queue = Queue()


class Direction(IntEnum):
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3


class SquareState(IntEnum):
    UNKNOWN = 0
    EMPTY = 1
    WALL = 2
    ROBOT = 3


currentDirection: Direction = Direction.NORTH
autoMode: bool = False
mapData: list[list[SquareState]] = [
    [SquareState.UNKNOWN for _ in range(75)]
    for _ in range(75)
]

# NOTE: (x, y)
lastPosition: tuple[int, int] = (37, 37)
robotPosition: tuple[int, int] = (37, 37)

driverReady: bool = True
driver_ttyUSB: serial.Serial | None = None
sensor_ttyUSB: serial.Serial | None = None

try:
    driver_ttyUSB = serial.Serial(
        port='/dev/ttyUSB0',
        baudrate=19200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_TWO,
        timeout=0.05,
    )
    sensor_ttyUSB = serial.Serial(
        port='/dev/ttyUSB1',
        baudrate=19200,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_TWO,
        timeout=0.05,
    )
except serial.SerialException:
    print("DEBUG: UART serial objects not created")
    pass


def uart_thread(
    ttyUSB: serial.Serial | None,
    send_queue: Queue,
    recv_queue: Queue,
) -> None:
    if not ttyUSB:
        print("UART device not initialized")
        return
    while True:
        # SEND
        if not send_queue.empty():
            data_to_send = send_queue.get()
            # print(ttyUSB, data_to_send)
            try:
                ttyUSB.write(data_to_send)
                # print(f"Sent: {data_to_send}")
            except serial.SerialException as e:
                print(f"Error writing to UART: {e}")

        # READ
        try:
            read_buf = ttyUSB.read(256)
            if read_buf:
                recv_queue.put(read_buf)
                if ttyUSB == driver_ttyUSB:
                    # print(f"Received: {read_buf}")
                    pass
        except serial.SerialException as e:
            print(f"Error reading from UART: {e}")

        time.sleep(0.01)


if driver_ttyUSB:
    Thread(
        target=uart_thread,
        args=(driver_ttyUSB, driverSndQueue, driverRcvQueue),
        daemon=True,
    ).start()
if sensor_ttyUSB:
    Thread(
        target=uart_thread,
        args=(sensor_ttyUSB, sensorSndQueue, sensorRcvQueue),
        daemon=True,
    ).start()


def uart_send(send_queue: Queue, data: bytes) -> None:
    if send_queue == driverSndQueue:
        print("Trying to send", data)
    send_queue.put(data)


def uart_recv(recv_queue: Queue) -> bytes | None:
    if not recv_queue.empty():
        data: bytes = recv_queue.get()
        # print("RECIEVED", data)
        return data
    return None


def get_interface_data(conn: socket.socket) -> int | None:
    ready = select.select([conn], [], [], 0)
    if ready[0]:
        data = conn.recv(64)
        if len(data) == 0:
            print('Disconnected')
            return -1
        print(len(data))
        return int.from_bytes(data, 'big')
    return None


def getDriverData() -> bool:
    global driverRcvQueue
    if DEBUG_STANDALONE_MODE:
        return True
    # print("gettin driver data ...")
    readBuf: bytes | None = uart_recv(driverRcvQueue)
    if readBuf:
        print(readBuf)
        print("read " + str(len(readBuf)) + " amount of bytes from DRIVER")

        if int.from_bytes(readBuf, 'big') == 0x0B:
            # print("DRIVER IS READY")
            return True
    return False


fakeWalls: dict[tuple[int, int], bool] = {
    (38, 37): True,
    (39, 36): True,
    (38, 35): True,
    (37, 34): True,
    (38, 33): True,
    (37, 33): True,
    (36, 33): True,
    (35, 33): True,
    (34, 33): True,
    (33, 33): True,
    (32, 33): True,
    (31, 33): True,
    (31, 34): True,
    (31, 35): True,
    (31, 36): True,
    (31, 37): True,
    (31, 38): True,
    (31, 39): True,
    (31, 40): True,
    (32, 40): True,
    (33, 40): True,
    (34, 40): True,
    (35, 40): True,
    (35, 36): True,  # ADDED
    (36, 38): True,
    (36, 39): True,
    (37, 38): True,

    # Köksön
    (34, 37): True,
    (33, 37): True,
    (33, 36): True,
    (33, 35): True,
    (34, 35): True,

}


def getSimulatedSensorData() -> list[int]:
    fakeSensorData = []
    for d in range(4):
        for distance in [1, 2]:
            delta: list[tuple[int, int]] = []
            direction = Direction(d)
            match currentDirection:
                case Direction.NORTH:
                    delta = [(0, -1), (1, 0), (0, 1), (-1, 0)]
                case Direction.EAST:
                    delta = [(1, 0), (0, 1), (-1, 0), (0, -1)]
                case Direction.SOUTH:
                    delta = [(0, 1), (-1, 0), (0, -1), (1, 0)]
                case Direction.WEST:
                    delta = [(-1, 0), (0, -1), (1, 0), (0, 1)]
            checkPos: tuple[int, int] = (
                robotPosition[0] + delta[d][0] * distance,
                robotPosition[1] + delta[d][1] * distance,
            )
            try:
                if fakeWalls[checkPos]:
                    fakeSensorData.append(11 + floor((distance-1)*50))
                    break
            except KeyError:
                pass
            if distance == 2:
                fakeSensorData.append(255)
    return fakeSensorData


def flood(goal: tuple[int, int]) -> Direction:
    floodQueue: Queue[tuple[tuple[int, int], list[Direction]]] = Queue()
    floodVisited: set[tuple[int, int]] = set()
    floodQueue.put((robotPosition, []))
    print("GOAL", goal)

    while not floodQueue.empty():
        next_square: tuple[int, int]
        path_there: list[Direction]
        next_square, path_there = floodQueue.get()
        if next_square in floodVisited:
            continue
        floodVisited.add(next_square)
        for sq, direction in adjacentSquares(next_square):
            new_path: list[Direction] = path_there + [direction]
            if sq not in floodVisited:
                if mapData[sq[1]][sq[0]] == SquareState.EMPTY:
                    floodQueue.put((sq, new_path))
                    if sq == goal:
                        return new_path[0]
    raise Exception("unreachable (flood)")


def adjacentSquares(
    pos: tuple[int, int],
) -> list[tuple[tuple[int, int], Direction]]:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    if currentDirection == Direction.NORTH:
        return [
            ((pos[0] - 1, pos[1]), Direction.WEST),
            ((pos[0], pos[1] + 1), Direction.SOUTH),
            ((pos[0], pos[1] - 1), Direction.NORTH),
            ((pos[0] + 1, pos[1]), Direction.EAST)
        ]
    if currentDirection == Direction.EAST:
        return [
            ((pos[0], pos[1] - 1), Direction.NORTH),
            ((pos[0] - 1, pos[1]), Direction.WEST),
            ((pos[0] + 1, pos[1]), Direction.EAST),
            ((pos[0], pos[1] + 1), Direction.SOUTH)
        ]
    if currentDirection == Direction.SOUTH:
        return [
            ((pos[0] + 1, pos[1]), Direction.EAST),
            ((pos[0], pos[1] - 1), Direction.NORTH),
            ((pos[0], pos[1] + 1), Direction.SOUTH),
            ((pos[0] - 1, pos[1]), Direction.WEST)
        ]
    if currentDirection == Direction.WEST:
        return [
            ((pos[0], pos[1] + 1), Direction.SOUTH),
            ((pos[0] + 1, pos[1]), Direction.EAST),
            ((pos[0] - 1, pos[1]), Direction.WEST),
            ((pos[0], pos[1] - 1), Direction.NORTH)
        ]


class Command(IntEnum):
    CMD_FORWARD = 1
    CMD_BACKWARD = 2
    CMD_TURNRIGHT = 3
    CMD_TURNLEFT = 4


def directionToCommand(direction: Direction) -> Command:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection

    diff: int = (direction - currentDirection + 4) % 4
    match diff:
        case 0:
            return Command.CMD_FORWARD
        case 1:
            return Command.CMD_TURNRIGHT
        case 2:
            return Command.CMD_BACKWARD
        case 3:
            return Command.CMD_TURNLEFT
        case _:
            raise Exception("unreachable (directionToCommand)")


queue: LifoQueue[tuple[int, int]] = LifoQueue()
queue.put((robotPosition[0], robotPosition[1] - 1))  # start
visitedSquares: set[tuple[int, int]] = set()
returnToStart: bool = False


def pathfindEmpty() -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection, \
        queue, returnToStart
    if queue.empty():
        if robotPosition != (37, 37):
            queue.put((37, 37))
            returnToStart = True
        else:
            # moveToDirection(Direction.SOUTH)
            print("Done driving...")
            autoMode = False
            return

    next_square = queue.get()
    if (next_square in visitedSquares) and not returnToStart:
        print("IGNORING NEXT SQUARE", len(queue.queue))
        return

    if robotPosition == next_square:
        return

    lastPosition = robotPosition

    nextDirection: Direction = flood(next_square)

    moveToDirection(nextDirection)

    if robotPosition != next_square:
        queue.put(next_square)
    print("exited.. pathfindEmpty")


def moveToDirection(nextDirection: Direction) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection, queue
    if not driverReady:
        return

    command: Command = directionToCommand(nextDirection)
    visitedSquares.add(robotPosition)
    if not DEBUG_STANDALONE_MODE:
        sendCommand(command.to_bytes(1, 'big'))
    if command == Command.CMD_FORWARD:
        match currentDirection:
            case Direction.NORTH:
                robotPosition = (robotPosition[0], robotPosition[1] - 1)
            case Direction.EAST:
                robotPosition = (robotPosition[0] + 1, robotPosition[1])
            case Direction.SOUTH:
                robotPosition = (robotPosition[0], robotPosition[1] + 1)
            case Direction.WEST:
                robotPosition = (robotPosition[0] - 1, robotPosition[1])
    elif command == Command.CMD_BACKWARD:
        print("BACKWARD")
        match currentDirection:
            case Direction.NORTH:
                robotPosition = (robotPosition[0], robotPosition[1] + 1)
            case Direction.EAST:
                robotPosition = (robotPosition[0] - 1, robotPosition[1])
            case Direction.SOUTH:
                robotPosition = (robotPosition[0], robotPosition[1] - 1)
            case Direction.WEST:
                robotPosition = (robotPosition[0] + 1, robotPosition[1])
    elif command == Command.CMD_TURNRIGHT:
        currentDirection = Direction((currentDirection + 1) % 4)
    elif command == Command.CMD_TURNLEFT:
        currentDirection = Direction((currentDirection - 1) % 4)


def addAdjacent() -> None:
    for adjSq, _ in adjacentSquares(robotPosition):
        if adjSq not in visitedSquares:
            if mapData[adjSq[1]][adjSq[0]] == SquareState.EMPTY:
                queue.put(adjSq)


def getSensorData() -> list[int] | None:
    global sensorSndQueue, sensorRcvQueue
    uart_send(sensorSndQueue, (253).to_bytes(1, 'big'))
    # print("gettin sensor data ... ")
    readBuf: bytes | None = uart_recv(sensorRcvQueue)
    # print("read sensor data !!!")

    if readBuf:
        # print("read " + str(len(readBuf)) + " amount of bytes from SENSOR")
        # print("FR", int.from_bytes(readBuf[0:1], 'big', signed=False))
        # print("FL", int.from_bytes(readBuf[1:2], 'big', signed=False))
        # print("F", int.from_bytes(readBuf[2:3], 'big', signed=False))
        # print("BR", int.from_bytes(readBuf[3:4], 'big', signed=False))
        # print("BL", int.from_bytes(readBuf[4:5], 'big', signed=False))
        # print("B", int.from_bytes(readBuf[5:6], 'big', signed=False))

        return [
            int.from_bytes(readBuf[2:3], 'big', signed=False),
            int.from_bytes(readBuf[3:4], 'big', signed=False),
            int.from_bytes(readBuf[5:6], 'big', signed=False),
            int.from_bytes(readBuf[4:5], 'big', signed=False),
        ]
    return None


def updateMap(sensorData: list[int] | None) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    delta = []
    match currentDirection:
        case Direction.NORTH:
            delta = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        case Direction.EAST:
            delta = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        case Direction.SOUTH:
            delta = [(0, 1), (-1, 0), (0, -1), (1, 0)]
        case Direction.WEST:
            delta = [(-1, 0), (0, -1), (1, 0), (0, 1)]
    for i in range(4):
        nextPos = tuple(map(lambda t1, t2: t1 + t2, robotPosition, delta[i]))
        if not sensorData:
            pass
        elif 11 <= sensorData[i] <= 30:
            mapData[nextPos[1]][nextPos[0]] = SquareState.WALL
        elif 30 < sensorData[i]:
            mapData[nextPos[1]][nextPos[0]] = SquareState.EMPTY
    mapData[lastPosition[1]][lastPosition[0]] = SquareState.EMPTY
    mapData[robotPosition[1]][robotPosition[0]] = SquareState.ROBOT


def sendSensorDataToInterface(
    conn: socket.socket,
    sensorData: list[int] | None,
    mapData: list[list[SquareState]],
) -> bool:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    # print("SENDDDDDDDD\n")
    pickled_data = pickle.dumps({"mapData": mapData, 'sensors': sensorData})
    length: int = len(pickled_data)
    # msg = struct.pack("<I", length) + pickled_data

    try:
        ready = select.select([], [conn], [], 0)
        if ready[1]:
            # print("Sending sensor data to interface...")
            conn.sendall(struct.pack("<I", length) + pickled_data)
            # print("finished sending sensor data to interface...")
    except ConnectionResetError:
        print("WARN: Connection reset")
        return False
    # print("sending donne")
    return True


def sendCommand(data: bytes) -> None:
    global driverReady, driverSndQueue
    print("command", data)

    if not driverReady:
        return

    uart_send(driverSndQueue, data)

    driverReady = False


def send_stop() -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection, \
        driverSndQueue
    print('sending stop')
    uart_send(driverSndQueue, (0).to_bytes(1, 'big'))


def send_forward(short: bool) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    print('sending fram', short)
    if short:
        sendCommand((5).to_bytes(1, 'big'))
    else:
        sendCommand((1).to_bytes(1, 'big'))
        lastPosition = robotPosition
        match currentDirection:
            case Direction.NORTH:
                robotPosition = (robotPosition[0], robotPosition[1] - 1)
            case Direction.EAST:
                robotPosition = (robotPosition[0] + 1, robotPosition[1])
            case Direction.SOUTH:
                robotPosition = (robotPosition[0], robotPosition[1] + 1)
            case Direction.WEST:
                robotPosition = (robotPosition[0] - 1, robotPosition[1])


def send_backward(short: bool) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    print('sending back', short)
    if short:
        sendCommand((6).to_bytes(1, 'big'))
    else:
        sendCommand((2).to_bytes(1, 'big'))
        lastPosition = robotPosition
        match currentDirection:
            case Direction.NORTH:
                robotPosition = (robotPosition[0], robotPosition[1] + 1)
            case Direction.EAST:
                robotPosition = (robotPosition[0] - 1, robotPosition[1])
            case Direction.SOUTH:
                robotPosition = (robotPosition[0], robotPosition[1] - 1)
            case Direction.WEST:
                robotPosition = (robotPosition[0] + 1, robotPosition[1])


def turn_right(short: bool) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    print('sending sväng höger')
    if short:
        sendCommand((7).to_bytes(1, 'big'))
    else:
        sendCommand((3).to_bytes(1, 'big'))
        currentDirection = Direction((int(currentDirection) + 1) % 4)


def turn_left(short: bool) -> None:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection
    print('sending sväng vänster')
    if short:
        sendCommand((8).to_bytes(1, 'big'))
    else:
        sendCommand((4).to_bytes(1, 'big'))
        currentDirection = Direction((int(currentDirection) + 3) % 4)


def main() -> int:
    global robotPosition, currentDirection, autoMode, lastPosition, \
        driver_ttyUSB, sensor_ttyUSB, driverReady, currentDirection, \
        queue, driverSndQueue, driverRcvQueue, sensorSndQueue, \
        sensorRcvQueue, mapData
    try:
        driverSndQueue.put((255).to_bytes(1, 'big'))
        sensorSndQueue.put((255).to_bytes(1, 'big'))
        print("getting driver ident (blocking...)")
        firstIdent: bytes = sensorRcvQueue.get()

        if int.from_bytes(firstIdent, 'big') == 1:
            print("UART connections Should be fine?")
        elif int.from_bytes(firstIdent, 'big') == 0xA:
            print("Switch UART connections...")
            driverSndQueue, sensorSndQueue = sensorSndQueue, driverSndQueue
            driverRcvQueue, sensorRcvQueue = sensorRcvQueue, driverRcvQueue
            driver_ttyUSB, sensor_ttyUSB = sensor_ttyUSB, driver_ttyUSB
            # sys.exit(9)
        else:
            print("First USB port sent neither identifier??")

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            client_socket.bind(('0.0.0.0', 8027))
        except socket.error as message:
            print(message)
            sys.exit(8)
        client_socket.listen(9)

        print("waiting for client to connect")
        conn: socket.socket
        address: socket._RetAddress
        conn, address = client_socket.accept()

        # send_forward(False)

        while True:
            # conn, address = client_socket.accept()

            print('Got new connection')
            while True:
                # print("LOOP")
                interfaceCommand = get_interface_data(conn)
                match interfaceCommand:
                    case 0:
                        send_stop()
                        pass
                    case 1:
                        if not autoMode and driverReady:
                            send_forward(False)
                    case 2:
                        if not autoMode and driverReady:
                            send_backward(False)
                    case 3:
                        if not autoMode and driverReady:
                            turn_right(False)
                    case 4:
                        if not autoMode and driverReady:
                            turn_left(False)
                    case 6:
                        if not autoMode and driverReady:
                            send_forward(True)
                    case 6:
                        if not autoMode and driverReady:
                            send_backward(True)
                    case 7:
                        if not autoMode and driverReady:
                            turn_right(True)
                    case 8:
                        if not autoMode and driverReady:
                            turn_left(True)
                    case 9:
                        autoMode = not autoMode
                        continue
                    case 10:
                        return 0
                    case -1:
                        print("Broken network connection")
                        return 2
                if not driverReady:
                    driverReady = getDriverData()

                sensorData: list[int] | None = None
                if driverReady:
                    # sensorData = getSensorData()
                    if not DEBUG_STANDALONE_MODE:
                        sensorData = getSensorData()
                    else:
                        sensorData = getSimulatedSensorData()

                    updateMap(sensorData)
                    if autoMode and sensorData:
                        addAdjacent()
                        pathfindEmpty()
                        autoMode = False

                sendSensorDataToInterface(conn, sensorData, mapData)
                time.sleep(0.01)

    except KeyboardInterrupt:
        # print("breakpoint...")
        # breakpoint()
        if sensor_ttyUSB and sensor_ttyUSB.is_open:
            sensor_ttyUSB.close()
        if driver_ttyUSB and driver_ttyUSB.is_open:
            driver_ttyUSB.close()
        return 1


if __name__ == '__main__':
    sys.exit(main())
