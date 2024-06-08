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

tun_interface_name="tun0"
tun_ip = "192.168.1.1"
tun_netmask = "255.255.255.0"


# Initialize virtual interface
tun = pytun.TunTapDevice(name=tun_interface_name, flags=pytun.IFF_TUN | pytun.IFF_MULTI_QUEUE)
tun.addr = tun_ip
tun.netmask = tun_netmask
tun.mtu = 1500
tun.up()

# Create two queues for managing packets
tx_queue = multiprocessing.Queue()
rx_queue = multiprocessing.Queue()


# Function to read data from TUN device and put into tx queue
def tun_reader(num):

    while True:
        # Read packet from TUN device
        packet = tun.read(num)
        # Put packet into queue
        tx_queue.put(packet)


# Function to get data from rx queue and write into TUN device
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
            packet = tx_queue.get(timeout=1)  # set timeout to 1 second

            if packet:
                packet = bytes([0x00, 0x00]) + packet + bytes([0xFF, 0xFF]) 
                print("Sending packet:", len(packet),"Bytes")
                chunks = [packet[i:i+32] for i in range(0, len(packet), 32)]
                result = nrf.send(chunks)
                time.sleep(0.1)
                print("Successful transmissions:", sum(result))    
        except queue.Empty:
            print("Queue is empty")

def rx(nrf, channel, address):
    nrf.open_rx_pipe(0, address)
    nrf.listen = True
    nrf.channel = channel
    print('Rx NRF24L01+ started, Power: {}, SPI frequency: {} Hz'.format(nrf.pa_level, nrf.spi_frequency))

    received_data = b''  
    start_time = time.monotonic()

    while True:
        if nrf.update() and nrf.pipe is not None:
            received = nrf.read()
            received_data += received

            if received_data.startswith(b'\x00\x00') and received_data.endswith(b'\xff\xff'):
                process_complete_packet(received_data)
                received_data = b''  
                start_time = time.monotonic()  

        if (time.monotonic() - start_time) >= 6:
            if received_data:
                print("Partial data received but not completed.")
                received_data = b''  
            else:
                print("No data packet received.")
            start_time = time.monotonic()  

def process_complete_packet(packet):
    packet_data = packet[2:-2]
    rx_queue.put(packet_data)
    print(packet_data)
    print("Received complete packet:", len(packet_data), "Bytes")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='NRF24L01+ test')
    parser.add_argument('--src', dest='src', type=str, default='Node2', help='NRF24L01+\'s source address')
    parser.add_argument('--dst', dest='dst', type=str, default='Node1', help='NRF24L01+\'s destination address')
    parser.add_argument('--size', dest='size', type=int, default=32, help='Packet size')
    parser.add_argument('--txchannel', dest='txchannel', type=int, default=111, help='Tx channel', choices=range(0,125))
    parser.add_argument('--rxchannel', dest='rxchannel', type=int, default=88, help='Rx channel', choices=range(0,125))

    args = parser.parse_args()

    spi0 = spidev.SpiDev()
    spi1 = spidev.SpiDev()
    spi0.open(0,0)
    spi1.open(1,0) 
    rx_nrf = RF24(spi0, 0, dio.DigitalInOut(board.D17))
    tx_nrf = RF24(spi1, 10, dio.DigitalInOut(board.D27))

    for nrf in [rx_nrf, tx_nrf]:
        nrf.data_rate = 2
        nrf.auto_ack = True
        nrf.payload_length = 32
        nrf.crc = True
        nrf.ack = 1
        nrf.spi_frequency = 20000000

tun_reader_process = multiprocessing.Process(target=tun_reader,args=(tun.mtu,))
tun_writer_process = multiprocessing.Process(target=tun_writer)

rx_process = multiprocessing.Process(target=rx, kwargs={'nrf':rx_nrf, 'address':bytes(args.src, 'utf-8'), 'channel': args.rxchannel})
tx_process = multiprocessing.Process(target=tx, kwargs={'nrf':tx_nrf, 'address':bytes(args.dst, 'utf-8'), 'channel': args.txchannel, 'size':args.size})

rx_process.start()
time.sleep(1)
tx_process.start()
tun_reader_process.start()
tun_writer_process.start()

rx_process.join()
tx_process.join()
tun_reader_process.join()
tun_writer_process.join()
