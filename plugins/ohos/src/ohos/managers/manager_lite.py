#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2020-2022 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import time
import threading

from xdevice import UserConfigManager
from xdevice import DeviceOsType
from xdevice import ManagerType
from xdevice import DeviceAllocationState
from xdevice import Plugin
from xdevice import get_plugin
from xdevice import IDeviceManager
from xdevice import platform_logger
from xdevice import convert_ip
from xdevice import convert_port
from xdevice import convert_serial

from ohos.exception import LiteDeviceError

__all__ = ["ManagerLite"]

LOG = platform_logger("ManagerLite")


@Plugin(type=Plugin.MANAGER, id=ManagerType.lite_device)
class ManagerLite(IDeviceManager):
    """
    Class representing device manager that
    managing the set of available devices for testing
    """

    def __init__(self):
        self.devices_list = []
        self.list_con = threading.Condition()
        self.support_labels = ["ipcamera", "wifiiot", "watchGT"]
        self.support_types = ["device"]

    def init_environment(self, environment="", user_config_file=""):
        device_lite = get_plugin(plugin_type=Plugin.DEVICE,
                                 plugin_id=DeviceOsType.lite)[0]

        devices = UserConfigManager(
            config_file=user_config_file, env=environment).get_com_device(
            "environment/device")

        for device in devices:
            try:
                device_lite_instance = device_lite.__class__()
                device_lite_instance.__init_device__(device)
                device_lite_instance.device_allocation_state = \
                    DeviceAllocationState.available
            except LiteDeviceError as exception:
                LOG.warning(exception)
                continue

            self.devices_list.append(device_lite_instance)

    def env_stop(self):
        pass

    def apply_device(self, device_option, timeout=10):
        """
        Request a device for testing that meets certain criteria.
        """
        del timeout
        LOG.debug("Lite apply device: apply lock")
        self.list_con.acquire()
        try:
            allocated_device = None
            for device in self.devices_list:
                if device_option.matches(device):
                    device.device_allocation_state = \
                        DeviceAllocationState.allocated
                    LOG.debug("Allocate device sn: %s, type: %s" % (
                        convert_serial(device.__get_serial__()),
                        device.__class__))
                    return device
            time.sleep(10)
            return allocated_device
        finally:
            LOG.debug("Lite apply device: release lock")
            self.list_con.release()

    def release_device(self, device):
        LOG.debug("Lite release device: apply lock")
        self.list_con.acquire()
        try:
            if device.device_allocation_state == \
                    DeviceAllocationState.allocated:
                device.device_allocation_state = \
                    DeviceAllocationState.available
            LOG.debug("Free device sn: %s, type: %s" % (
                device.__get_serial__(), device.__class__))
        finally:
            LOG.debug("Lite release device: release lock")
            self.list_con.release()

    def list_devices(self):
        print("Lite devices:")
        print("{0:<20}{1:<16}{2:<16}{3:<16}{4:<16}{5:<16}{6:<16}".
              format("SerialPort/IP", "Baudrate/Port", "OsType", "Allocation",
                     "Product", "ConnectType", "ComType"))
        for device in self.devices_list:
            if device.device_connect_type == "remote" or \
                    device.device_connect_type == "agent":
                print("{0:<20}{1:<16}{2:<16}{3:<16}{4:<16}{5:<16}".format(
                    convert_ip(device.device.host),
                    convert_port(device.device.port),
                    device.device_os_type,
                    device.device_allocation_state,
                    device.label,
                    device.device_connect_type))
            else:
                for com_controller in device.device.com_dict:
                    print("{0:<20}{1:<16}{2:<16}{3:<16}{4:<16}{5:<16}{6:<16}".
                          format(convert_port(device.device.com_dict[
                                     com_controller].serial_port),
                                 device.device.com_dict[
                                     com_controller].baud_rate,
                                 device.device_os_type,
                                 device.device_allocation_state,
                                 device.label,
                                 device.device_connect_type,
                                 com_controller))
