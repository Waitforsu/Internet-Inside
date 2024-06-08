
# -*- coding: utf-8 -*-
"""
Created on Wed May  8 16:28:49 2024

@author: fa2160mo-s
"""


import os
import struct
import time
import subprocess
from circuitpython_nrf24l01.rf24 import RF24
import digitalio as dio
import spidev
import threading
from multiprocessing import Process
from argparse import ArgumentParser
import numpy as np
import board        
from setup import TunTapDevice
import socket
from scapy.all import *
import pytun
import rsa
from Crypto.PublicKey import RSA
import concurrent.futures

executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


tun_interface_name = "tun1"
tun_ip = "192.168.1.2"
tun_netmask = "255.255.255.0"
tun_mtu = 1500
CE0 = dio.DigitalInOut(board.D17)
CSN0 = 0
CE1 = dio.DigitalInOut(board.D27)
CSN1 = 10

# initialize virtual interface

tun = pytun.TunTapDevice(name=tun_interface_name, flags=pytun.IFF_TUN | pytun.IFF_MULTI_QUEUE)
tun.addr = tun_ip
tun.netmask = tun_netmask
tun.mtu = 1500
tun.up()
# 执行设置TUN设备的命令
commands = [
f'sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE', 
f'sudo iptables -A FORWARD -i eth0 -o {tun_interface_name} -m state --state RELATED,ESTABLISHED -m limit --limit 20/sec -j ACCEPT ',
f'sudo iptables -A FORWARD -i {tun_interface_name} -o eth0 -j ACCEPT'  ]

for cmd in commands:
    print("ip route set")
    subprocess.run(cmd, shell=True, check=True)

def load_mobile_public_key(public_key_file):

    with open(public_key_file, "rb") as f:
        mobile_public_key =  rsa.PublicKey.load_pkcs1_openssl_pem(f.read())
    return mobile_public_key


def load_base_station_key_pair(private_key_file, public_key_file):
    with open(private_key_file, "rb") as f:
        base_station_private_key = rsa.PrivateKey.load_pkcs1(f.read())
    with open(public_key_file, "rb") as f:
        base_station_public_key = rsa.PublicKey.load_pkcs1_openssl_pem(f.read())
    return base_station_private_key, base_station_public_key

base_station_private_key, base_station_public_key = load_base_station_key_pair("/home/mo/base_station_private_key.pem", "/home/mo/base_station_public_key.pem")
mobile_public_key = load_mobile_public_key("/home/mo/mobile_public_key.pem")
 
def encrypt(data):
    return rsa.encrypt(data,mobile_public_key)
def decrypt(data):
    return rsa.decrypt(data,base_station_private_key)


def tx(nrf, channel, address, count, size, tun):
    nrf.open_tx_pipe(address)
    nrf.listen = False
    nrf.channel = channel
    status = []
    buffer = []  

    
    while True:

        data = tun.read(tun_mtu)
        data = encrypt(data)
              
        if len(data) < 40:    
            print("response is ", data)
        if data is None:
            print("No data received")
        else:
            #print("this is received data from Ethernet/self :")
            chunks = data_nrf(data)
            print("send reply data into nrf")
            result = nrf.send(chunks)
            print(result)

def rx(nrf, channel, address, size, tun):
    nrf.open_rx_pipe(0, address)
    nrf.listen = True
    nrf.channel = channel
    packet = []
    count = 0
    while True:
        while nrf.available():
            print("Now basesation received data...")
            packet.append(nrf.read())
            if packet[0].startswith(b'\x00\x00') and packet[-1].endswith(b'\xff\xff'):
                count = count + 1
                print('icmp request packet received ', count)

                result_list = [b"".join(packet)]
                re_result = result_list[0][2:-2]
                re_result = decrypt(re_result)
                print("data joined, write data into virtual interface.....")
                tun.write(bytes(re_result))
                packet = []

def data_nrf(data):
    l = len(data)
    header = bytes([0b00000000])+bytes([0b00000000]) #creat header
    footer = bytes([0b11111111])+bytes([0b11111111]) #creat footer
    data = header + data + footer 
    chunk_size = 32
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    return chunks

if __name__ == "__main__":
    parser = ArgumentParser(description='NRF24L01+ test')
    parser.add_argument('--src', dest='src', type=str, default='Node1', help='NRF24L01+\'s source address')
    parser.add_argument('--dst', dest='dst', type=str, default='Node2', help='NRF24L01+\'s destination address')
    parser.add_argument('--count', dest='cnt', type=int, default=0, help='Number of transmissions')
    parser.add_argument('--size', dest='size', type=int, default=32, help='Packet size')
    parser.add_argument('--txchannel', dest='txchannel', type=int, default=111, help='Tx channel', choices=range(0,125))
    parser.add_argument('--rxchannel', dest='rxchannel', type=int, default=111, help='Rx channel', choices=range(0,125))
    args = parser.parse_args()

    spi0 = spidev.SpiDev()
    spi1 = spidev.SpiDev()
    spi0.open(0, 0)  # Specify the bus number and device number for SPI0
    spi1.open(1, 0)  # Specify the bus number and device number for SPI1

    rx_nrf = RF24(spi0, CSN0, CE0)
    tx_nrf = RF24(spi1, CSN1, CE1)


    for nrf in [rx_nrf, tx_nrf]:
        nrf.data_rate = 2
        nrf.auto_ack = True
        nrf.payload_length = 32
#        nrf.dynamic_payloads = True
        nrf.crc = True
        nrf.ack = 1
        nrf.spi_frequency = 20000000

    rx_process = Process(target=rx, kwargs={'nrf':rx_nrf, 'channel': args.rxchannel, 'address':bytes(args.src, 'utf-8'), 'size': args.size, 'tun': tun})
    tx_process = Process(target=tx, kwargs={'nrf':tx_nrf, 'channel': args.txchannel, 'address':bytes(args.dst, 'utf-8'), 'count': args.cnt, 'size': args.size, 'tun': tun})

    rx_process.start()
    time.sleep(1)
    tx_process.start()

    tx_process.join()
    rx_process.join()
