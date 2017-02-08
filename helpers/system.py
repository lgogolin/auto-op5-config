#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import fcntl
import struct
import re


# Get all real mountpoints for check_disk
def get_mount_points():
    mountpoints_array = []

    with open('/proc/mounts') as f:
        tmp_array = re.findall('^/dev.*', f.read(), re.MULTILINE)
        for item in tmp_array:
            mountpoints_array.append(item.split()[1])

        return mountpoints_array


# Get eth{x} interfaces name
def get_interface_name():
    with open('/proc/net/route') as f:
       for line in f.readlines():
            try:
                iface, dest, _, flags, _, _, _, _, _, _, _, =  line.strip().split()
                if dest != '00000000' or not int(flags, 16) & 2:
                    continue
                return iface
            except:
                continue 

# Get ip address for given network card
def get_ip_address(ifname):
    if ifname:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15]))[20:24])
    # In case that /proc/net/route does not have default dst
    else:
        return socket.gethostbyname(socket.gethostname())


# Get FQDN
def get_fqdn():
    return socket.gethostname()


def init(service_name, *service_parameters):

    # Initializie dictionary
    service_array = {}
    tmp_array = dict()

    # if service == check_disk, make loop over all mount points
    if service_name == "check_disk":
        for mount_point in get_mount_points():
            tmp_array['description'] = str(service_parameters[0]['description'] + " - " + mount_point)
            tmp_array['command'] = str(service_parameters[0]['command'] + service_parameters[0]['parameters'] + mount_point)
            service_array[mount_point] = dict()
            service_array[mount_point].update(tmp_array)

        return service_array
    else:
        tmp_array['description'] = str(service_parameters[0]['description'])
        tmp_array['command'] = str(service_parameters[0]['command'] + service_parameters[0]['parameters'])
        service_array[service_name] = dict()
        service_array[service_name].update(tmp_array)

        return service_array
