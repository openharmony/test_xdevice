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

import time
import os
import threading
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from xdevice import DeviceOsType
from xdevice import ProductForm
from xdevice import ReportException
from xdevice import IDevice
from xdevice import platform_logger
from xdevice import Plugin
from xdevice import exec_cmd
from xdevice import ConfigConst
from xdevice import HdcError
from xdevice import DeviceAllocationState
from xdevice import convert_serial
from xdevice import check_path_legal
from xdevice import start_standing_subprocess
from xdevice import stop_standing_subprocess

from ohos.environment.dmlib import HdcHelper
from ohos.environment.dmlib import CollectingOutputReceiver

__all__ = ["Device"]
TIMEOUT = 300 * 1000
RETRY_ATTEMPTS = 2
DEFAULT_UNAVAILABLE_TIMEOUT = 20 * 1000
BACKGROUND_TIME = 2 * 60 * 1000
LOG = platform_logger("Device")
DEVICETEST_HAP_PACKAGE_NAME = "com.ohos.devicetest"
UITEST_NAME = "uitest"
NATIVE_CRASH_PATH = "/data/log/faultlog/temp"
JS_CRASH_PATH = "/data/log/faultlog/faultlogger"
ROOT_PATH = "/data/log/faultlog"


def perform_device_action(func):
    def callback_to_outer(device, msg):
        # callback to decc ui
        if getattr(device, "callback_method", None):
            device.callback_method(msg)

    def device_action(self, *args, **kwargs):
        if not self.get_recover_state():
            LOG.debug("Device %s %s is false" % (self.device_sn,
                                                 ConfigConst.recover_state))
            return
        # avoid infinite recursion, such as device reboot
        abort_on_exception = bool(kwargs.get("abort_on_exception", False))
        if abort_on_exception:
            result = func(self, *args, **kwargs)
            return result

        tmp = int(kwargs.get("retry", RETRY_ATTEMPTS))
        retry = tmp + 1 if tmp > 0 else 1
        exception = None
        for _ in range(retry):
            try:
                result = func(self, *args, **kwargs)
                return result
            except ReportException as error:
                self.log.exception("Generate report error!", exc_info=False)
                exception = error
            except (ConnectionResetError, ConnectionRefusedError) as error:
                self.log.error("error type: %s, error: %s" %
                               (error.__class__.__name__, error))
                cmd = "hdc_std target boot"
                self.log.info("re-execute hdc reset")
                exec_cmd(cmd)
                callback_to_outer(self, "error:%s, prepare to recover" % error)
                if not self.recover_device():
                    LOG.debug("Set device %s %s false" % (
                        self.device_sn, ConfigConst.recover_state))
                    self.set_recover_state(False)
                    callback_to_outer(self, "recover failed")
                    raise error
                exception = error
                callback_to_outer(self, "recover success")
            except HdcError as error:
                self.log.error("error type: %s, error: %s" %
                               (error.__class__.__name__, error))
                callback_to_outer(self, "error:%s, prepare to recover" % error)
                if not self.recover_device():
                    LOG.debug("Set device %s %s false" % (
                        self.device_sn, ConfigConst.recover_state))
                    self.set_recover_state(False)
                    callback_to_outer(self, "recover failed")
                    raise error
                exception = error
                callback_to_outer(self, "recover success")
            except Exception as error:
                self.log.exception("error type: %s, error: %s" % (
                    error.__class__.__name__, error), exc_info=False)
                exception = error
        raise exception

    return device_action


