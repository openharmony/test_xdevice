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

from dataclasses import dataclass

from _core.config.config_manager import UserConfigManager
from _core.logger import platform_logger
from _core.logger import change_logger_level
from _core.plugin import Plugin
from _core.plugin import get_plugin
from _core.utils import convert_serial
from _core.constants import ProductForm
from _core.constants import ConfigConst
from _core.environment.device_state import DeviceAllocationState

__all__ = ["EnvironmentManager", "DeviceSelectionOption", "Environment"]

LOG = platform_logger("ManagerEnv")


class Environment(object):
    """
    Environment required for each dispatch
    """
    device_mapper = {
        ProductForm.phone: "Phone",
        ProductForm.tablet: "Tablet",
        ProductForm.car: "Car",
        ProductForm.television: "Tv",
        ProductForm.watch: "Watch",
        }

    def __init__(self):
        self.devices = []
        self.phone = 0
        self.wifiiot = 0
        self.ipcamera = 0
        self.device_recorder = dict()

    def __get_serial__(self):
        device_serials = []
        for device in self.devices:
            device_serials.append(convert_serial(device.__get_serial__()))
        return ";".join(device_serials)

    def get_devices(self):
        return self.devices

    def check_serial(self):
        if self.__get_serial__():
            return True
        return False

    def add_device(self, device, index=None):
        label = self.device_mapper.get(device.label, "DUT")
        if index:
            current = index
        else:
            current = self.device_recorder.get(label, 0) + 1
        device.device_id = "%s%s" % (label, current)
        LOG.debug("add_device, sn: {}, id: {}".format(device.device_sn, device.device_id))
        self.device_recorder.update({label: current})
        self.devices.append(device)


