# -*- coding: utf-8 -*-
"""
Created on Tue May  7 18:37:27 2024

@author: xi5400ya-s
"""

import multiprocessing
import os
import fcntl
import struct
from multiprocessing import Process
from circuitpython_nrf24l01.rf24 import RF24
import board
import digitalio as dio
import time
import argparse
from random import randint
import numpy as np
import spidev
import pytun
import threading
import queue
import rsa

tun_interface_name="tun0"
tun_ip = "192.168.1.1"
tun_netmask = "255.255.255.0"

# Initialize virtual interface
tun = pytun.TunTapDevice(name=tun_interface_name, flags=pytun.IFF_TUN | pytun.IFF_MULTI_QUEUE)
tun.addr = tun_ip
tun.netmask = tun_netmask
tun.mtu = 1500
tun.up()

# Create two queues to manage packets
tx_queue = multiprocessing.Queue()
rx_queue = multiprocessing.Queue()

# Encryption functions
def load_mobile_key_pair(private_key_file, public_key_file):
    with open(private_key_file, "rb") as f:
        mobile_private_key = rsa.PrivateKey.load_pkcs1(f.read())
    with open(public_key_file, "rb") as f:
        mobile_public_key = rsa.PublicKey.load_pkcs1_openssl_pem(f.read())
    return mobile_private_key, mobile_public_key

def load_base_station_public_key(public_key_file):
    with open(public_key_file, "rb") as f:
        base_station_public_key = rsa.PublicKey.load_pkcs1_openssl_pem(f.read())
    return base_station_public_key

# Load mobile device key pair
mobile_private_key, mobile_public_key = load_mobile_key_pair("/home/yaoi/mobile_private_key.pem", "/home/yaoi/mobile_public_key.pem")

# Load base station public key
base_station_public_key = load_base_station_public_key("/home/yaoi/base_station_public_key.pem")

def encrypt(data):
    return rsa.encrypt(data, base_station_public_key)

# Decryption function
def decrypt(data):
    return rsa.decrypt(data, mobile_private_key)

# Function to read data from TUN device and put it into the tx queue
def tun_reader(num):
    while True:
        # Read packet
        packet = tun.read(num)
        # print("Read packet from TUN:", len(packet), "Bytes")  # Debug: print the read packet
        # Put packet into the queue
        tx_queue.put(packet)
        # print("Put packet into tx_queue")  # Debug: print message when packet is put into the queue

# Function to get data from the rx queue and write it to the TUN device
def tun_writer():
    while True:
        packet = rx_queue.get()
        tun.write(packet)

def tx(nrf, channel, address, size):
    nrf.open_tx_pipe(address)  # set address of RX node into a TX pipe
    nrf.listen = False
    nrf.channel = channel

    while True:
        try:
            packet = tx_queue.get(timeout=1)  # Set timeout to 1 second
            # print("Got packet from queue:", packet)  # Debug: check if packet is successfully got from the queue
            
            if packet:
                # Add header and footer
                # print("Received data from TUN:", len(packet), "Bytes")
                packet_en = encrypt(packet)
                packet = bytes([0x00, 0x00]) + packet_en + bytes([0xFF, 0xFF])
                print("Sending packet:", len(packet), "Bytes")  # Print the packet to be sent
                # Split packet into 32-byte chunks
                chunks = [packet[i:i+32] for i in range(0, len(packet), 32)]
                # print(chunks)
                result = nrf.send(chunks)
                # print(result)
                # if not result:
                #    print("[T1] send() failed or timed out")
                time.sleep(0.1)
                print("Successful transmissions:", sum(result))
        except queue.Empty:
            print("Queue is empty")

def rx(nrf, channel, address):
    nrf.open_rx_pipe(0, address)
    nrf.listen = True  # Set the radio to receive mode and power on
    nrf.channel = channel
    print('Rx NRF24L01+ started, power: {}, SPI frequency: {} Hz'.format(nrf.pa_level, nrf.spi_frequency))

    received_data = b''  # Initialize an empty byte string to store received data
    start_time = time.monotonic()

    while True:
        if nrf.update() and nrf.pipe is not None:
            # Read received data from NRF24L01+
            received = nrf.read()
            received_data += received

            # Check if received data starts with header and ends with footer
            if received_data.startswith(b'\x00\x00') and received_data.endswith(b'\xff\xff'):
                process_complete_packet(received_data)
                received_data = b''  # Reset received data buffer
                start_time = time.monotonic()  # Reset timeout

        # Check for timeout
        if (time.monotonic() - start_time) >= 6:
            if received_data:
                print("Partial data received but not complete.")
                received_data = b''  # Reset received data buffer
            else:
                print("No packet received.")
            start_time = time.monotonic()  # Reset timeout

def process_complete_packet(packet):
    # Remove header and footer from the packet
    packet_data = packet[2:-2]
    packet_de = decrypt(packet_data)
    rx_queue.put(packet_de)
    print(packet_de)
    # Write received packet data to TUN device
    # tun.write(packet_data)
    print("Received complete packet:", len(packet_data), "Bytes")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='NRF24L01+ test')
    parser.add_argument('--src', dest='src', type=str, default='Node2', help='NRF24L01+\'s source address')
    parser.add_argument('--dst', dest='dst', type=str, default='Node1', help='NRF24L01+\'s destination address')
    parser.add_argument('--size', dest='size', type=int, default=32, help='Packet size')
    parser.add_argument('--txchannel', dest='txchannel', type=int, default=111, help='Tx channel', choices=range(0, 125))
    parser.add_argument('--rxchannel', dest='rxchannel', type=int, default=111, help='Rx channel', choices=range(0, 125))

    args = parser.parse_args()

    spi0 = spidev.SpiDev()
    spi1 = spidev.SpiDev()
    spi0.open(0, 0)
    spi1.open(1, 0)
    rx_nrf = RF24(spi0, 0, dio.DigitalInOut(board.D17))
    tx_nrf = RF24(spi1, 10, dio.DigitalInOut(board.D27))

    for nrf in [rx_nrf, tx_nrf]:
        nrf.data_rate = 2
        nrf.auto_ack = True
        nrf.payload_length = 32
        nrf.crc = True
        nrf.ack = 1
        nrf.spi_frequency = 20000000

tun_reader_process = multiprocessing.Process(target=tun_reader, args=(tun.mtu,))
tun_writer_process = multiprocessing.Process(target=tun_writer)

rx_process = multiprocessing.Process(target=rx, kwargs={'nrf': rx_nrf, 'address': bytes(args.src, 'utf-8'), 'channel': args.rxchannel})
tx_process = multiprocessing.Process(target=tx, kwargs={'nrf': tx_nrf, 'address': bytes(args.dst, 'utf-8'), 'channel': args.txchannel, 'size': args.size})

rx_process.start()
time.sleep(1)
tx_process.start()
tun_reader_process.start()
tun_writer_process.start()

rx_process.join()
tx_process.join()
tun_reader_process.join()
tun_writer_process.join()