@Plugin(type=Plugin.DEVICE, id=DeviceOsType.default)
class Device(IDevice):
    """
    Class representing a device.

    Each object of this class represents one device in xDevice,
    including handles to hdc, fastboot, and test agent (DeviceTest.apk).

    Attributes:
        device_sn: A string that's the serial number of the device.
    """

    device_sn = None
    host = None
    port = None
    usb_type = None
    is_timeout = False
    device_log_proc = None
    device_hilog_proc = None
    device_os_type = DeviceOsType.default
    test_device_state = None
    device_allocation_state = DeviceAllocationState.available
    label = None
    log = platform_logger("Device")
    device_state_monitor = None
    reboot_timeout = 2 * 60 * 1000
    log_file_pipe = None
    hilog_file_pipe = None

    _proxy = None
    _is_harmony = None
    initdevice = True
    d_port = 8009
    _uitestdeamon = None
    rpc_timeout = 300
    device_id = None
    reconnecttimes = 0
    _h_port = None
    screenshot = False
    screenshot_fail = True
    module_package = None
    module_ablity_name = None

    model_dict = {
        'default': ProductForm.phone,
        'car': ProductForm.car,
        'tv': ProductForm.television,
        'watch': ProductForm.watch,
        'tablet': ProductForm.tablet,
        'nosdcard': ProductForm.phone
    }

    def __init__(self):
        self.extend_value = {}
        self.device_lock = threading.RLock()
        self.forward_ports = []

    @property
    def is_hw_root(self):
        if self.is_harmony:
            return True

    def __eq__(self, other):
        return self.device_sn == other.__get_serial__() and \
               self.device_os_type == other.device_os_type

    def __set_serial__(self, device_sn=""):
        self.device_sn = device_sn
        return self.device_sn

    def __get_serial__(self):
        return self.device_sn

    def get(self, key=None, default=None):
        if not key:
            return default
        value = getattr(self, key, None)
        if value:
            return value
        else:
            return self.extend_value.get(key, default)

    def recover_device(self):
        if not self.get_recover_state():
            LOG.debug("Device %s %s is false, cannot recover device" % (
                self.device_sn, ConfigConst.recover_state))
            return

        LOG.debug("Wait device %s to recover" % self.device_sn)
        return self.device_state_monitor.wait_for_device_available()

    def get_device_type(self):
        self.label = self.model_dict.get("default", None)

    def get_property(self, prop_name, retry=RETRY_ATTEMPTS,
                     abort_on_exception=False):
        """
        Hdc command, ddmlib function.
        """
        command = "param get %s" % prop_name
        stdout = self.execute_shell_command(command, timeout=5 * 1000,
                                            output_flag=False,
                                            retry=retry,
                                            abort_on_exception=
                                            abort_on_exception).strip()
        if stdout:
            LOG.debug(stdout)
        return stdout

    @perform_device_action
    def connector_command(self, command, **kwargs):
        timeout = int(kwargs.get("timeout", TIMEOUT)) / 1000
        error_print = bool(kwargs.get("error_print", True))
        join_result = bool(kwargs.get("join_result", False))
        timeout_msg = '' if timeout == 300.0 else \
            " with timeout %ss" % timeout
        if self.host != "127.0.0.1":
            cmd = ["hdc_std", "-s", "{}:{}".format(self.host, self.port)]
        else:
            cmd = ["hdc_std", "-t", self.device_sn]
        LOG.debug("%s execute command hdc %s%s" % (
            convert_serial(self.device_sn), command, timeout_msg))
        if isinstance(command, list):
            cmd.extend(command)
        else:
            command = command.strip()
            cmd.extend(command.split(" "))
        result = exec_cmd(cmd, timeout, error_print, join_result)
        if not result:
            return result
        for line in str(result).split("\n"):
            if line.strip():
                LOG.debug(line.strip())
        return result

    @perform_device_action
    def execute_shell_command(self, command, timeout=TIMEOUT,
                              receiver=None, **kwargs):
        if not receiver:
            collect_receiver = CollectingOutputReceiver()
            HdcHelper.execute_shell_command(
                self, command, timeout=timeout,
                receiver=collect_receiver, **kwargs)
            return collect_receiver.output
        else:
            return HdcHelper.execute_shell_command(
                self, command, timeout=timeout,
                receiver=receiver, **kwargs)

    def execute_shell_cmd_background(self, command, timeout=TIMEOUT,
                                     receiver=None):
        status = HdcHelper.execute_shell_command(self, command,
                                                 timeout=timeout,
                                                 receiver=receiver)

        self.wait_for_device_not_available(DEFAULT_UNAVAILABLE_TIMEOUT)
        self.device_state_monitor.wait_for_device_available(BACKGROUND_TIME)
        cmd = "target mount"
        self.connector_command(cmd)
        self.start_catch_device_log()
        return status

    def wait_for_device_not_available(self, wait_time):
        return self.device_state_monitor.wait_for_device_not_available(
            wait_time)

    def _wait_for_device_online(self, wait_time=None):
        return self.device_state_monitor.wait_for_device_online(wait_time)

    def _do_reboot(self):
        HdcHelper.reboot(self)
        self.wait_for_boot_completion()

    def _reboot_until_online(self):
        self._do_reboot()
        self._wait_for_device_online()

    def reboot(self):
        self._reboot_until_online()
        self.device_state_monitor.wait_for_device_available(
            self.reboot_timeout)
        self.enable_hdc_root()

    @perform_device_action
    def install_package(self, package_path, command=""):
        if package_path is None:
            raise HdcError(
                "install package: package path cannot be None!")
        return HdcHelper.install_package(self, package_path, command)

    @perform_device_action
    def uninstall_package(self, package_name):
        return HdcHelper.uninstall_package(self, package_name)

    @perform_device_action
    def push_file(self, local, remote, **kwargs):
        """
        Push a single file.
        The top directory won't be created if is_create is False (by default)
        and vice versa
        """
        if local is None:
            raise HdcError("XDevice Local path cannot be None!")

        remote_is_dir = kwargs.get("remote_is_dir", False)
        if remote_is_dir:
            ret = self.execute_shell_command("test -d %s && echo 0" % remote)
            if not (ret != "" and len(str(ret).split()) != 0 and
                    str(ret).split()[0] == "0"):
                self.execute_shell_command("mkdir -p %s" % remote)

        if self.host != "127.0.0.1":
            self.connector_command("file send {} {}".format(local, remote))
        else:
            is_create = kwargs.get("is_create", False)
            timeout = kwargs.get("timeout", TIMEOUT)
            HdcHelper.push_file(self, local, remote, is_create=is_create,
                                timeout=timeout)
        if not self.is_file_exist(remote):
            LOG.error("Push %s to %s failed" % (local, remote))
            raise HdcError("push %s to %s failed" % (local, remote))

    @perform_device_action
    def pull_file(self, remote, local, **kwargs):
        """
        Pull a single file.
        The top directory won't be created if is_create is False (by default)
        and vice versa
        """
        if self.host != "127.0.0.1":
            self.connector_command("file recv {} {}".format(remote, local))
        else:
            is_create = kwargs.get("is_create", False)
            timeout = kwargs.get("timeout", TIMEOUT)
            HdcHelper.pull_file(self, remote, local, is_create=is_create,
                                timeout=timeout)

    def enable_hdc_root(self):
        return True

    def is_directory(self, path):
        path = check_path_legal(path)
        output = self.execute_shell_command("ls -ld {}".format(path))
        if output and output.startswith('d'):
            return True
        return False

    def is_file_exist(self, file_path):
        file_path = check_path_legal(file_path)
        output = self.execute_shell_command("ls {}".format(file_path))
        if output and "No such file or directory" not in output:
            return True
        return False

    def start_catch_device_log(self, log_file_pipe=None,
                               hilog_file_pipe=None):
        """
        Starts hdc log for each device in separate subprocesses and save
        the logs in files.
        """
        self._sync_device_time()
        if log_file_pipe:
            self.log_file_pipe = log_file_pipe
        if hilog_file_pipe:
            self.hilog_file_pipe = hilog_file_pipe
        self._start_catch_device_log()

    def stop_catch_device_log(self):
        """
        Stops all hdc log subprocesses.
        """
        self._stop_catch_device_log()

    def _start_catch_device_log(self):
        if self.hilog_file_pipe:
            command = "hilog"
            cmd = ['hdc_std', "-t", self.device_sn, "shell", command]
            LOG.info("execute command: %s" % " ".join(cmd).replace(
                self.device_sn, convert_serial(self.device_sn)))
            self.device_hilog_proc = start_standing_subprocess(
                cmd, self.hilog_file_pipe)

    def _stop_catch_device_log(self):
        if self.device_log_proc:
            if not HdcHelper.is_hdc_std():
                stop_standing_subprocess(self.device_log_proc)
            self.device_log_proc = None
            self.log_file_pipe = None
        if self.device_hilog_proc:
            stop_standing_subprocess(self.device_hilog_proc)
            self.device_hilog_proc = None
            self.hilog_file_pipe = None

    def start_hilog_task(self):
        self._clear_crash_log()
        # 先停止一下
        cmd = "hilog -w stop"
        out = self.execute_shell_command(cmd)
        # 清空日志
        cmd = "hilog -r"
        out = self.execute_shell_command(cmd)
        cmd = "rm -rf /data/log/hilog/*"
        out = self.execute_shell_command(cmd)
        # 开始日志任务 设置落盘文件个数最大值1000，链接https://gitee.com/openharmony/hiviewdfx_hilog
        cmd = "hilog -w start -n 1000"
        out = self.execute_shell_command(cmd)
        LOG.info("Execute command: {}, result is {}".format(cmd, out))

    def stop_hilog_task(self, log_name):
        cmd = "hilog -w stop"
        out = self.execute_shell_command(cmd)
        # 把hilog文件夹下所有文件拉出来 由于hdc不支持整个文件夹拉出只能采用先压缩再拉取文件
        cmd = "tar -zcvf /data/log/hilog_{}.tar.gz /data/log/hilog/".format(log_name)
        out = self.execute_shell_command(cmd)
        LOG.info("Execute command: {}, result is {}".format(cmd, out))
        self.pull_file("/data/log/hilog_{}.tar.gz".format(log_name), "{}/log/".format(self._device_log_path))
        cmd = "rm -rf /data/log/hilog_{}.tar.gz".format(log_name)
        out = self.execute_shell_command(cmd)
        # 获取crash日志
        self._start_get_crash_log(log_name)

    def _get_log(self, log_cmd, *params):
        def filter_by_name(log_name, args):
            for starts_name in args:
                if log_name.startswith(starts_name):
                    return True
            return False

        data_list = list()
        log_name_array = list()
        log_result = self.execute_shell_command(log_cmd)
        if log_result is not None and len(log_result) != 0:
            log_name_array = log_result.strip().replace("\r", "").split("\n")
        for log_name in log_name_array:
            log_name = log_name.strip()
            if len(params) == 0 or \
                    filter_by_name(log_name, params):
                data_list.append(log_name)
        return data_list

    def get_cur_crash_log(self, crash_path, log_name):
        log_name_map = {'cppcrash': NATIVE_CRASH_PATH,
                        "jscrash": JS_CRASH_PATH,
                        "SERVICE_BLOCK": ROOT_PATH,
                        "appfreeze": ROOT_PATH}
        if not os.path.exists(crash_path):
            os.makedirs(crash_path)
        if "Not support std mode" in log_name:
            return

        def get_log_path(logname):
            name_array = logname.split("-")
            if len(name_array) <= 1:
                return ROOT_PATH
            return log_name_map.get(name_array[0])

        log_path = get_log_path(log_name)
        temp_path = "%s/%s" % (log_path, log_name)
        self.pull_file(temp_path, crash_path)
        LOG.debug("Finish pull file: %s" % log_name)

    def _start_get_crash_log(self, task_name):
        log_array = list()
        native_crash_cmd = "ls /data/log/faultlog/temp"
        js_crash_cmd = '"ls /data/log/faultlog/faultlogger | grep jscrash"'
        block_crash_cmd = '"ls /data/log/faultlog/"'

        # 获取crash日志文件
        log_array.extend(self._get_log(native_crash_cmd, "cppcrash"))
        log_array.extend(self._get_log(js_crash_cmd, "jscrash"))
        log_array.extend(self._get_log(block_crash_cmd, "SERVICE_BLOCK", "appfreeze"))
        LOG.debug("crash log file {}, length is {}".format(str(log_array), str(len(log_array))))
        crash_path = "{}/log/crash_log_{}/".format(self._device_log_path, task_name)
        for log_name in log_array:
            log_name = log_name.strip()
            self.get_cur_crash_log(crash_path, log_name)

    def _clear_crash_log(self):
        self._sync_device_time()
        clear_block_crash_cmd = "rm -rf /data/log/faultlog/"
        self.execute_shell_command(clear_block_crash_cmd)
        mkdir_block_crash_cmd = "mkdir /data/log/faultlog/"
        mkdir_native_crash_cmd = "mkdir /data/log/faultlog/temp"
        mkdir_debug_crash_cmd = "mkdir /data/log/faultlog/debug"
        mkdir_js_crash_cmd = "mkdir /data/log/faultlog/faultlogger"
        self.execute_shell_command(mkdir_block_crash_cmd)
        self.execute_shell_command(mkdir_native_crash_cmd)
        self.execute_shell_command(mkdir_js_crash_cmd)
        self.execute_shell_command(mkdir_debug_crash_cmd)

    def _sync_device_time(self):
        # 先同步PC和设备的时间
        SHA_TZ = timezone(
            timedelta(hours=8),
            name='Asia/Shanghai',
        )
        ISOTIMEFORMAT = '%Y-%m-%d %H:%M:%S'
        cur_time = datetime.now(tz=timezone.utc).astimezone(SHA_TZ)\
            .strftime(ISOTIMEFORMAT)
        self.execute_shell_command("date '{}'".format(cur_time))
        self.execute_shell_command("hwclock --systohc")

    def get_recover_result(self, retry=RETRY_ATTEMPTS):
        command = "param get sys.boot_completed"
        stdout = self.execute_shell_command(command, timeout=5 * 1000,
                                            output_flag=False, retry=retry,
                                            abort_on_exception=True).strip()
        if stdout:
            LOG.debug(stdout)
        return stdout

    def set_recover_state(self, state):
        with self.device_lock:
            setattr(self, ConfigConst.recover_state, state)

    def get_recover_state(self, default_state=True):
        with self.device_lock:
            state = getattr(self, ConfigConst.recover_state, default_state)
            return state

    def close(self):
        self.reconnecttimes = 0

    def reset(self):
        self.log.debug("start stop rpc")
        if self._proxy is not None:
            self._proxy.close()
        self._proxy = None
        self.remove_ports()
        self.stop_harmony_rpc()

    @property
    def proxy(self):
        """The first rpc session initiated on this device. None if there isn't
        one.
        """
        try:
            if self._proxy is None:
                self._proxy = self.get_harmony()
        except Exception as error:
            self._proxy = None
            self.log.error("DeviceTest-10012 proxy:%s" % str(error))
        return self._proxy

    @property
    def uitestdeamon(self):
        from devicetest.controllers.uitestdeamon import \
            UiTestDeamon
        if self._uitestdeamon is None:
            self._uitestdeamon = UiTestDeamon(self)
        return self._uitestdeamon

    @classmethod
    def set_module_package(cls, module_packag):
        cls.module_package = module_packag

    @classmethod
    def set_moudle_ablity_name(cls, module_ablity_name):
        cls.module_ablity_name = module_ablity_name

    @property
    def is_harmony(self):
        if self._is_harmony is not None:
            return self._is_harmony
        oh_version = self.execute_shell_command("param get const.product.software.version")
        self.log.debug("is_harmony, OpenHarmony verison :{}".format(oh_version))
        self._is_harmony = True
        return self._is_harmony

    def get_harmony(self):
        if self.initdevice:
            self.start_harmony_rpc(re_install_rpc=True)
        self._h_port = self.get_local_port()
        cmd = "fport tcp:{} tcp:{}".format(
            self._h_port, self.d_port)
        self.connector_command(cmd)
        self.log.info(
            "get_proxy d_port:{} {}".format(self._h_port, self.d_port))
        try:
            from devicetest.controllers.openharmony import OpenHarmony
            self._proxy = OpenHarmony(port=self._h_port, addr=self.host, device=self)
        except Exception as error:
            self.log.error(' proxy init error: {}.'.format(str(error)))
        return self._proxy

    def start_harmony_rpc(self, port=8080, re_install_rpc=False):
        from devicetest.core.error_message import ErrorMessage
        if re_install_rpc:
            try:
                from devicetest.controllers.openharmony import OpenHarmony
                OpenHarmony.install_harmony_rpc(self)
            except (ModuleNotFoundError, ImportError) as error:
                self.log.debug(str(error))
                self.log.error('please check devicetest extension module is exist.')
                raise Exception(ErrorMessage.Error_01437.Topic)
            except Exception as error:
                self.log.debug(str(error))
                self.log.error('root device init RPC error.')
                raise Exception(ErrorMessage.Error_01437.Topic)
        self.stop_harmony_rpc()
        self.execute_shell_command("param set testName 123")
        result = self.execute_shell_command("/system/bin/uitest start-daemon 0123456789 &")
        self.log.debug('start uitest, {}'.format(result))
        cmd = "aa start -a {}.ServiceAbility -b {}".format(DEVICETEST_HAP_PACKAGE_NAME, DEVICETEST_HAP_PACKAGE_NAME)
        result = self.execute_shell_command(cmd)
        self.log.debug('start devicetest ability, {}'.format(result))
        time.sleep(1)
        if not self.is_harmony_rpc_running():
            raise Exception("harmony rpc not running")

    def stop_harmony_rpc(self):
        # 先杀掉uitest和devicetest
        if self.is_harmony_rpc_running():
            self.kill_all_uitest()
            self.kill_devicetest_agent()
        else:
            self.log.debug("stop_harmony_rpc, devicetest rpc is not running.")

    def is_harmony_rpc_running(self):
        cmd = 'ps -ef | grep %s' % DEVICETEST_HAP_PACKAGE_NAME
        rpc_running = self.execute_shell_command(cmd).strip()
        self.log.debug('is_rpc_running out:{}'.format(rpc_running))
        cmd = 'ps -ef | grep %s' % UITEST_NAME
        uitest_running = self.execute_shell_command(cmd).strip()
        self.log.debug('is_uitest_running out:{}'.format(uitest_running))
        if DEVICETEST_HAP_PACKAGE_NAME in rpc_running and UITEST_NAME in uitest_running:
            return True
        return False

    def kill_all_uitest(self):
        cmd = 'ps -ef | grep %s' % UITEST_NAME
        out = self.execute_shell_command(cmd).strip()
        out = out.split("\n")
        for str in out:
            if "start-daemon" in str:
                str = str.split()
                cmd = 'kill %s' % str[1]
                self.execute_shell_command(cmd).strip()
                return

    def kill_devicetest_agent(self):
        cmd = 'ps -ef | grep %s' % DEVICETEST_HAP_PACKAGE_NAME
        out = self.execute_shell_command(cmd).strip()
        out = out.split("\n")
        for str in out:
            if DEVICETEST_HAP_PACKAGE_NAME in str:
                str = str.split()
                cmd = 'kill %s' % str[1]
                self.execute_shell_command(cmd).strip()
                self.log.debug('stop devicetest ability success.')
                return

    def install_app(self, remote_path, command):
        try:
            ret = self.execute_shell_command(
                "pm install %s %s" % (command, remote_path))
            if ret is not None and str(
                    ret) != "" and "Unknown option: -g" in str(ret):
                return self.execute_shell_command(
                    "pm install -r %s" % remote_path)
            return ret
        except Exception as error:
            self.log.error("%s, maybe there has a warning box appears "
                           "when installing RPC." % error)

    def uninstall_app(self, package_name):
        try:
            ret = self.execute_shell_command("pm uninstall %s" % package_name)
            self.log.debug(ret)
            return ret
        except Exception as err:
            self.log.error('DeviceTest-20013 uninstall: %s' % str(err))

    def reconnect(self, waittime=60):
        '''
        @summary: Reconnect the device.
        '''
        if not self.is_harmony:
            if not self.wait_for_boot_completion(waittime):
                raise Exception("Reconnect timed out.")

        if self._proxy:
            self.start_harmony_rpc(re_install_rpc=True)
            self._h_port = self.get_local_port()
            cmd = "fport tcp:{} tcp:{}".format(
                self._h_port, self.d_port)
            self.connector_command(cmd)
            try:
                self._proxy.init(port=self._h_port, addr=self.host, _ad=self)
            except Exception as _:
                time.sleep(3)
                self._proxy.init(port=self._h_port, addr=self.host, _ad=self)

            if self._uitestdeamon is not None:
                self._uitestdeamon.init(self)

        if self._proxy:
            return self._proxy
        return None

    def wait_for_boot_completion(self, waittime=60 * 15, reconnect=False):
        """Waits for the device to boot up.

        Returns:
            True if the device successfully finished booting, False otherwise.
        """
        if not self.wait_for_device_not_available(
                DEFAULT_UNAVAILABLE_TIMEOUT):
            LOG.error("Did not detect device {} becoming unavailable "
                      "after reboot".format(convert_serial(self.device_sn)))
        self._wait_for_device_online()
        self.device_state_monitor.wait_for_device_available(
            self.reboot_timeout)
        return True

    def get_local_port(self):
        from devicetest.utils.util import get_forward_port
        host = self.host
        port = None
        h_port = get_forward_port(self, host, port)
        self.forward_ports.append(h_port)
        self.log.info(
            "tcp forward port: %s for %s*******" % (str(h_port),
                                                    self.device_sn[0:4]))
        return h_port

    def remove_ports(self):
        if self._uitestdeamon is not None:
            self._uitestdeamon = None
        for port in self.forward_ports:
            cmd = "fport rm tcp:{} tcp:{}".format(
                port, self.d_port)
            self.connector_command(cmd)
        self.forward_ports.clear()

    @classmethod
    def check_recover_result(cls, recover_result):
        if HdcHelper.is_hdc_std():
            return "1" in recover_result
        else:
            return "1" == recover_result

    def take_picture(self, name):
        '''
        @summary: 截取手机屏幕图片并保存
        @param  name: 保存的图片名称,通过getTakePicturePath方法获取保存全路径
        '''
        try:
            temp_path = os.path.join(self._device_log_path, "temp")
            path = os.path.join(temp_path, name)
            self.execute_shell_command(
                "snapshot_display -f /data/screen.png")
            self.pull_file("/data/screen.png", path)
        except Exception as error:
            self.log.error("devicetest take_picture: {}".format(str(error)))

        return path

    def set_device_report_path(self, path):
        self._device_log_path = path