class EnvironmentManager(object):
    """
    Class representing environment manager that
    managing the set of available devices for testing
    """
    __instance = None
    __init_flag = False

    def __new__(cls, *args, **kwargs):
        """
        Singleton instance
        """
        del args, kwargs
        if cls.__instance is None:
            cls.__instance = super(EnvironmentManager, cls).__new__(cls)
        return cls.__instance

    def __init__(self, environment="", user_config_file=""):
        if EnvironmentManager.__init_flag:
            return
        self.managers = {}
        self.env_start(environment, user_config_file)
        EnvironmentManager.__init_flag = True

    def env_start(self, environment="", user_config_file=""):

        log_level_dict = UserConfigManager(
            config_file=user_config_file, env=environment).get_log_level()
        if log_level_dict:
            # change log level when load or reset EnvironmentManager object
            change_logger_level(log_level_dict)

        manager_plugins = get_plugin(Plugin.MANAGER)
        for manager_plugin in manager_plugins:
            try:
                manager_instance = manager_plugin.__class__()
                manager_instance.init_environment(environment,
                                                  user_config_file)
                self.managers[manager_instance.__class__.__name__] = \
                    manager_instance
            except Exception as error:
                LOG.debug("Env start error: %s" % error)
        if len(self.managers):
            self.managers = dict(sorted(self.managers.items(), reverse=True))

    def env_stop(self):
        for manager in self.managers.values():
            manager.env_stop()
            manager.devices_list = []
        self.managers = {}

        EnvironmentManager.__init_flag = False

    def env_reset(self):
        for manager in self.managers.values():
            manager.env_reset()

    def apply_environment(self, device_options):
        environment = Environment()
        for device_option in device_options:
            LOG.debug("Visit options to find device")
            device = self.apply_device(device_option)
            if device is not None:
                index = self.get_config_device_index(device)
                environment.add_device(device, index)
                device.extend_value = device_option.extend_value
                LOG.debug("Device %s: extend value: %s", convert_serial(
                    device.device_sn), device.extend_value)
            else:
                LOG.debug("Require label is '%s', then next" %
                          device_option.label)
        return environment

    def release_environment(self, environment):
        for device in environment.devices:
            device.extend_value = {}
            self.release_device(device)

    def apply_device(self, device_option, timeout=10):
        LOG.debug("Apply device from managers:%s" % self.managers)
        for manager_type, manager in self.managers.items():
            support_labels = getattr(manager, "support_labels", [])
            support_types = getattr(manager, "support_types", [])
            if device_option.required_manager not in support_types:
                LOG.warning("'%s' not in %s's support types" % (
                    device_option.required_manager, manager_type))
                continue
            if not support_labels:
                continue
            if device_option.label is None:
                if manager_type != "ManagerDevice" and \
                        manager_type != "ManagerAospDevice":
                    continue
            else:
                if support_labels and \
                        device_option.label not in support_labels:
                    continue
            device = manager.apply_device(device_option, timeout)
            if hasattr(device, "env_index"):
                device.env_index = device_option.get_env_index()
            if device:
                return device
        else:
            return None

    def get_config_device_index(self, device):
        if device and hasattr(device, "device_sn"):
            sn = device.device_sn
            for manager in self.managers.items():
                if hasattr(manager[1], "global_device_filter"):
                    index = 1
                    for s in manager[1].global_device_filter:
                        if s == sn:
                            return index
                        else:
                            index += 1
        return None

    def check_device_exist(self, device_options):
        """
        Check if there are matched devices which can be allocated or available.
        """
        devices = []
        for device_option in device_options:
            for manager_type, manager in self.managers.items():
                support_labels = getattr(manager, "support_labels", [])
                support_types = getattr(manager, "support_types", [])
                if device_option.required_manager not in support_types:
                    continue
                if device_option.label is None:
                    if manager_type != "ManagerDevice" and \
                        manager_type != "ManagerAospDevice":
                        continue
                else:
                    if support_labels and \
                            device_option.label not in support_labels:
                        continue
                for device in manager.devices_list:
                    if device.device_sn in devices:
                        continue
                    if device_option.matches(device, False):
                        devices.append(device.device_sn)
                        break
                else:
                    continue
                break
            else:
                return False
        return True

    def release_device(self, device):
        for manager in self.managers.values():
            if device in manager.devices_list:
                manager.release_device(device)

    def list_devices(self):
        LOG.info("List devices.")
        for manager in self.managers.values():
            manager.list_devices()


class DeviceSelectionOption(object):
    """
    Class representing device selection option
    """

    def __init__(self, options, label=None, test_source=None):
        self.device_sn = [x for x in options["device_sn"].split(";") if x]
        self.label = label
        self.test_driver = test_source.test_type
        self.source_file = ""
        self.extend_value = {}
        self.required_manager = ""
        self.required_component = ""
        self.env_index = None

    def get_label(self):
        return self.label

    def get_env_index(self):
        return self.env_index

    def matches(self, device, allocate=True):
        LOG.debug("Do matches, device:{state:%s, sn:%s, label:%s}, selection "
                  "option:{device sn:%s, label:%s}" % (
                   device.device_allocation_state,
                   convert_serial(device.device_sn),
                   device.label,
                   [convert_serial(sn) if sn else "" for sn in self.device_sn],
                   self.label))
        if not getattr(device, "task_state", True):
            return False
        if allocate and device.device_allocation_state != \
                DeviceAllocationState.available:
            return False

        if not allocate:
            if device.device_allocation_state != \
                    DeviceAllocationState.available and \
                    device.device_allocation_state != \
                    DeviceAllocationState.allocated:
                return False

        if len(self.device_sn) != 0 and device.device_sn not in self.device_sn:
            return False

        if self.label and self.label != device.label:
            return False
        if self.required_component and \
                hasattr(device, ConfigConst.support_component):
            subsystems, parts = getattr(device, ConfigConst.support_component)
            required_subsystems, require_part = self.required_component
            if required_subsystems not in subsystems and \
                    require_part not in parts:
                return False
        return True
