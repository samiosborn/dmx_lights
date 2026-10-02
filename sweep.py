# sweep.py

import socket
import struct
import time


TARGET = "192.168.4.1"
PORT = 6454
UNIVERSE = 0


def local_ip_for(target):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((target, PORT))
    ip = s.getsockname()[0]
    s.close()
    return ip


def artdmx(ch1, sequence):
    dmx = bytearray(512)
    dmx[0] = ch1

    return (
        b"Art-Net\x00"
        + struct.pack("<H", 0x5000)   # ArtDMX
        + struct.pack(">H", 14)       # protocol version
        + bytes([sequence, 0])        # sequence, physical
        + struct.pack("<H", UNIVERSE)
        + struct.pack(">H", 512)
        + dmx
    )


local_ip = local_ip_for(TARGET)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((local_ip, 0))

print(f"{local_ip} -> {TARGET}:{PORT}")
print("Sweeping DMX CH1 continuously. Ctrl+C to stop.")

seq = 1

try:
    while True:
        # left -> right
        for value in range(0, 256, 4):
            sock.sendto(artdmx(value, seq), (TARGET, PORT))
            seq = 1 if seq == 255 else seq + 1
            time.sleep(0.025)

        # right -> left
        for value in range(255, -1, -4):
            sock.sendto(artdmx(value, seq), (TARGET, PORT))
            seq = 1 if seq == 255 else seq + 1
            time.sleep(0.025)

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    sock.close()