#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2022 Huawei Device Co., Ltd.
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

import os
import platform
import subprocess
import sys

from xdevice import IDriver
from xdevice import Plugin
from xdevice import platform_logger
from xdevice import get_device_log_file
from xdevice import JsonParser
from xdevice import get_config_value
from xdevice import FilePermission
from xdevice import get_decode

HOMEVISION_TEST = "HomeVision"
LOG = platform_logger(HOMEVISION_TEST)


@Plugin(type=Plugin.DRIVER, id=HOMEVISION_TEST)
class HomeVisionTest(IDriver):
    """
    HomeVisionTest is a Test that runs a driver test on given tv devices.
    """
    # test driver config
    config = None
    result = ""

    def __check_environment__(self, device_options):
        pass

    def __check_config__(self, config):
        pass

    def __execute__(self, request):
        self.config = request.config
        self.config.device = request.get_devices()[0]
        self.config.devices = request.get_devices()

        # get config file
        config_file = request.get_config_file()
        if not config_file:
            LOG.error("Config file not exists")
            return
        LOG.debug("HomeVisionTest config file Path: %s" % config_file)

        device_log_pipes = []
        try:
            for device in self.config.devices:
                device_name = device.get("name", "")
                device_log = get_device_log_file(
                    request.config.report_path, device.__get_serial__(),
                    "device_log", device_name)
                hilog = get_device_log_file(
                    request.config.report_path, device.__get_serial__(),
                    "device_hilog", device_name)

                device_log_open = os.open(device_log, os.O_WRONLY |
                                          os.O_CREAT | os.O_APPEND,
                                          FilePermission.mode_755)
                hilog_open = os.open(hilog, os.O_WRONLY | os.O_CREAT |
                                     os.O_APPEND, FilePermission.mode_755)

                device_log_pipe = os.fdopen(device_log_open, "a")
                hilog_pipe = os.fdopen(hilog_open, "a")
                device.start_catch_device_log(device_log_pipe, hilog_pipe)
                device_log_pipes.extend([device_log_pipe, hilog_pipe])

            self._run_homevision_test(config_file)
        finally:
            for device_log_pipe in device_log_pipes:
                device_log_pipe.flush()
                device_log_pipe.close()
            for device in self.config.devices:
                device.stop_catch_device_log()

    @classmethod
    def _run_homevision_test(cls, config_file):
        from xdevice import Variables
        # insert RegressionTest path for loading homevision module
        homevision_test_module = os.path.join(Variables.exec_dir,
                                              "RegressionTest")
        sys.path.insert(1, homevision_test_module)
        json_config = JsonParser(config_file)
        device_ip = get_config_value("device-ip", json_config.get_driver(),
                                     False)
        job_id = get_config_value("job-id", json_config.get_driver(), False)
        home_vision_app_name = get_config_value(
            "home-vision-app-name", json_config.get_driver(), False)

        cmd_parts = []
        if platform.system() == "Windows":
            cmd_parts.append("python")
        else:
            cmd_parts.append("python3")
        relative_path = "startAutoTest.py"
        cmd_parts.append(os.path.abspath(os.path.join(homevision_test_module,
                                         relative_path)))
        cmd_parts.append(device_ip)
        cmd_parts.append(job_id)
        cmd_parts.append(home_vision_app_name)
        cmd = " ".join(cmd_parts)
        LOG.info("Start HomeVision test with cmd: %s" % cmd)
        try:
            proc = subprocess.Popen(cmd_parts, shell=False,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            (out, _) = proc.communicate()
            out = get_decode(out).strip()
            for line in out.split("\n"):
                LOG.info(line)
        except (subprocess.CalledProcessError, FileNotFoundError,
                Exception) as error:
            LOG.error("HomeVision test error: %s" % error)

    def __result__(self):
        return self.result if os.path.exists(self.result) else ""
